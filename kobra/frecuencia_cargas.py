# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Frecuencia de cargas: ¿está al día cada tabla?
=============================================================
El tablero más aburrido y el que más problemas evita: para cada tabla que el
programa usa, cuándo se cargó por última vez, de qué fecha son los datos,
cuántas filas tiene y si eso llegó tarde.

El problema que resuelve
------------------------
Un dashboard que muestra números viejos no se ve roto: se ve igual que uno
correcto. La mora de ayer y la de hace tres semanas se dibujan con el mismo
gráfico verde. El daño no aparece cuando el proceso falla, aparece en la
reunión donde alguien decide sobre datos que no sabía que estaban vencidos.

Por eso lo que importa no es "cuándo se cargó" sino **"¿llegó tarde?"**, y esa
respuesta necesita saber cada cuánto se ESPERA cada tabla. Sin la frecuencia
esperada, una fecha de carga es un dato sin veredicto.

De dónde sale la verdad
-----------------------
Del disco, no de una tabla que alguien tenga que mantener: fecha de
modificación del archivo, cantidad de filas y —cuando la tabla tiene una
columna de fecha— la fecha máxima del dato. Un registro paralelo se
desincroniza del archivo real, y ahí el panel pasa a mentir con confianza.

La distinción que importa
-------------------------
**Fecha del dato** y **fecha de carga** no son lo mismo, y confundirlas es el
error clásico: un proceso que corrió hoy a las 6 AM pero trajo el cierre de
hace tres días está "actualizado" y sus datos están viejos. El panel muestra
las dos, siempre.

Idiomas
-------
La estructura (qué tablas hay, cada cuánto se esperan, qué columna de fecha
tienen) vive acá; el texto vive en `kobra/frecuencia/{es,en,pt}.json`. Es la
misma separación que usa la memoria técnica y por el mismo motivo: con la
prosa metida en el código, agregar un idioma obliga a tocar la lógica y las
tres versiones se separan a los pocos meses.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

# Estados posibles. El vocabulario es el del operador, no el del sistema.
AL_DIA = "al_dia"
ATRASADA = "atrasada"
SIN_DATOS = "sin_datos"

# Cuánto se tolera antes de marcar atraso, por frecuencia esperada. Es 1,5x el
# período: un proceso diario que llega a las 30 horas todavía no es un
# problema —pudo correr tarde—, a las 40 sí. Sin margen, el panel se pone rojo
# todas las mañanas antes de que corra el proceso y se lo deja de mirar, que
# es la forma en que un semáforo deja de servir.
TOLERANCIA = 1.5

PERIODOS_HORAS = {
    "continua": 1,
    "diaria": 24,
    "semanal": 24 * 7,
    "mensual": 24 * 30,
    # `manual` no tiene vencimiento: la sube una persona cuando corresponde.
    # Marcarla en rojo por antigüedad sería ruido, no información.
    "manual": None,
}

IDIOMAS = ("es", "en", "pt")
_DIR_TEXTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "frecuencia")


@dataclass(frozen=True)
class Tabla:
    """Una tabla que el programa usa, con su cadencia esperada.

    Sin prosa: el nombre y el "para qué" salen del diccionario del idioma.
    """
    id: str
    frecuencia: str
    # Columna de fecha del DATO, si la tabla tiene. Distinta de la fecha de
    # carga: ver el docstring del módulo.
    columna_fecha: str | None = None
    etiquetas: tuple[str, ...] = field(default_factory=tuple)
    # ¿Es un archivo de filas? El modelo entrenado es un binario: contarle
    # "líneas" da un número que parece un dato y no lo es —el `.joblib` decía
    # «45 registros», que no significa nada— y un número inventado en un panel
    # que existe para dar confianza es exactamente lo que no puede pasar.
    tabular: bool = True


