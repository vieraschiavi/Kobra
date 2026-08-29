# © 2026 Martín Viera. Todos los derechos reservados.

"""La película de la landing: una por idioma, con el programa y la voz en ese
idioma.

La primera versión era un video en castellano con tres pistas de subtítulos.
No alcanzaba: quien elige portugués o inglés en la web ve el menú traducido y
después una película donde el programa habla en castellano. Ahora se graba una
por idioma —interfaz en ese idioma, narración con una voz de ese idioma— y la
landing sirve la que corresponde.

Lo que se ata acá:

  * el guion existe en los tres idiomas y no declara duraciones (las decide la
    narración medida — ver `marketing/pelicula_demo.py`);
  * los tres videos y sus subtítulos están publicados;
  * los subtítulos NO dejan silencios largos: el "lag" que se escuchaba era
    justamente eso, y se mide sobre el archivo publicado, no sobre la promesa;
  * la landing sirve el video del idioma elegido.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from marketing import subtitulos as ksub  # noqa: E402
from marketing.pelicula_demo import (  # noqa: E402
    ESCENARIO,
    INTERACCIONES,
    RECORRIDO,
    frases_de,
    salida_de,
    subtitulo_de,
)

LANDING = os.path.join(ROOT, "landing", "index.html")
# Silencio máximo tolerable entre dos frases. El video anterior llegó a 5,37 s
# medidos y se escuchaba como que la película se colgaba.
SILENCIO_MAX_S = 3.0


def _cues(idioma):
    """(inicio, fin, texto) de una pista publicada."""
    texto = open(subtitulo_de(idioma), encoding="utf-8").read()
    salida = []
    for bloque in texto.split("\n\n"):
        m = re.search(r"(\d+):(\d+):(\d+)\.(\d+) --> (\d+):(\d+):(\d+)\.(\d+)", bloque)
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
        cuerpo = bloque.split("\n", 2)[-1].strip()
        salida.append((h1 * 3600 + m1 * 60 + s1 + ms1 / 1000,
                       h2 * 3600 + m2 * 60 + s2 + ms2 / 1000, cuerpo))
    return salida


# --- El guion --------------------------------------------------------------
def test_cada_escena_esta_en_los_tres_idiomas():
    for n, (ruta, textos) in enumerate(ksub.PELICULA_ESCENAS):
        for idioma in ksub.IDIOMAS:
            frases = frases_de(textos, idioma)
            assert frases and all(f.strip() for f in frases), \
                f"escena {n} ({ruta}) sin texto en {idioma}"


def test_el_guion_no_declara_duraciones():
    """Cuánto dura cada pantalla lo decide la narración medida de cada idioma.
    Si volviera a declararse acá, el mismo número tendría que servir para tres
    idiomas que hablan a ritmos distintos — y no sirve."""
    for escena in ksub.PELICULA_ESCENAS:
        assert len(escena) == 2, f"la escena {escena[0]} volvió a traer duración"


def test_la_historia_empieza_en_el_problema_y_termina_en_el_resultado():
    assert RECORRIDO[0] == "/"
    assert RECORRIDO[-1] == "/roi"
    assert "mora" in frases_de(ksub.PELICULA_ESCENAS[0][1], "es")[0].lower()


def test_la_pelicula_recorre_todos_los_modulos():
    for pantalla in ("/", "/cuentas-por-cobrar", "/originacion", "/cartera",
                     "/agenda", "/demo-vivo", "/portal-cobros", "/tablero",
                     "/asistente", "/gestores", "/calidad",
                     "/ingenieria-datos", "/gobernanza", "/medidas",
                     "/automl", "/logistica", "/proyectos", "/roi"):
        assert pantalla in RECORRIDO, f"la película no pasa por {pantalla}"


def test_las_escenas_con_accion_llevan_dos_frases():
    """Donde el producto TRABAJA en cámara (subir un archivo, entrenar, cobrar)
    la acción tarda lo suyo: con una sola frase quedaban seis segundos de
    silencio mirando a la máquina pensar."""
    for ruta in INTERACCIONES:
        escena = next(t for r, t in ksub.PELICULA_ESCENAS if r == ruta)
        for idioma in ksub.IDIOMAS:
            assert len(frases_de(escena, idioma)) >= 2, \
                f"{ruta} en {idioma} tiene una sola frase para toda la acción"


def test_la_narracion_nombra_lo_que_se_ve():
    texto = " ".join(f.lower() for _r, t in ksub.PELICULA_ESCENAS
                     for f in frases_de(t, "es"))
    for palabra in ("mora", "probpago", "whatsapp", "portal", "tablero",
                    "gobernanza", "kpi", "automl", "logística", "proyectos",
                    "ingeniería de datos"):
        assert palabra in texto, f"la narración no menciona {palabra!r}"


def test_los_datos_de_la_pelicula_son_un_escenario_de_demo():
    from kobra import demo_escenarios
    assert ESCENARIO in demo_escenarios.ESCENARIOS


# --- Los archivos publicados ----------------------------------------------
@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_hay_una_pelicula_por_idioma(idioma):
    ruta = salida_de(idioma)
    assert os.path.exists(ruta), (
        f"falta la película en {idioma}: "
        f"python3 -m marketing.pelicula_demo --idioma {idioma}")
    mb = os.path.getsize(ruta) / 1e6
    assert mb > 1.5, f"la película en {idioma} pesa {mb:.2f} MB: quedó cortada"
    assert mb < 30, f"la película en {idioma} pesa {mb:.1f} MB: no entra bien"


@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_cada_pelicula_trae_sus_subtitulos(idioma):
    ruta = subtitulo_de(idioma)
    assert os.path.exists(ruta), f"falta pelicula.{idioma}.vtt"
    assert open(ruta, encoding="utf-8").read().startswith("WEBVTT")
    cues = _cues(idioma)
    esperadas = sum(len(frases_de(t, idioma)) for _r, t in ksub.PELICULA_ESCENAS)
    assert len(cues) == esperadas, (
        f"{idioma}: {len(cues)} subtítulos para {esperadas} frases del guion")


@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_los_subtitulos_van_en_orden_y_sin_pisarse(idioma):
    fin_anterior = 0.0
    for ini, fin, _txt in _cues(idioma):
        assert ini >= fin_anterior - 0.01, f"{idioma}: el cue de {ini}s pisa al anterior"
        assert fin > ini
        fin_anterior = fin


@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_la_pelicula_no_tiene_silencios_largos(idioma):
    """El control del "lag": entre que termina una frase y arranca la
    siguiente no puede haber un pozo. Se mide sobre la pista PUBLICADA, que
    es lo que escucha el que mira el video."""
    cues = _cues(idioma)
    huecos = [round(cues[i + 1][0] - cues[i][1], 2) for i in range(len(cues) - 1)]
    peor = max(huecos)
    assert peor <= SILENCIO_MAX_S, (
        f"{idioma}: {peor}s de silencio entre dos frases (tope {SILENCIO_MAX_S}s). "
        f"Huecos: {huecos}")


@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_los_subtitulos_dicen_lo_que_dice_el_guion(idioma):
    """La pista publicada tiene que ser el texto del guion en ESE idioma — no
    el de otro idioma ni una versión vieja."""
    delguion = [f for _r, t in ksub.PELICULA_ESCENAS for f in frases_de(t, idioma)]
    publicados = [c[2].replace("\n", " ") for c in _cues(idioma)]
    assert [f.replace("\n", " ") for f in delguion] == publicados


# --- La landing ------------------------------------------------------------
def test_la_landing_sirve_la_pelicula_del_idioma():
    html = open(LANDING, encoding="utf-8").read()
    assert 'id="pelicula"' in html
    bloque = html.split('id="pelicula"')[1].split("</section>")[0]
    assert "data-pelicula" in bloque, \
        "el <video> de la película no está marcado: setLang no lo encuentra"
    assert "MVKobraAI_Pelicula_Demo.es.webm" in bloque
    # Y el JS tiene que cambiar el archivo al cambiar de idioma.
    assert "MVKobraAI_Pelicula_Demo.' + lang + '.webm" in html, \
        "cambiar de idioma no cambia la película"
    assert "pelicula.' + lang + '.vtt" in html


def test_los_subtitulos_no_se_prenden_solos():
    html = open(LANDING, encoding="utf-8").read()
    bloque = html.split('id="pelicula"')[1].split("</section>")[0]
    for track in re.findall(r"<track[^>]*>", bloque):
        assert " default" not in track, \
            f"una pista de la película trae `default`: se enciende sola ({track})"


def test_la_pelicula_esta_en_el_menu():
    html = open(LANDING, encoding="utf-8").read()
    assert 'href="#pelicula" data-i="navp"' in html
    pt = html.split("pt:{")[1].split("en:{")[0]
    en = html.split("en:{")[1]
    for clave in ("navp", "pfey", "pfh", "pfl"):
        assert f"{clave}:" in pt, f"falta {clave!r} en el diccionario pt"
        assert f"{clave}:" in en, f"falta {clave!r} en el diccionario en"


def test_las_variantes_de_idioma_estan_regeneradas():
    for lang in ("pt", "en"):
        variante = open(os.path.join(ROOT, "landing", lang, "index.html"),
                        encoding="utf-8").read()
        assert 'id="pelicula"' in variante, (
            f"landing/{lang}/ no tiene la película: "
            "python3 -m marketing.generar_paginas_idioma")
        assert "data-pelicula" in variante
