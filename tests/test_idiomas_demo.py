"""Tests del idioma de las piezas con voz e imagen.

Bug reportado: eligiendo portugués o inglés en el sitio, **el audio y el video
seguían en castellano**. Eran dos huecos distintos:

* El demo (`dashboard_estatico/`) no tenía idioma en absoluto — ni guion, ni
  etiquetas, ni MP3: todo estaba escrito a mano en castellano.
* El video de la landing está narrado en castellano y no tenía subtítulos, así
  que quien no habla español no entendía la pieza principal de la página.
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data import generar_audio_demo_voz as gav  # noqa: E402
from marketing import subtitulos as S  # noqa: E402

DEMO = os.path.join(ROOT, "dashboard_estatico")
LANDING = os.path.join(ROOT, "landing", "index.html")


def _leer(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as f:
        return f.read()


# --- guiones del demo ------------------------------------------------------
def test_guiones_js_es_parseable_por_el_navegador_y_por_python():
    """El mismo archivo lo consumen los dos: el navegador como <script> y el
    generador de audio como datos. Si se desincronizan, el texto en pantalla
    deja de coincidir con la voz."""
    js = _leer(DEMO, "guiones.js")
    assert js.lstrip().startswith("// ")
    assert re.search(r"^window\.GUIONES\s*=\s*\{", js, re.M)
    assert re.search(r"^window\.IDIOMA_DEMO\s*=", js, re.M)
    # Y el bloque de datos tiene que ser JSON estricto.
    m = re.search(r"^window\.GUIONES\s*=\s*(\{.*?^\});", js, re.S | re.M)
    assert m and set(json.loads(m.group(1))) == set(gav.IDIOMAS)


def test_el_demo_no_tiene_los_guiones_escritos_a_mano():
    """Regresión: estaban embebidos en index.html solo en castellano."""
    html = _leer(DEMO, "index.html")
    assert "var CALL_SCRIPT=[" not in html
    assert "var WSP_SCRIPT=[" not in html
    assert "_G.llamada" in html and "_G.whatsapp" in html


def test_el_demo_resuelve_el_idioma_con_prioridad_util():
    """?lang= primero (única vía que funciona en el paquete offline, donde no
    hay localStorage compartido con el sitio), después lo elegido en la
    landing, después el navegador, y castellano como piso."""
    js = _leer(DEMO, "guiones.js")
    orden = [js.index("searchParams" if "searchParams" in js else "URLSearchParams"),
             js.index("kobra_lang"),
             js.index("navigator")]
    assert orden == sorted(orden), "cambió el orden de prioridad del idioma"
    assert "return url || guardado || navegador || 'es';" in js


def test_las_etiquetas_de_la_llamada_salen_del_guion():
    """Antes estaban escritas en el HTML: la llamada hablaba en inglés pero
    las burbujas seguían diciendo 'Cliente'."""
    html = _leer(DEMO, "index.html")
    for clave in ("etiqueta_ia", "etiqueta_cliente", "finalizada", "detenida"):
        assert f"TXT.{clave}" in html, clave


def test_la_voz_del_navegador_tambien_respeta_el_idioma():
    """El fallback sin MP3 buscaba siempre una voz castellana, así que leía el
    texto traducido con fonética española."""
    html = _leer(DEMO, "index.html")
    assert "new RegExp('^'+IDIOMA" in html
    assert "pt-BR" in html and "en-US" in html


def test_hay_selector_de_idioma_en_el_demo():
    """El demo se distribuye suelto en el paquete offline, donde no hay
    landing de la que heredar el idioma."""
    html = _leer(DEMO, "index.html")
    assert 'id="langSel"' in html and ".langsel{" in html


def test_la_landing_lleva_el_idioma_al_demo():
    html = _leer(LANDING)
    assert "'/demo/?lang=' + lang" in html


# --- subtítulos del video --------------------------------------------------
@pytest.mark.parametrize("idioma", S.IDIOMAS)
def test_existe_la_pista_de_subtitulos(idioma):
    ruta = os.path.join(S.VIDEO_DIR, f"copiloto.{idioma}.vtt")
    assert os.path.exists(ruta), f"falta {os.path.basename(ruta)}"
    texto = _leer(ruta)
    assert texto.startswith("WEBVTT")
    assert texto.count("-->") == len(S.CUES)


def test_los_tiempos_avanzan_y_no_se_pisan():
    """Un cue que empieza antes de que termine el anterior hace parpadear los
    subtítulos; uno invertido directamente no se muestra."""
    anterior = 0.0
    for ini, fin, _ in S.CUES:
        assert ini < fin, f"cue invertido en {ini}"
        assert ini >= anterior - 1e-6, f"cue solapado en {ini}"
        anterior = fin


def test_el_formato_de_tiempo_es_el_que_exige_webvtt():
    assert S._marca(0) == "00:00:00.000"
    assert S._marca(63.86) == "00:01:03.860"
    assert S._marca(3661.5) == "01:01:01.500"
    # WebVTT usa punto decimal en los tiempos; con coma (que es lo que usa el
    # formato SRT) el navegador descarta la pista entera y no muestra ningún
    # subtítulo. Se miran solo las líneas de tiempo: en el texto las comas son
    # puntuación normal.
    tiempos = [ln for ln in S.vtt("es").splitlines() if "-->" in ln]
    assert len(tiempos) == len(S.CUES)
    for ln in tiempos:
        assert "," not in ln, ln
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}",
                            ln), ln


def test_ningun_idioma_quedo_sin_traducir():
    for idioma in S.IDIOMAS:
        faltan = [i for i, c in enumerate(S.CUES) if not c[2].get(idioma, "").strip()]
        assert not faltan, f"{idioma}: cues vacíos {faltan}"
    # Y que no sea el castellano copiado en las tres.
    junto = {i: " ".join(c[2][i] for c in S.CUES) for i in S.IDIOMAS}
    assert len(set(junto.values())) == 3


def test_el_nombre_del_producto_esta_bien_escrito():
    """La transcripción automática escribía 'cobra' en vez de 'Kobra'. Si el
    texto se regenera sin corregir, la marca sale mal en pantalla."""
    for idioma in S.IDIOMAS:
        texto = S.vtt(idioma)
        assert "MV Kobra AI" in texto
        assert not re.search(r"\bcobra\b", texto, re.I) or "Kobra" in texto


def test_el_video_de_la_landing_ofrece_las_tres_pistas():
    html = _leer(LANDING)
    for idioma in S.IDIOMAS:
        assert f'src="/video/copiloto.{idioma}.vtt" srclang="{idioma}"' in html
    # Y cambiar de idioma tiene que cambiar la pista activa.
    assert "video track" in html and "t.track.mode" in html
