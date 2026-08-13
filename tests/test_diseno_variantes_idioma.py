# © 2026 Martín Viera. Todos los derechos reservados.

"""Eje DISEÑO: los mismos meta tags en TODAS las variantes de idioma.

`?lang=en` traducía el contenido visible pero nunca tocaba el `<head>`:
`description`, `canonical`, `og:*`, `twitter:*` quedaban siempre en español.
Medido antes de arreglarlo — abrir `/?lang=en` y `/demo/?lang=en` con un
scraper que no ejecuta JavaScript (que es exactamente cómo Facebook/LinkedIn/
X arman el preview de un link):

    og:locale         es_UY   (los tres idiomas)
    og:title          "MV Kobra AI · Cobranzas Inteligentes"   (los tres)
    canonical         https://mvkobranzaia.com/   (los tres, con o sin ?lang=)

`marketing/generar_paginas_idioma.py` genera `/en/`, `/pt/`, `/demo/en/` y
`/demo/pt/` como URLs PROPIAS, con el `<head>` traducido — mismo body/JS que
el maestro (la demo, además, con las rutas relativas absolutizadas contra
`/demo/`, porque el maestro las necesita relativas para el paquete offline).

Estos tests verifican dos cosas: que los archivos generados coincidan con lo
que el generador produciría HOY (no queden desactualizados si se edita el
maestro y nadie vuelve a correr el generador), y que el `<head>` de cada
variante tenga sentido — idioma, locale y URL canónica correctos, y las
cuatro páginas presentes en todos los `hreflang`.
"""
import os

from marketing import generar_paginas_idioma as gen

PAGINAS = [
    ("es", os.path.join(gen.krutas.ROOT_REPO, "landing", "index.html"), "https://mvkobranzaia.com/"),
    ("pt", os.path.join(gen.krutas.ROOT_REPO, "landing", "pt", "index.html"), "https://mvkobranzaia.com/pt/"),
    ("en", os.path.join(gen.krutas.ROOT_REPO, "landing", "en", "index.html"), "https://mvkobranzaia.com/en/"),
    ("es", os.path.join(gen.krutas.ROOT_REPO, "dashboard_estatico", "index.html"), "https://mvkobranzaia.com/demo/"),
    ("pt", os.path.join(gen.krutas.ROOT_REPO, "dashboard_estatico", "pt", "index.html"), "https://mvkobranzaia.com/demo/pt/"),
    ("en", os.path.join(gen.krutas.ROOT_REPO, "dashboard_estatico", "en", "index.html"), "https://mvkobranzaia.com/demo/en/"),
]


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def test_las_variantes_generadas_estan_al_dia_con_el_maestro():
    """Si alguien edita `landing/index.html` o `dashboard_estatico/index.html`
    y no vuelve a correr el generador, `/en/`/`/pt/` quedan mostrando el
    `<head>` viejo — recalcula lo que el generador produciría HOY y lo
    compara contra lo que hay commiteado en disco."""
    base_landing = _leer(gen.LANDING)
    base_demo = _leer(gen.DEMO)
    for lang, reemplazos in gen.META_LANDING.items():
        html = base_landing.replace('<html lang="es">', f'<html lang="{lang}">')
        for viejo, nuevo in reemplazos.items():
            html = html.replace(viejo, nuevo)
        destino = os.path.join(gen.krutas.ROOT_REPO, "landing", lang, "index.html")
        assert _leer(destino) == html, (
            f"landing/{lang}/index.html quedó desactualizado — correr "
            "python -m marketing.generar_paginas_idioma")
    for lang, reemplazos in gen.META_DEMO.items():
        html = base_demo.replace('<html lang="es">', f'<html lang="{lang}">')
        for viejo, nuevo in reemplazos.items():
            html = html.replace(viejo, nuevo)
        html = gen._absolutizar_rutas_demo(html)
        destino = os.path.join(gen.krutas.ROOT_REPO, "dashboard_estatico", lang, "index.html")
        assert _leer(destino) == html, (
            f"dashboard_estatico/{lang}/index.html quedó desactualizado — "
            "correr python -m marketing.generar_paginas_idioma")


def test_cada_variante_tiene_el_idioma_el_locale_y_la_url_correctos():
    LOCALE = {"es": "es_UY", "pt": "pt_BR", "en": "en_US"}
    for lang, ruta, url in PAGINAS:
        html = _leer(ruta)
        assert f'<html lang="{lang}">' in html, f"{ruta}: html lang no es {lang}"
        assert f'content="{LOCALE[lang]}"' in html and "og:locale" in html.split(
            f'content="{LOCALE[lang]}"')[0][-40:], f"{ruta}: og:locale no es {LOCALE[lang]}"
        assert f'href="{url}"' in html and 'rel="canonical"' in html.split(
            f'href="{url}"')[0][-30:], f"{ruta}: canonical no apunta a {url}"
        assert f'content="{url}"' in html, f"{ruta}: og:url no apunta a {url}"


def test_cada_variante_lista_las_mismas_cuatro_alternativas_de_idioma():
    """El bloque `hreflang` tiene que ser IDÉNTICO en las tres versiones de
    cada página: le dice al buscador "estas cuatro URLs son la misma
    página" — si una lista distinto, deja de ser una lista consistente."""
    for grupo in [PAGINAS[:3], PAGINAS[3:]]:
        bloques = []
        for _, ruta, _ in grupo:
            html = _leer(ruta)
            ini = html.index('rel="alternate"') - 20
            fin = html.index("x-default", ini) + 60
            bloques.append(html[ini:fin])
        assert len(set(bloques)) == 1, f"el bloque hreflang difiere entre variantes: {grupo}"


def test_la_demo_generada_no_referencia_ninguna_ruta_relativa_propia():
    """Si queda una ruta relativa (`src="chart.umd.min.js"` en vez de
    `/demo/chart.umd.min.js`), el navegador la pide contra `/demo/en/` en vez
    de `/demo/`, y 404. Ya pasó al escribir el generador."""
    for lang, ruta, _ in PAGINAS:
        if "dashboard_estatico" not in ruta or lang == "es":
            continue
        html = _leer(ruta)
        for nombre in gen._ASSETS_DEMO_RELATIVOS:
            assert f'"{nombre}"' not in html, f"{ruta}: {nombre} sigue siendo relativo"
        assert "fetch('/demo/modelo_web.json')" in html
        assert "'/demo/audio_demo/'+IDIOMA" in html


def test_vercel_json_tiene_un_rewrite_para_cada_variante():
    import json
    with open(os.path.join(gen.krutas.ROOT_REPO, "vercel.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    fuentes = {r["source"] for r in cfg["rewrites"]}
    for esperada in ("/en/", "/pt/", "/demo/en/", "/demo/pt/"):
        assert esperada in fuentes, f"falta el rewrite de {esperada} en vercel.json"
    # Y que /demo/en//demo/pt/ estén ANTES del catch-all /demo/:path*, si no
    # el catch-all los intercepta primero.
    orden = [r["source"] for r in cfg["rewrites"]]
    assert orden.index("/demo/en/") < orden.index("/demo/:path*")
    assert orden.index("/demo/pt/") < orden.index("/demo/:path*")
