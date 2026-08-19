# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Gobernanza de datos
=================================
Módulo de la suite (se vende aparte: `plan.exigir("gobernanza")`). Responde
cuatro preguntas que una empresa hace antes de dejar entrar un producto a su
cartera real, y que hasta ahora Kobra no podía contestar:

  1. **¿Qué dato es personal?**       → clasificación (`clasificar`)
  2. **¿Quién puede verlo?**          → enmascarado por rol (`enmascarar`)
  3. **¿Este dato sirve?**            → reglas de calidad (`evaluar_calidad`)
  4. **¿De dónde salió?**             → linaje (`registrar_linaje`, `linaje`)

Por qué enmascarar en vez de borrar
------------------------------------
La reacción obvia a "este dato es personal" es esconderlo, y deja el producto
inútil: un gestor sin `monto_deuda` no puede cobrar. Acá cada nivel de
sensibilidad tiene una estrategia que **conserva el valor analítico y saca el
identificatorio**: un ingreso se vuelve un tramo (`$30.000–$40.000`), un
identificador se vuelve un seudónimo estable, un teléfono deja ver los últimos
dígitos para que el gestor confirme con quién habla. El gestor sigue
trabajando; lo que no puede es llevarse una lista nominal.

Qué NO es esto
---------------
No es cifrado ni control de acceso a nivel de base de datos. El enmascarado
ocurre en la capa de aplicación: protege contra que un rol vea de más y contra
que un export se lleve datos crudos, no contra alguien con acceso al archivo.
Es la misma clase de garantía que `kobra/plan.py` da sobre el cupo, y se
declara igual de explícito para no vender lo que no es.

El seudónimo usa HMAC-SHA256 con una sal propia de la instalación: es estable
(el mismo deudor da siempre el mismo seudónimo, así que se puede agrupar y
contar) y no reversible sin la sal. Un hash pelado NO serviría: el espacio de
identificadores es chico y se recorre entero en segundos.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone

import pandas as pd

from kobra import auditoria as kauditoria
from kobra import config as kconfig

# ---------------------------------------------------------------------------
# 1. Clasificación
# ---------------------------------------------------------------------------
# Cuatro niveles, de menor a mayor sensibilidad. El orden importa: se usa para
# decidir si un rol alcanza a ver una columna.
PUBLICO = "publico"          # agregados, nada que identifique
INTERNO = "interno"          # del negocio, no de la persona
PERSONAL = "personal"        # identifica o permite reidentificar
SENSIBLE = "sensible"        # personal + daño concreto si se filtra

NIVELES = (PUBLICO, INTERNO, PERSONAL, SENSIBLE)
_ORDEN = {n: i for i, n in enumerate(NIVELES)}

# Clasificación explícita del dataset de cartera. Se declara a mano porque
# adivinar por nombre es exactamente el error que hace inútiles a estas
# herramientas: `score_buro` no dice "personal" en ninguna parte del nombre y
# es de lo más sensible que hay acá.
CATALOGO_CARTERA = {
    "id_deudor":                PERSONAL,   # seudónimo, pero identifica a una persona
    "segmento":                 INTERNO,
    "producto":                 INTERNO,
    "departamento":             PERSONAL,   # cuasi-identificador: cruza y reidentifica
    "monto_deuda":              INTERNO,
    "dias_mora":                INTERNO,
    "cuotas_atrasadas":         INTERNO,
    "antiguedad_cliente_meses": INTERNO,
    "score_buro":               SENSIBLE,   # dato crediticio: afecta el acceso al crédito
    "ingreso_estimado":         SENSIBLE,   # dato patrimonial
    "pagos_ultimos_12m":        INTERNO,
    "promesas_cumplidas":       INTERNO,
    "promesas_incumplidas":     INTERNO,
    "contactabilidad":          INTERNO,
    "gestiones_previas":        INTERNO,
    "canal_preferido":          INTERNO,
    "pago":                     INTERNO,
    "tramo_mora":               PUBLICO,
}