# El catálogo de tablas que la aplicación lee de verdad. Los ids coinciden con
# las claves que resuelve `webapp/backend/api.py::_rutas_de_tablas`, y hay un
# test que falla si acá se nombra una tabla que el backend no sabe ubicar.
TABLAS: tuple[Tabla, ...] = (
    Tabla("scored", "diaria", columna_fecha=None, etiquetas=("núcleo",)),
    Tabla("gestiones", "diaria", columna_fecha="fecha_gestion",
          etiquetas=("núcleo",)),
    Tabla("calidad", "semanal", columna_fecha="fecha", etiquetas=("calidad",)),
    Tabla("cartera_real", "manual", etiquetas=("datos",)),
    Tabla("modelo", "mensual", etiquetas=("ml",), tabular=False),
)


def por_id(id_tabla: str) -> Tabla | None:
    return next((t for t in TABLAS if t.id == id_tabla), None)


def normalizar(idioma: str | None) -> str:
    """Cualquier cosa rara cae a castellano: un `Accept-Language` inesperado no
    puede dejar la pantalla sin texto."""
    codigo = (idioma or "es").strip().lower()[:2]
    return codigo if codigo in IDIOMAS else "es"


@lru_cache(maxsize=len(IDIOMAS))
def textos(idioma: str = "es") -> dict:
    """El diccionario del idioma, cacheado: el panel se abre en cada pantalla."""
    ruta = os.path.join(_DIR_TEXTOS, f"{normalizar(idioma)}.json")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _fecha_dato(ruta: str, columna: str | None) -> str | None:
    """La fecha MÁXIMA de la columna de fecha, que es la fecha del dato.

    Se lee solo esa columna: estas tablas tienen cientos de miles de filas y
    el panel se abre en cada carga de pantalla. Traer el archivo entero para
    mirar una columna es la diferencia entre una pantalla que responde y una
    que tarda cinco segundos.

    `format="mixed"` no es un detalle: una cartera real trae `2026-01-01` y
    `2026-06-30 23:50` en la MISMA columna, y sin eso pandas infiere el
    formato de la primera fila y convierte en NaT todas las que traen hora.
    Con la fecha más nueva justo en una de esas filas, el panel informaba un
    dato de febrero cuando el último era de junio: cinco meses de atraso
    inventados, en silencio y en la pantalla que existe para que el atraso
    NO pase inadvertido.
    """
    if not columna:
        return None
    try:
        import pandas as pd
        serie = pd.read_csv(ruta, usecols=[columna])[columna]
        fecha = pd.to_datetime(serie, format="mixed", errors="coerce").max()
        return None if pd.isna(fecha) else fecha.strftime("%Y-%m-%d")
    except Exception:
        # Una tabla sin esa columna, o con basura adentro, no puede tirar
        # abajo el panel entero: se muestra sin fecha de dato.
        return None


def _filas(ruta: str, tabular: bool = True) -> int | None:
    """Cuenta filas sin cargar el archivo en memoria.

    `None` para lo que no son filas: un `.joblib` tiene saltos de línea adentro
    y contarlos devuelve un número con toda la pinta de ser un dato.
    """
    if not tabular:
        return None
    try:
        with open(ruta, "rb") as f:
            return max(0, sum(1 for _ in f) - 1)   # menos el encabezado
    except OSError:
        return None


def _humano(horas: float, txt: dict) -> str:
    """«hace 3 días» y no «hace 74.2 horas». El panel lo lee un operador."""
    hace = txt["hace"]
    if horas < 1:
        return hace["minutos"].format(n=int(horas * 60))
    if horas < 48:
        return hace["horas"].format(n=int(horas))
    dias = horas / 24
    if dias < 60:
        return hace["dias"].format(n=int(dias))
    return hace["meses"].format(n=int(dias / 30))


