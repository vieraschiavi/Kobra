# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Memoria técnica del pipeline
===========================================
Qué hace el programa, en orden, contado dos veces: una para quien va a leer el
código y otra para quien va a firmar la compra. En castellano, inglés y
portugués.

Por qué dos registros y no un resumen
--------------------------------------
Un solo texto no sirve a los dos lectores. El técnico necesita saber qué
modelo, con qué validación y qué pasa si falla; el gerente necesita saber qué
problema resuelve y qué cambia en su operación. Escribir "en el medio" produce
un documento que no le alcanza a ninguno: al programador le falta precisión y
al gerente le sobra jerga.

Por qué la estructura va separada de los textos
------------------------------------------------
`memoria/estructura.json` tiene lo que NO se traduce —el orden, el id, los
módulos donde vive cada etapa, las etiquetas— y `memoria/<idioma>.json` solo
la prosa. Un catálogo completo por idioma se separa solo: alcanza con que
alguien agregue una etapa en castellano y se olvide del inglés para que las
dos versiones dejen de describir el mismo programa, y nadie se entera hasta
que un cliente compara los dos PDF.

Con la estructura única eso no puede pasar: las etapas, su orden y sus módulos
son los mismos en los tres idiomas por construcción, y
`tests/test_memoria_tecnica.py` falla si a un idioma le falta un texto.

Por qué es DATO y no un .md suelto
-----------------------------------
Un documento en Markdown se desactualiza en silencio: el código cambia, nadie
lo lee, y a los seis meses describe un programa que ya no existe. Acá cada
etapa nombra los módulos reales que la implementan, y los tests fallan si
alguno deja de existir. No garantiza que el texto sea verdad —eso no lo puede
verificar una máquina— pero sí que no quede describiendo módulos borrados.

El orden es el del pipeline real (`kobra/pipeline.py` y lo que la app llama
después), no un orden temático: la pregunta que este documento contesta es
"¿qué le pasa a un dato desde que entra hasta que sale?".
"""
from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, field

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria")

IDIOMAS = ("es", "en", "pt")
IDIOMA_POR_DEFECTO = "es"

# Los campos que se traducen y los que no. La lista está acá y no repartida
# por el archivo porque es lo que los tests recorren para comprobar que a
# ningún idioma le falte nada.
CAMPOS_TEXTO = ("titulo", "tecnico", "criollo", "por_que", "repercusion",
                "limites", "entradas", "salidas")


@dataclass(frozen=True)
class Etapa:
    """Una etapa del pipeline, contada para los dos lectores.

    `frozen=True`: el catálogo se lee desde la API, los exports y los tests a
    la vez. Que nadie pueda mutarlo al pasar evita que un export salga distinto
    de la pantalla que lo generó.
    """
    orden: int
    id: str
    titulo: str
    # Para quien lee el código: qué hace, con qué, y qué pasa si falla.
    tecnico: str
    # Para quien firma la compra: qué problema resuelve, en castellano llano.
    criollo: str
    # Por qué existe. Casi siempre: qué se rompía antes.
    por_que: str
    # Qué cambia aguas abajo. Es lo que convierte una lista en un pipeline.
    repercusion: str
    modulos: tuple[str, ...]
    entradas: str
    salidas: str
    # Lo que esta etapa NO hace. Un documento de venta que solo suma es
    # publicidad; los límites son lo que lo vuelve creíble en una auditoría.
    limites: str = ""
    etiquetas: tuple[str, ...] = field(default_factory=tuple)


def _leer(nombre: str):
    with open(os.path.join(_DIR, f"{nombre}.json"), encoding="utf-8") as f:
        return json.load(f)


def normalizar(idioma: str | None) -> str:
    """`pt-BR` → `pt`, `None` o un idioma que no existe → castellano.

    La cabecera `Accept-Language` llega con formas como `pt-BR` o `en-US`, y
    el catálogo se indexa por las dos letras.
    """
    if not idioma:
        return IDIOMA_POR_DEFECTO
    corto = str(idioma).strip().lower().replace("_", "-").split("-")[0]
    return corto if corto in IDIOMAS else IDIOMA_POR_DEFECTO


@functools.lru_cache(maxsize=len(IDIOMAS))
def etapas(idioma: str = IDIOMA_POR_DEFECTO) -> tuple[Etapa, ...]:
    """El catálogo completo en un idioma, en orden de pipeline.

    Cacheado: la pantalla lo pide en cada carga y son tres archivos que no
    cambian mientras el proceso vive.

    Un texto que falte cae al castellano en vez de romper la pantalla. Los
    tests garantizan que eso no pase en producción; el fallback existe para
    que un JSON a medio editar no deje la aplicación sin la pestaña.
    """
    idioma = normalizar(idioma)
    textos = _leer(idioma)
    respaldo = _leer(IDIOMA_POR_DEFECTO) if idioma != IDIOMA_POR_DEFECTO else textos
    salida = []
    for e in _leer("estructura"):
        t = textos.get(e["id"], {})
        r = respaldo.get(e["id"], {})
        salida.append(Etapa(
            orden=e["orden"], id=e["id"],
            modulos=tuple(e["modulos"]), etiquetas=tuple(e.get("etiquetas", ())),
            **{c: (t.get(c) or r.get(c) or "") for c in CAMPOS_TEXTO}))
    return tuple(salida)


def por_id(id_etapa: str, idioma: str = IDIOMA_POR_DEFECTO) -> Etapa | None:
    return next((e for e in etapas(idioma) if e.id == id_etapa), None)


def como_dicts(idioma: str = IDIOMA_POR_DEFECTO) -> list[dict]:
    """Para la API y el frontend. `dataclasses.asdict` convierte las tuplas en
    listas, que es lo que espera JSON."""
    from dataclasses import asdict
    return [asdict(e) for e in etapas(idioma)]


def etiquetas_disponibles() -> list[str]:
    """Las etiquetas usadas, ordenadas — la pantalla filtra por acá. No se
    traducen: son claves, no texto de pantalla."""
    return sorted({t for e in etapas() for t in e.etiquetas})


def textos_crudos(idioma: str) -> dict:
    """El JSON de un idioma tal cual está en disco.

    Lo usan los tests para comprobar que no falte ningún texto SIN que el
    fallback al castellano tape el agujero: `etapas()` completa los huecos a
    propósito, y eso haría pasar un test que debería fallar.
    """
    return _leer(normalizar(idioma))
