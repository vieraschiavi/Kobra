# © 2026 Martín Viera. Todos los derechos reservados.

"""La película de la landing: la demo completa, de la mora al recupero.

El guion vive en `marketing/subtitulos.py::PELICULA_ESCENAS` y de ahí salen
las tres cosas a la vez —el recorrido de la grabación, los subtítulos y la
narración—, así que lo que puede romperse en silencio es distinto que en la
suite: que una escena pierda un idioma, que el recorrido deje afuera un módulo
que la sección promete mostrar, que los archivos publicados (video y .vtt) no
existan o no coincidan con el guion, o que la landing anuncie la película y no
la referencie.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from marketing import subtitulos as ksub  # noqa: E402
from marketing.pelicula_demo import ESCENARIO, RECORRIDO  # noqa: E402

VIDEO = os.path.join(ROOT, "landing", "video", "MVKobraAI_Pelicula_Demo.webm")
LANDING = os.path.join(ROOT, "landing", "index.html")


# --- El guion --------------------------------------------------------------
def test_cada_escena_esta_en_los_tres_idiomas():
    for n, (_ruta, _seg, textos) in enumerate(ksub.PELICULA_ESCENAS):
        faltan = set(ksub.IDIOMAS) - set(textos)
        assert not faltan, f"a la escena {n} le faltan idiomas: {sorted(faltan)}"


def test_el_recorrido_sale_del_guion():
    """Recorrido y cues son la misma lista: si alguien los separa, la
    grabación y los subtítulos pueden volver a desincronizarse."""
    assert RECORRIDO == [(r, s) for r, s, _ in ksub.PELICULA_ESCENAS]
    assert len(ksub.PELICULA_CUES) == len(ksub.PELICULA_ESCENAS)


def test_los_cues_acumulan_las_duraciones_sin_pisarse():
    t = 0.0
    for (ruta, seg, _), (ini, fin, _t) in zip(ksub.PELICULA_ESCENAS,
                                              ksub.PELICULA_CUES):
        assert ini == pytest.approx(t), f"{ruta}: cue arranca en {ini}, no {t}"
        assert fin == pytest.approx(t + seg)
        t += seg


def test_la_historia_empieza_en_el_problema_y_termina_en_el_resultado():
    """El arco que pide la pieza: arrancar en la situación actual (la mora en
    el panel general) y cerrar en /roi, que es el argumento para un gerente."""
    assert RECORRIDO[0][0] == "/"
    assert RECORRIDO[-1][0] == "/roi"
    texto_apertura = ksub.PELICULA_ESCENAS[0][2]["es"].lower()
    assert "mora" in texto_apertura


def test_la_pelicula_recorre_todos_los_modulos():
    """La sección de la landing promete "todos los módulos": si una pantalla
    se cae del recorrido, se anuncia algo que el video no muestra."""
    rutas = {r for r, _ in RECORRIDO}
    for pantalla in ("/", "/cuentas-por-cobrar", "/originacion", "/cartera",
                     "/agenda", "/demo-vivo", "/portal-cobros", "/tablero",
                     "/asistente", "/gestores", "/calidad",
                     "/ingenieria-datos", "/gobernanza", "/medidas",
                     "/automl", "/logistica", "/proyectos", "/roi"):
        assert pantalla in rutas, f"la película no pasa por {pantalla}"


def test_la_narracion_nombra_lo_que_se_ve():
    """Como en la suite: nombre COMERCIAL, no slug — el módulo de /medidas se
    vende como "KPIs propios"."""
    texto = " ".join(t["es"].lower() for _r, _s, t in ksub.PELICULA_ESCENAS)
    for palabra in ("mora", "probpago", "whatsapp", "portal", "tablero",
                    "gobernanza", "kpi", "automl", "logística", "proyectos",
                    "ingeniería de datos"):
        assert palabra in texto, f"la narración no menciona {palabra!r}"


def test_los_datos_de_la_pelicula_son_un_escenario_de_demo():
    """La película se graba sobre un escenario de `kobra/demo_escenarios.py`:
    la misma empresa sintética, completa y verificada, que un prospecto activa
    desde Configuración — no un CSV armado a mano para el video."""
    from kobra import demo_escenarios
    assert ESCENARIO in demo_escenarios.ESCENARIOS


# --- Los archivos publicados ----------------------------------------------
def test_el_video_existe_y_tiene_el_peso_de_una_pelicula():
    assert os.path.exists(VIDEO), \
        "falta la película: python3 -m marketing.pelicula_demo"
    mb = os.path.getsize(VIDEO) / 1e6
    assert mb > 1.5, f"la película pesa {mb:.2f} MB: quedó cortada o vacía"
    assert mb < 30, f"la película pesa {mb:.1f} MB: no entra bien en la landing"


@pytest.mark.parametrize("idioma", ksub.IDIOMAS)
def test_cada_idioma_tiene_su_pista_de_subtitulos(idioma):
    ruta = os.path.join(ROOT, "landing", "video", f"pelicula.{idioma}.vtt")
    assert os.path.exists(ruta), \
        f"falta pelicula.{idioma}.vtt: python3 -m marketing.subtitulos"
    contenido = open(ruta, encoding="utf-8").read()
    assert contenido.startswith("WEBVTT")
    assert contenido.count("-->") == len(ksub.PELICULA_CUES)


# --- La landing ------------------------------------------------------------
def test_la_landing_referencia_el_video_y_sus_pistas():
    html = open(LANDING, encoding="utf-8").read()
    assert "MVKobraAI_Pelicula_Demo.webm" in html
    assert 'id="pelicula"' in html
    for idioma in ksub.IDIOMAS:
        assert f"pelicula.{idioma}.vtt" in html, \
            f"la landing no ofrece los subtítulos en {idioma}"


def test_los_subtitulos_no_se_prenden_solos():
    """Misma decisión que los otros videos: los subtítulos son opcionales
    (botón CC), no tapan la pantalla por defecto."""
    import re
    html = open(LANDING, encoding="utf-8").read()
    bloque = html.split('id="pelicula"')[1].split("</section>")[0]
    # Se mira el atributo dentro de cada <track>, no la palabra suelta: el
    # comentario del propio HTML la usa para explicar la decisión.
    for track in re.findall(r"<track[^>]*>", bloque):
        assert " default" not in track, \
            f"una pista de la película trae `default`: se enciende sola ({track})"


def test_la_pelicula_esta_en_el_menu():
    """El pedido incluía la entrada de menú — y en los tres idiomas."""
    html = open(LANDING, encoding="utf-8").read()
    assert 'href="#pelicula" data-i="navp"' in html
    # Las claves de la sección y del menú tienen que estar en los dos
    # diccionarios de traducción (el castellano es el propio HTML).
    pt = html.split("pt:{")[1].split("en:{")[0]
    en = html.split("en:{")[1]
    for clave in ("navp", "pfey", "pfh", "pfl"):
        assert f"{clave}:" in pt, f"falta {clave!r} en el diccionario pt"
        assert f"{clave}:" in en, f"falta {clave!r} en el diccionario en"


def test_las_variantes_de_idioma_estan_regeneradas():
    """`landing/pt|en/index.html` son builds del maestro: si el maestro suma
    la película y las variantes no, el visitante de /en/ no la ve."""
    for lang in ("pt", "en"):
        variante = open(os.path.join(ROOT, "landing", lang, "index.html"),
                        encoding="utf-8").read()
        assert 'id="pelicula"' in variante, (
            f"landing/{lang}/ no tiene la película: "
            "python3 -m marketing.generar_paginas_idioma")