def estado_de(ruta: str, tabla: Tabla, ahora: datetime | None = None,
              idioma: str = "es") -> dict:
    """El estado de una tabla, leído del disco.

    `ahora` se puede inyectar para los tests: un semáforo que depende del reloj
    es imposible de probar de otra forma sin dejar tests que fallan un martes.
    """
    ahora = ahora or datetime.now()
    txt = textos(idioma)
    ficha = txt["tablas"][tabla.id]
    base = {
        "id": tabla.id,
        "nombre": ficha["nombre"],
        "para_que": ficha["para_que"],
        "frecuencia": tabla.frecuencia,
        "esperada": txt["cada"][tabla.frecuencia],
        "etiquetas": list(tabla.etiquetas),
    }

    if not ruta or not os.path.exists(ruta):
        return {**base, "estado": SIN_DATOS, "carga": None, "dia_carga": None,
                "fecha_dato": None, "filas": None, "horas_desde_carga": None,
                "motivo": txt["motivo"]["sin_datos"]}

    carga = datetime.fromtimestamp(os.path.getmtime(ruta))
    horas = (ahora - carga).total_seconds() / 3600
    limite = PERIODOS_HORAS.get(tabla.frecuencia)

    if limite is None:
        estado, motivo = AL_DIA, txt["motivo"]["manual"]
    elif horas <= limite * TOLERANCIA:
        estado, motivo = AL_DIA, ""
    else:
        estado = ATRASADA
        motivo = txt["motivo"]["atrasada"].format(
            frecuencia=txt["frecuencia"][tabla.frecuencia],
            hace=_humano(horas, txt),
            atraso=_humano(horas - limite, txt))

    return {
        **base,
        "estado": estado,
        "carga": carga.strftime("%Y-%m-%d %H:%M:%S"),
        # El día de la semana, como en el panel de referencia: un operador
        # detecta "cargó un domingo" más rápido por el nombre que por la fecha.
        "dia_carga": txt["dias"][carga.weekday()],
        "fecha_dato": _fecha_dato(ruta, tabla.columna_fecha),
        "filas": _filas(ruta, tabla.tabular),
        "horas_desde_carga": round(horas, 1),
        "motivo": motivo,
    }


def panel(rutas: dict, idioma: str = "es",
          ahora: datetime | None = None) -> dict:
    """El panel completo: una tarjeta por tabla, más el resumen.

    `rutas` es {id_tabla: ruta}. Las resuelve el backend, que es el único que
    sabe dónde viven los datos de cada empresa — este módulo no debe conocer
    la estructura de carpetas del tenant.
    """
    ahora = ahora or datetime.now()
    lang = normalizar(idioma)
    tarjetas = [estado_de(rutas.get(t.id, ""), t, ahora, lang) for t in TABLAS]
    atrasadas = [t for t in tarjetas if t["estado"] == ATRASADA]
    faltantes = [t for t in tarjetas if t["estado"] == SIN_DATOS]
    return {
        "generado": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "idioma": lang,
        "tablas": tarjetas,
        "resumen": {
            "total": len(tarjetas),
            "al_dia": len(tarjetas) - len(atrasadas) - len(faltantes),
            "atrasadas": len(atrasadas),
            "sin_datos": len(faltantes),
        },
        # El titular, ya redactado: es lo que se lee de un vistazo y lo que se
        # copia en un mail cuando algo está mal.
        "titular": _titular(atrasadas, faltantes, textos(lang)),
    }


def _titular(atrasadas: list, faltantes: list, txt: dict) -> str:
    plantillas = txt["titular"]
    if not atrasadas and not faltantes:
        return plantillas["todo_al_dia"]
    partes = []
    for clave, grupo in (("atrasadas", atrasadas), ("sin_cargar", faltantes)):
        if grupo:
            partes.append(plantillas[clave].format(
                n=len(grupo), nombres=", ".join(t["nombre"] for t in grupo)))
    return plantillas["separador"].join(partes)


def proxima_carga(tabla: Tabla, ultima: datetime) -> datetime | None:
    """Cuándo se espera la próxima. `None` para las manuales."""
    horas = PERIODOS_HORAS.get(tabla.frecuencia)
    return None if horas is None else ultima + timedelta(hours=horas)
