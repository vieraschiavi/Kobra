# © 2026 Martín Viera. Todos los derechos reservados.

"""Un export que falla no puede descargarse igual.

Los cuatro botones de exportar de la webapp —cartera, agenda, calidad, informe
ejecutivo— hacían `await r.blob()` sin mirar `r.ok`. Cuando el backend contesta
un error, el cuerpo es un JSON de tres líneas… y ese JSON se descargaba igual,
con nombre `MVKobraAI_Promesas_Vencidas.xlsx`.

O sea: sesión vencida, plan sin la feature, cupo agotado o un 500 armando el
Excel, y el cliente terminaba con un archivo que Excel no abre y **ningún
mensaje**. Es la peor forma de fallar porque parece que anduvo: el usuario
piensa que el archivo está corrupto, o que el producto no sirve, y en el mejor
de los casos abre un ticket que nadie puede reproducir.

`descargar()` en `api.js` mira la respuesta primero, lee el mensaje del error
antes de tirarlo —si no, el texto que el backend se tomó el trabajo de escribir
se pierde— y avisa del plan igual que `api()`.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINAS = {
    "Cartera.jsx": "cartera_priorizada.csv",
    "Agenda.jsx": "MVKobraAI_Promesas_Vencidas.xlsx",
    "Calidad.jsx": "MVKobraAI_Calidad.xlsx",
    "Dashboard.jsx": "informe_ejecutivo.pdf",
}


def fuente(rel):
    with open(os.path.join(ROOT, "webapp", "frontend", "src", rel),
              encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("pagina,archivo", sorted(PAGINAS.items()))
def test_ningun_export_arma_el_blob_a_mano(pagina, archivo):
    """La firma del defecto: `await r.blob()` suelto en la página. Si el
    export pasa por `descargar()`, la comprobación de `r.ok` está garantizada
    en un solo lugar y no hay cuatro copias que puedan divergir."""
    src = fuente(f"pages/{pagina}")
    assert ".blob()" not in src, (
        f"{pagina} vuelve a armar la descarga a mano: si el backend contesta "
        "un error, ese error se descarga como si fuera el archivo")
    assert "descargar(" in src, f"{pagina} no usa el helper de descarga"
    assert archivo in src, f"{pagina} dejó de nombrar el archivo {archivo}"


@pytest.mark.parametrize("pagina", sorted(PAGINAS))
def test_el_error_se_le_muestra_al_usuario(pagina):
    """Que `descargar()` tire una excepción no alcanza: si nadie la agarra, el
    botón sigue pareciendo que no hizo nada."""
    src = fuente(f"pages/{pagina}")
    bloque = re.search(r"descargar\([^)]*\)[\s\S]{0,240}", src)
    assert bloque, f"{pagina}: no se encontró la llamada a descargar()"
    assert "catch" in bloque.group(0), (
        f"{pagina} llama a descargar() sin catch: el fallo queda en la consola "
        "del navegador y el usuario no se entera")


def test_descargar_mira_la_respuesta_antes_de_tocar_el_cuerpo():
    src = fuente("api.js")
    assert "export async function descargar(" in src, "no existe el helper"
    cuerpo = src[src.index("export async function descargar("):]
    cuerpo = cuerpo[:cuerpo.index("\n}\n") + 3]

    assert "if (!r.ok)" in cuerpo, "no mira r.ok"
    # El `r.ok` tiene que ir ANTES del blob, no después.
    assert cuerpo.index("if (!r.ok)") < cuerpo.index("r.blob()"), (
        "arma el blob antes de mirar si la respuesta era un error")
    # El mensaje del backend se lee del cuerpo: un archivo no tiene 'detail'
    # en una cabecera, y sin esto el usuario ve solo un número de estado.
    assert "detail" in cuerpo, "descarta el mensaje que escribió el backend"
    # 401 se trata como en `api()`: se limpia la sesión y se manda al login.
    assert "401" in cuerpo and "setSesion(null)" in cuerpo, (
        "con la sesión vencida deja al usuario reintentando para siempre")
    # Y el chip del plan se entera igual que en `api()`.
    assert "avisarPlan" in cuerpo, (
        "un 402 por cupo agotado no refresca el estado del plan")
