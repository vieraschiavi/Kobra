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
# 5. Enforcement: DDL para la base del cliente
# ---------------------------------------------------------------------------
# Adaptado de `mvdg/enforcement.py` de MV Data Governance.
#
# Honestidad de arquitectura, y es lo que hace útil a esto: el enmascarado de
# `enmascarar()` protege lo que sale POR KOBRA. No protege la base del cliente:
# quien se conecte a su Postgres con un cliente SQL ve la tabla entera, y con
# razón — Kobra no está parado en el camino de esa consulta y no puede estarlo.
#
# Lo que sí puede hacer, y es lo que hace acá, es traducir lo que el catálogo
# ya sabe —qué columna es personal, qué rol la ve— al DDL que su DBA aplica en
# la base. Kobra escribe la receta; quien tiene las llaves la ejecuta. **Nunca
# se conecta a correr nada de esto**: devuelve texto.
#
# Postgres y SQL Server porque son los dos motores con enforcement declarativo
# nativo bien establecido (RLS desde 9.5 y Dynamic Data Masking + RLS desde
# 2016). Para MySQL/Oracle/Snowflake el patrón de GRANT/REVOKE aplica igual,
# pero el enmascarado y RLS tienen sintaxis propia que todavía no está acá.
MOTORES_DDL = ("postgresql", "sqlserver")

# Qué rol de la base puede ver cada nivel. Es el espejo en la base de
# VISIBILIDAD_POR_ROL, que rige dentro de Kobra.
ROLES_POR_NIVEL_SUGERIDO = {
    PUBLICO:  ["kobra_lectura"],
    INTERNO:  ["kobra_lectura", "kobra_gestor"],
    PERSONAL: ["kobra_admin"],
    SENSIBLE: ["kobra_admin"],
}


def _ident(nombre: str, motor: str) -> str:
    """Cita un identificador según el motor.

    No es cosmético: sin comillas, una tabla que se llame `orden` o `user`
    —palabras reservadas— rompe el DDL, y un nombre con mayúsculas en Postgres
    se pliega a minúsculas y deja de encontrar la tabla.
    """
    return f"[{nombre}]" if motor == "sqlserver" else f'"{nombre}"'


def _validar_motor(motor: str) -> None:
    if motor not in MOTORES_DDL:
        raise ValueError(
            f"motor {motor!r} no soportado todavía — cubiertos: "
            f"{', '.join(MOTORES_DDL)}")


def ddl_acceso(tabla: str, columnas, roles_por_nivel: dict | None = None,
               motor: str = "postgresql", catalogo: dict | None = None) -> list[str]:
    """GRANT/REVOKE por nivel de sensibilidad.

    Empieza con un REVOKE de PUBLIC: sin eso, una tabla nueva en Postgres
    queda legible por cualquiera con acceso a la base, y todos los GRANT de
    abajo serían decorativos.
    """
    _validar_motor(motor)
    roles = roles_por_nivel or ROLES_POR_NIVEL_SUGERIDO
    t = _ident(tabla, motor)
    ddl = [f"REVOKE ALL ON {t} FROM PUBLIC;"]

    # El acceso a la tabla lo manda su columna MÁS sensible: alcanza una
    # columna personal para que la tabla entera necesite el rol de esa altura.
    nivel_tabla = max((clasificar(c, catalogo) for c in columnas),
                      key=lambda n: _ORDEN[n], default=INTERNO)
    for rol in roles.get(nivel_tabla, []):
        ddl.append(f"GRANT SELECT ON {t} TO {_ident(rol, motor)};")
    ddl.append(f"-- nivel de la tabla: {nivel_tabla} "
               f"(lo fija su columna más sensible)")
    return ddl