# Heurística para columnas que no están en el catálogo — el caso de un cliente
# que sube su propia cartera con nombres que no conocemos. Se aplica SOLO como
# respaldo y siempre hacia el lado seguro: ante la duda, se clasifica de más.
_PATRONES = [
    (SENSIBLE, r"salari|ingreso|sueldo|patrimon|score|buro|burÃ³|buró|"
               r"salud|medic|religi|etni|politic|biometr|penal|judicial"),
    (PERSONAL, r"nombre|apellido|documento|cedula|cédula|ci\b|rut|cuit|cuil|"
               r"dni|pasaporte|email|mail|correo|telefon|teléfon|celular|"
               r"movil|móvil|direccion|dirección|domicilio|calle|barrio|"
               r"departamento|localidad|nacimiento|edad|genero|género|sexo|"
               r"id_deudor|id_cliente|titular"),
]


def clasificar(columna: str, catalogo: dict | None = None) -> str:
    """Nivel de sensibilidad de una columna.

    Primero el catálogo declarado; si no está, la heurística por nombre. Nunca
    devuelve `PUBLICO` por descarte: una columna desconocida se trata como
    `INTERNO`, porque el default de una herramienta de gobernanza tiene que
    equivocarse hacia proteger de más, no de menos.
    """
    cat = CATALOGO_CARTERA if catalogo is None else catalogo
    if columna in cat:
        return cat[columna]
    limpio = columna.strip().lower()
    for nivel, patron in _PATRONES:
        if re.search(patron, limpio):
            return nivel
    return INTERNO


def clasificar_tabla(df: pd.DataFrame, catalogo: dict | None = None) -> dict:
    """`{columna: nivel}` para todas las columnas de un DataFrame."""
    return {c: clasificar(c, catalogo) for c in df.columns}


# ---------------------------------------------------------------------------
# 2. Enmascarado por rol
# ---------------------------------------------------------------------------
# Hasta qué nivel ve cada rol EN CLARO. Lo de más arriba se enmascara.
#
# `gestor` llega a INTERNO: ve la deuda, la mora y el canal —todo lo que
# necesita para cobrar— pero el identificador le llega seudonimizado y los
# datos patrimoniales por tramo. `admin` ve todo: es quien responde legalmente
# por la cartera.
VISIBILIDAD_POR_ROL = {
    "admin":  SENSIBLE,
    "gestor": INTERNO,
}
_NIVEL_POR_DEFECTO = INTERNO

_CLAVE_SAL = "GOBERNANZA_SAL"


def _sal() -> bytes:
    """Sal de la instalación para los seudónimos. Se crea una sola vez.

    Vive en el mismo almacén seguro que las demás claves (keyring del sistema
    operativo > archivo cifrado). Es por instalación a propósito: dos empresas
    distintas no pueden cruzar sus seudónimos para reconstruir una persona.
    """
    guardada = kconfig.leer_extra(_CLAVE_SAL)
    if guardada:
        return bytes.fromhex(guardada)
    nueva = secrets.token_bytes(32)
    kconfig.guardar_extra(_CLAVE_SAL, nueva.hex())
    return nueva


def seudonimo(valor, largo: int = 10) -> str:
    """Identificador estable y no reversible: `KB-100000` -> `anon:7f3a2b91c4`.

    HMAC y no un hash suelto: con SHA-256 pelado, quien tenga la lista de
    identificadores posibles la recorre entera y deshace el seudónimo. La sal
    secreta es lo que lo impide.
    """
    if pd.isna(valor):
        return ""
    d = hmac.new(_sal(), str(valor).encode("utf-8"), hashlib.sha256)
    return "anon:" + d.hexdigest()[:largo]


