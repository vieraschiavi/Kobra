# © 2026 Martín Viera. Todos los derechos reservados.

"""El video de la suite: que exista, que esté subtitulado y que no se
desincronice.

El video es un screencast REAL (Playwright contra la app corriendo), y sus
subtítulos/narración viven en `marketing/subtitulos.py::SUITE_CUES`. Tres
cosas se pueden romper en silencio y acá se atan:

  * el video se regenera con otro recorrido y los subtítulos quedan viejos;
  * se agrega un idioma al producto y el video queda sin su pista;
  * la landing referencia archivos que nadie generó.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from marketing import subtitulos as ksub  # noqa: E402
from marketing.screencast_suite import RECORRIDO  # noqa: E402

VIDEO = os.path.join(ROOT, "landing", "video", "MVKobraAI_Suite_Demo.webm")


def test_el_video_existe_y_no_es_un_archivo_vacio():
    """Un <video> con src roto en la landing es un rectángulo negro con un
    error de consola — justo en la sección que dice 'grabado en vivo'."""
    assert os.path.exists(VIDEO), \
        "falta el video: python3 -m marketing.screencast_suite"
    mb = os.path.getsize(VIDEO) / 1e6
    assert mb > 0.5, f"el video pesa {mb:.2f} MB: quedó cortado o vacío"
    assert mb < 20, f"el video pesa {mb:.1f} MB: no entra bien en la landing"


@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_cada_idioma_tiene_su_pista_de_subtitulos(idioma):
    ruta = os.path.join(ROOT, "landing", "video", f"suite.{idioma}.vtt")
    assert os.path.exists(ruta), \
        f"falta suite.{idioma}.vtt: python3 -m marketing.subtitulos"
    contenido = open(ruta, encoding="utf-8").read()
    assert contenido.startswith("WEBVTT")
    assert contenido.count("-->") == len(ksub.SUITE_CUES)


def test_los_cues_cubren_el_recorrido_del_screencast():
    """Si el recorrido crece y los subtítulos no, el final del video queda
    mudo; si los subtítulos sobran, hablan de una pantalla que no está."""
    duracion_recorrido = sum(seg for _, seg in RECORRIDO)
    fin_ultimo_cue = ksub.SUITE_CUES[-1][1]
    # El video real suma ~1 s de navegación por pantalla: los subtítulos
    # tienen que llegar al menos hasta el fin del recorrido declarado.
    assert fin_ultimo_cue >= duracion_recorrido, (
        f"los subtítulos terminan en {fin_ultimo_cue}s y el recorrido dura "
        f"{duracion_recorrido}s: el final del video queda sin texto")


def test_los_cues_no_se_pisan_ni_van_hacia_atras():
    fin_anterior = 0.0
    for ini, fin, _ in ksub.SUITE_CUES:
        assert ini >= fin_anterior, f"el cue que arranca en {ini}s pisa al anterior"
        assert fin > ini
        fin_anterior = fin


def test_cada_cue_esta_en_los_tres_idiomas():
    for n, (_i, _f, textos) in enumerate(ksub.SUITE_CUES):
        faltan = set(ksub.IDIOMAS) - set(textos)
        assert not faltan, f"al cue {n} le faltan idiomas: {sorted(faltan)}"


def test_la_landing_referencia_el_video_y_sus_pistas():
    html = open(os.path.join(ROOT, "landing", "index.html"), encoding="utf-8").read()
    assert "MVKobraAI_Suite_Demo.webm" in html
    for idioma in ksub.IDIOMAS:
        assert f"suite.{idioma}.vtt" in html, \
            f"la landing no ofrece los subtítulos en {idioma}"


def test_el_recorrido_muestra_todos_los_modulos_nuevos():
    """El video existe para mostrar la suite: si un módulo se cae del
    recorrido, se anuncia algo que el video no muestra."""
    rutas = {r for r, _ in RECORRIDO}
    for pantalla in ("/tablero", "/gobernanza", "/medidas", "/automl",
                     "/logistica", "/proyectos"):
        assert pantalla in rutas, f"el recorrido no pasa por {pantalla}"


def test_la_narracion_nombra_lo_que_se_ve():
    """Subtítulo y pantalla tienen que hablar de lo mismo: la narración en
    castellano tiene que nombrar cada módulo del recorrido."""
    texto = " ".join(t["es"].lower() for _, _, t in ksub.SUITE_CUES)
    for palabra in ("tablero", "gobernanza", "medidas", "automl",
                    "logística", "proyectos"):
        assert palabra in texto, f"la narración no menciona {palabra!r}"


def test_el_guion_de_la_voz_es_el_mismo_de_los_subtitulos():
    """marketing/voz_suite.py lee SUITE_CUES: si alguien copiara el guion a
    otro lado, narración y subtítulo podrían separarse. Este test documenta
    esa decisión verificando que voz_suite no tenga textos propios."""
    import ast
    fuente = open(os.path.join(ROOT, "marketing", "voz_suite.py"),
                  encoding="utf-8").read()
    assert "SUITE_CUES" in fuente
    # Ningún string largo con pinta de guion adentro de voz_suite. Se analiza
    # el AST y no el texto: una regex sobre el fuente confunde el docstring
    # (que legítimamente es largo) con un guion.
    arbol = ast.parse(fuente)
    docstrings = {ast.get_docstring(n, clean=False)
                  for n in ast.walk(arbol)
                  if isinstance(n, (ast.Module, ast.FunctionDef))}
    largos = [n.value for n in ast.walk(arbol)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and len(n.value) >= 80 and n.value not in docstrings]
    assert not largos, \
        "voz_suite.py tiene textos largos propios: el guion vive en subtitulos.py"