def ddl_enmascarado(tabla: str, columnas, motor: str = "postgresql",
                    rol_sin_datos: str = "kobra_gestor",
                    catalogo: dict | None = None) -> list[str]:
    """Enmascara en la base las columnas personales y sensibles.

    Postgres no tiene enmascarado nativo de columna, así que se genera una
    vista con las columnas ofuscadas y se le da acceso al rol sobre la vista,
    no sobre la tabla. SQL Server sí lo tiene (`ADD MASKED WITH`) y se usa
    directo.
    """
    _validar_motor(motor)
    protegidas = [c for c in columnas
                  if _ORDEN[clasificar(c, catalogo)] > _ORDEN[INTERNO]]
    if not protegidas:
        return [f"-- {tabla}: ninguna columna personal ni sensible que enmascarar"]

    ddl = []
    if motor == "sqlserver":
        t = _ident(tabla, motor)
        for col in protegidas:
            bajo = col.lower()
            # `email()` conserva la forma (a***@dominio.com), que deja al
            # gestor confirmar que es la casilla correcta sin poder leerla.
            func = "email()" if ("mail" in bajo or "correo" in bajo) else "default()"
            ddl.append(f"ALTER TABLE {t} ALTER COLUMN {_ident(col, motor)} "
                       f"ADD MASKED WITH (FUNCTION = '{func}');")
        ddl.append(f"-- para que un rol vea el dato real: GRANT UNMASK TO "
                   f"{_ident('kobra_admin', motor)};")
    else:
        seleccion = ", ".join(
            f"'***' AS {_ident(c, motor)}" if c in protegidas else _ident(c, motor)
            for c in columnas)
        vista = _ident(f"{tabla}_enmascarada", motor)
        ddl.append(f"CREATE OR REPLACE VIEW {vista} AS "
                   f"SELECT {seleccion} FROM {_ident(tabla, motor)};")
        ddl.append(f"GRANT SELECT ON {vista} TO {_ident(rol_sin_datos, motor)};")
        ddl.append(f"-- a {rol_sin_datos} se le da la VISTA, nunca la tabla: si "
                   f"tuviera la tabla, la vista no protegería nada")
    return ddl


def ddl_por_fila(tabla: str, columna_politica: str, rol: str,
                 motor: str = "postgresql") -> list[str]:
    """Seguridad por fila: cada gestor ve solo su cartera asignada.

    El valor con el que se compara en tiempo de ejecución lo define quien
    administra la base (variable de sesión, `current_user`), porque depende de
    cómo esa empresa identifica a sus gestores — Kobra no lo puede saber.
    """
    _validar_motor(motor)
    t, c = _ident(tabla, motor), _ident(columna_politica, motor)
    if motor == "postgresql":
        return [
            f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;",
            f"CREATE POLICY {tabla}_rls ON {t} FOR SELECT "
            f"TO {_ident(rol, motor)} "
            f"USING ({c} = current_setting('kobra.gestor_actual', true));",
        ]
    fn = f"dbo.fn_{tabla}_predicado"
    return [
        f"CREATE FUNCTION {fn}(@valor AS sysname) RETURNS TABLE "
        f"WITH SCHEMABINDING AS RETURN SELECT 1 AS resultado "
        f"WHERE @valor = SESSION_CONTEXT(N'kobra_gestor_actual');",
        f"CREATE SECURITY POLICY {tabla}_rls "
        f"ADD FILTER PREDICATE {fn}({c}) ON {t};",
    ]


def plan_enforcement(tabla: str, columnas, motor: str = "postgresql",
                     roles_por_nivel: dict | None = None,
                     catalogo: dict | None = None) -> dict:
    """El paquete completo, listo para copiar y pasarle al DBA."""
    _validar_motor(motor)
    columnas = list(columnas)
    accesos = ddl_acceso(tabla, columnas, roles_por_nivel, motor, catalogo)
    mascaras = ddl_enmascarado(tabla, columnas, motor, catalogo=catalogo)
    guion = "\n".join([
        "-- MV Kobra AI · DDL de gobernanza GENERADO, no ejecutado.",
        "-- Kobra nunca se conecta a correr esto: revisalo y aplicalo vos.",
        f"-- Motor: {motor} · Tabla: {tabla}",
        "",
        "-- 1) Acceso por nivel de sensibilidad",
        *accesos,
        "",
        "-- 2) Enmascarado de columnas personales y sensibles",
        *mascaras,
    ])
    return {"motor": motor, "tabla": tabla,
            "sentencias_acceso": len(accesos),
            "sentencias_enmascarado": len(mascaras),
            "guion": guion}