def _tramo(valor, ancho: int = 10000) -> str:
    """Un número se vuelve su rango: 37.300 -> `30.000–40.000`.

    Conserva lo que sirve para analizar (distribución, correlación con el pago)
    y saca la precisión que permite reidentificar a alguien por su ingreso.
    """
    if pd.isna(valor):
        return ""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "—"
    piso = int(v // ancho) * ancho
    return f"{piso:,.0f}–{piso + ancho:,.0f}".replace(",", ".")


def _ancho_de_tramo(serie: pd.Series) -> int:
    """Ancho de tramo proporcional a la escala de la columna.

    Un ancho fijo sería inútil en los dos extremos: agrupar un score de buró
    (300–950) de a 10.000 lo deja todo en un solo tramo, y agrupar un ingreso
    de a 10 no esconde nada.
    """
    try:
        rango = float(serie.max()) - float(serie.min())
    except (TypeError, ValueError):
        return 10000
    if rango <= 0:
        return 1
    # Un orden de magnitud menos que el rango: da ~10 tramos, que es donde
    # todavía se ve la forma de la distribución sin identificar a nadie.
    magnitud = 10 ** max(0, len(str(int(rango))) - 2)
    return int(magnitud)


def enmascarar(df: pd.DataFrame, rol: str, catalogo: dict | None = None) -> pd.DataFrame:
    """Copia del DataFrame con lo que `rol` no puede ver ya enmascarado.

    No borra columnas: las transforma. Un gestor sigue viendo todas las
    columnas y puede trabajar; lo que no puede es llevarse los valores crudos.
    """
    tope = _ORDEN[VISIBILIDAD_POR_ROL.get(rol, _NIVEL_POR_DEFECTO)]
    salida = df.copy()
    for col in df.columns:
        nivel = clasificar(col, catalogo)
        if _ORDEN[nivel] <= tope:
            continue
        serie = df[col]
        if nivel == PERSONAL:
            salida[col] = serie.map(seudonimo)
        else:                                   # SENSIBLE
            if pd.api.types.is_numeric_dtype(serie):
                ancho = _ancho_de_tramo(serie)
                salida[col] = serie.map(lambda v, a=ancho: _tramo(v, a))
            else:
                salida[col] = serie.map(seudonimo)
    return salida


def columnas_visibles(rol: str, columnas, catalogo: dict | None = None) -> dict:
    """`{columna: True/False}` — si el rol la ve en claro o enmascarada.

    Sirve para que la interfaz avise cuáles están enmascaradas en vez de
    mostrar valores raros sin explicación.
    """
    tope = _ORDEN[VISIBILIDAD_POR_ROL.get(rol, _NIVEL_POR_DEFECTO)]
    return {c: _ORDEN[clasificar(c, catalogo)] <= tope for c in columnas}


# ---------------------------------------------------------------------------
# 3. Reglas de calidad (las seis dimensiones DAMA)
# ---------------------------------------------------------------------------
COMPLETITUD = "completitud"
UNICIDAD = "unicidad"
VALIDEZ = "validez"
CONSISTENCIA = "consistencia"
OPORTUNIDAD = "oportunidad"
EXACTITUD = "exactitud"

DIMENSIONES = (COMPLETITUD, UNICIDAD, VALIDEZ, CONSISTENCIA, OPORTUNIDAD,
               EXACTITUD)


class Regla:
    """Una regla de calidad sobre una tabla.

    `evaluar` devuelve la cantidad de filas que la INCUMPLEN. Se cuenta el
    incumplimiento y no el cumplimiento a propósito: lo que hay que mostrar y
    corregir son las filas malas, y un conteo de buenas esconde el problema
    detrás de un porcentaje alto.
    """

    def __init__(self, nombre: str, dimension: str, columna: str | None,
                 predicado, umbral: float = 0.0, descripcion: str = "",
                 necesita=None):
        if dimension not in DIMENSIONES:
            raise ValueError(f"dimensión desconocida: {dimension!r}")
        self.nombre = nombre
        self.dimension = dimension
        self.columna = columna
        self._predicado = predicado
        self.umbral = umbral          # % de filas malas tolerado (0 = ninguna)
        self.descripcion = descripcion
        # Columnas que el predicado necesita. Una regla de una sola columna la
        # deduce de `columna`; una regla ENTRE columnas tiene que declararlas,
        # porque si no se descubre que falta una recién al reventar dentro del
        # predicado — justo evaluando los datos rotos que esto viene a revisar.
        if necesita is not None:
            self.necesita = tuple(necesita)
        elif columna is not None:
            self.necesita = (columna,)
        else:
            self.necesita = ()

    def _sin_datos(self, df: pd.DataFrame, motivo: str) -> dict:
        return {"regla": self.nombre, "dimension": self.dimension,
                "columna": self.columna, "estado": "no_aplica",
                "malas": 0, "total": len(df), "pct_malas": 0.0,
                "umbral": self.umbral, "detalle": motivo}

    def evaluar(self, df: pd.DataFrame) -> dict:
        faltan = [c for c in self.necesita if c not in df.columns]
        if faltan:
            return self._sin_datos(
                df, f"no están en los datos: {', '.join(faltan)}")
        try:
            malas = int(self._predicado(df).sum())
        except Exception as e:                          # noqa: BLE001
            # Red de contención para reglas que define el cliente: una regla
            # mal escrita tiene que aparecer como regla rota en el informe, no
            # tumbar la evaluación entera y dejarlo sin ver las demás.
            return self._sin_datos(df, f"la regla no se pudo evaluar: {e}")
        total = len(df)
        pct = (malas / total * 100) if total else 0.0
        return {"regla": self.nombre, "dimension": self.dimension,
                "columna": self.columna,
                "estado": "ok" if pct <= self.umbral else "falla",
                "malas": malas, "total": total, "pct_malas": round(pct, 2),
                "umbral": self.umbral, "detalle": self.descripcion}


def regla_no_nulos(columna: str, umbral: float = 0.0) -> Regla:
    return Regla(f"{columna}: sin vacíos", COMPLETITUD, columna,
                 lambda d: d[columna].isna(), umbral,
                 "una fila sin este dato no se puede gestionar")


def regla_unica(columna: str, umbral: float = 0.0) -> Regla:
    return Regla(f"{columna}: sin duplicados", UNICIDAD, columna,
                 lambda d: d[columna].duplicated(keep=False), umbral,
                 "un identificador repetido gestiona dos veces a la misma persona")


def regla_rango(columna: str, minimo=None, maximo=None,
                umbral: float = 0.0) -> Regla:
    def fuera(d):
        s = pd.to_numeric(d[columna], errors="coerce")
        mal = s.isna()
        if minimo is not None:
            mal = mal | (s < minimo)
        if maximo is not None:
            mal = mal | (s > maximo)
        return mal
    limites = " a ".join(str(x) for x in (minimo, maximo) if x is not None)
    return Regla(f"{columna}: dentro de {limites}", VALIDEZ, columna, fuera,
                 umbral, "un valor fuera de rango suele ser un error de carga")


def regla_valores(columna: str, permitidos, umbral: float = 0.0) -> Regla:
    admitidos = set(permitidos)
    return Regla(f"{columna}: valores conocidos", VALIDEZ, columna,
                 lambda d: ~d[columna].isin(admitidos), umbral,
                 f"solo se esperan: {sorted(admitidos)}")


def regla_coherencia(nombre: str, predicado_malo, descripcion: str = "",
                     umbral: float = 0.0, necesita=()) -> Regla:
    """Regla entre columnas: `lambda d: (d.a > 0) & (d.b == 0)`.

    `necesita` lista las columnas que toca el predicado. Es obligatorio en la
    práctica: sin eso, una tabla a la que le falte una de ellas hace reventar
    la regla en vez de reportarla como no aplicable.
    """
    return Regla(nombre, CONSISTENCIA, None, predicado_malo, umbral,
                 descripcion, necesita=necesita)


def reglas_cartera() -> list[Regla]:
    """El juego de reglas de la cartera de cobranzas.

    No son genéricas: cada una viene de un error de carga que rompe algo
    concreto río abajo (el scoring, la gestión o el reporte).
    """
    return [
        regla_no_nulos("id_deudor"),
        regla_unica("id_deudor"),
        regla_no_nulos("monto_deuda"),
        regla_rango("monto_deuda", minimo=0),
        regla_rango("dias_mora", minimo=0, maximo=3650),
        regla_rango("score_buro", minimo=300, maximo=950),
        regla_rango("contactabilidad", minimo=0, maximo=1),
        regla_rango("cuotas_atrasadas", minimo=0),
        # Una deuda en mora con cero días de atraso es contradictorio, y el
        # modelo la usa como si fuera al día.
        regla_coherencia(
            "mora coherente con cuotas atrasadas",
            lambda d: (d["cuotas_atrasadas"] > 0) & (d["dias_mora"] <= 0),
            "hay cuotas atrasadas pero los días de mora dicen que está al día",
            necesita=("cuotas_atrasadas", "dias_mora")),
    ]


def evaluar_calidad(df: pd.DataFrame, reglas: list[Regla] | None = None) -> dict:
    """Corre las reglas y devuelve el informe.

    Nunca lanza: un dato malo tiene que poder mostrarse y decidirse, no tumbar
    el proceso. Quien quiera cortar la carga mira `apto`.
    """
    reglas = reglas_cartera() if reglas is None else reglas
    resultados = [r.evaluar(df) for r in reglas]
    fallas = [r for r in resultados if r["estado"] == "falla"]
    por_dimension = {}
    for dim in DIMENSIONES:
        del_dim = [r for r in resultados if r["dimension"] == dim
                   and r["estado"] != "no_aplica"]
        if not del_dim:
            continue
        buenas = sum(1 for r in del_dim if r["estado"] == "ok")
        por_dimension[dim] = round(buenas / len(del_dim) * 100, 1)
    return {
        "apto": not fallas,
        "filas": len(df),
        "reglas_corridas": sum(1 for r in resultados if r["estado"] != "no_aplica"),
        "fallas": len(fallas),
        "por_dimension": por_dimension,
        "resultados": resultados,
    }


# ---------------------------------------------------------------------------
# 4. Linaje
# ---------------------------------------------------------------------------
# El linaje se escribe en el MISMO log append-only con cadena de hashes que ya
# usa el resto de la app (kobra/auditoria.py). No se inventa un almacén nuevo:
# la garantía de que nadie editó el linaje después es exactamente la que ese
# log ya da, y tener dos registros de "qué pasó" que puedan discrepar es peor
# que tener uno.
ACCION_LINAJE = "linaje"


def registrar_linaje(destino: str, origenes, operacion: str,
                     filas: int | None = None, detalle: dict | None = None) -> None:
    """Deja asentado que `destino` salió de `origenes` por `operacion`."""
    if isinstance(origenes, str):
        origenes = [origenes]
    cuerpo = {
        "destino": destino,
        "origenes": list(origenes),
        "operacion": operacion,
        "filas": filas,
        "cuando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if detalle:
        cuerpo.update(detalle)
    kauditoria.registrar(ACCION_LINAJE, cuerpo)


def linaje(destino: str | None = None) -> list[dict]:
    """Los asientos de linaje, opcionalmente los de un destino."""
    entradas = [e for e in kauditoria.leer()
                if e.get("accion") == ACCION_LINAJE]
    if destino is None:
        return entradas
    return [e for e in entradas
            if (e.get("detalle") or {}).get("destino") == destino]


def aguas_arriba(destino: str, _vistos: set | None = None) -> list[str]:
    """Todo lo que alimentó a `destino`, directa o indirectamente.

    Es la pregunta que se hace cuando un número del dashboard está mal: de
    dónde salió. Corta ciclos —un linaje mal cargado puede tenerlos— en vez de
    colgarse.
    """
    _vistos = set() if _vistos is None else _vistos
    if destino in _vistos:
        return []
    _vistos.add(destino)
    resultado = []
    for e in linaje(destino):
        for origen in (e.get("detalle") or {}).get("origenes", []):
            if origen in _vistos:
                continue
            resultado.append(origen)
            resultado.extend(aguas_arriba(origen, _vistos))
    return resultado


def aguas_abajo(origen: str) -> list[str]:
    """Qué se rompe si `origen` está mal: la pregunta al revés."""
    salida = []
    for e in linaje():
        det = e.get("detalle") or {}
        if origen in det.get("origenes", []):
            destino = det.get("destino")
            if destino and destino not in salida:
                salida.append(destino)
    return salida


# ---------------------------------------------------------------------------
# Resumen para la interfaz
# ---------------------------------------------------------------------------
def resumen(df: pd.DataFrame, rol: str = "admin") -> dict:
    """Todo lo que necesita la pantalla de gobernanza, en una sola llamada."""
    niveles = clasificar_tabla(df)
    conteo = {n: sum(1 for v in niveles.values() if v == n) for n in NIVELES}
    calidad = evaluar_calidad(df)
    return {
        "columnas": len(df.columns),
        "filas": len(df),
        "por_nivel": conteo,
        "clasificacion": niveles,
        "visibles": columnas_visibles(rol, df.columns),
        "calidad": calidad,
        "integridad_log": kauditoria.verificar_integridad(),
    }