# ---------------------------------------------------------------------------
# 6. Glosario de negocio
# ---------------------------------------------------------------------------
# Adaptado de `mvdg/glossary.py`, con los términos de cobranzas.
#
# Para qué sirve: que "mora" signifique lo mismo en el tablero, en el informe
# al directorio y en la conversación con el gestor. Es el problema más común
# y menos técnico del gobierno de datos — dos áreas reportan el mismo número
# distinto porque cada una definió el término por su cuenta, y la reunión se
# va en discutir cuál está bien.
GLOSARIO = [
    {"id": "mora", "es": "Mora", "pt": "Inadimplência",
     "definicion_es": "Días transcurridos desde el primer vencimiento impago. "
                      "Se cuenta desde la cuota más antigua sin pagar, no desde la última.",
     "definicion_pt": "Dias desde o primeiro vencimento não pago. Conta-se a partir "
                      "da parcela mais antiga em aberto, não da última.",
     "dueno": "Gerencia de Cobranzas", "columnas": ["dias_mora", "tramo_mora"]},
    {"id": "gestion", "es": "Gestión", "pt": "Ação de cobrança",
     "definicion_es": "Cada acción de cobranza asistida por IA: una gestión del "
                      "agente negociador, el análisis de una llamada o la evaluación "
                      "de un audio. NO cuenta mirar el tablero ni exportar.",
     "definicion_pt": "Cada ação de cobrança assistida por IA: uma ação do agente "
                      "negociador, a análise de uma ligação ou a avaliação de um "
                      "áudio. NÃO conta ver o painel nem exportar.",
     "dueno": "Gerencia de Cobranzas", "columnas": ["gestiones_previas"]},
    {"id": "promesa", "es": "Promesa de pago", "pt": "Promessa de pagamento",
     "definicion_es": "Compromiso de pago con fecha y monto acordados en una gestión. "
                      "Se considera cumplida si el pago entra dentro de los 3 días "
                      "hábiles siguientes a la fecha prometida.",
     "definicion_pt": "Compromisso de pagamento com data e valor acordados numa ação. "
                      "Considera-se cumprida se o pagamento entrar em até 3 dias "
                      "úteis após a data prometida.",
     "dueno": "Gerencia de Cobranzas",
     "columnas": ["promesas_cumplidas", "promesas_incumplidas"]},
    {"id": "probpago", "es": "ProbPago", "pt": "ProbPago",
     "definicion_es": "Probabilidad estimada de que un deudor pague en los próximos "
                      "30 días. Sale del modelo, no de una regla: es una estimación "
                      "con error, no una certeza.",
     "definicion_pt": "Probabilidade estimada de que um devedor pague nos próximos "
                      "30 dias. Vem do modelo, não de uma regra: é uma estimativa "
                      "com erro, não uma certeza.",
     "dueno": "Datos / Riesgo", "columnas": ["prob_pago"]},
    {"id": "contactabilidad", "es": "Contactabilidad", "pt": "Contatabilidade",
     "definicion_es": "Proporción de intentos de contacto que terminaron en una "
                      "conversación efectiva, sobre los últimos 6 meses. Un teléfono "
                      "que atiende y corta NO cuenta como efectivo.",
     "definicion_pt": "Proporção de tentativas de contato que terminaram em conversa "
                      "efetiva, nos últimos 6 meses. Um telefone que atende e desliga "
                      "NÃO conta como efetivo.",
     "dueno": "Operaciones", "columnas": ["contactabilidad"]},
    {"id": "recupero", "es": "Recupero", "pt": "Recuperação",
     "definicion_es": "Monto efectivamente cobrado en el período, imputado a la fecha "
                      "en que entró el dinero — no a la fecha de la promesa ni a la "
                      "de la gestión que lo originó.",
     "definicion_pt": "Valor efetivamente recebido no período, lançado na data em que "
                      "o dinheiro entrou — não na data da promessa nem na da ação "
                      "que o originou.",
     "dueno": "Finanzas", "columnas": ["pago"]},
    {"id": "cartera", "es": "Cartera", "pt": "Carteira",
     "definicion_es": "Conjunto de deudas vigentes bajo gestión. Excluye las dadas de "
                      "baja contablemente (castigadas) aunque sigan siendo cobrables.",
     "definicion_pt": "Conjunto de dívidas vigentes sob gestão. Exclui as baixadas "
                      "contabilmente, mesmo que ainda sejam cobráveis.",
     "dueno": "Gerencia de Cobranzas", "columnas": ["monto_deuda"]},
]


def glosario(idioma: str = "es") -> list[dict]:
    """Los términos en el idioma pedido, con qué columnas los materializan."""
    corto = "pt" if str(idioma).lower().startswith("pt") else "es"
    return [{"id": t["id"], "termino": t[corto],
             "definicion": t[f"definicion_{corto}"],
             "dueno": t["dueno"], "columnas": t["columnas"]}
            for t in GLOSARIO]


def termino_de(columna: str, idioma: str = "es") -> dict | None:
    """Qué término de negocio define esta columna.

    Es lo que convierte al glosario en algo vivo: al mirar una columna del
    catálogo se ve su definición oficial, en vez de tener que ir a buscarla a
    un documento que nadie abre.
    """
    for t in glosario(idioma):
        if columna in t["columnas"]:
            return t
    return None


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
