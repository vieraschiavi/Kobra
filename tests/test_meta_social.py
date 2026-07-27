"""Tests de la previsualización al compartir (Open Graph / Twitter Card) y de
la coherencia de los iconos de marca.

Dos defectos reales que cubren estos tests:

* Ninguna de las páginas públicas tenía etiquetas Open Graph, así que compartir
  el link en LinkedIn, X o WhatsApp lo mostraba como texto pelado — sin imagen,
  sin título y sin descripción.
* `assets/brand/mv_icon_256.png` era en realidad de 1024×1024: el nombre mentía
  y quien lo usara por su nombre embebía una imagen 16 veces más pesada de lo
  que esperaba.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from marketing import kit_social as K  # noqa: E402

# (archivo, URL canónica que le corresponde según vercel.json)
PAGINAS = [
    (os.path.join("landing", "index.html"), f"https://{K.DOMINIO}/"),
    (os.path.join("landing", "descarga.html"), f"https://{K.DOMINIO}/descarga"),
    (os.path.join("dashboard_estatico", "index.html"), f"https://{K.DOMINIO}/demo/"),
]

OG_IMAGEN = f"https://{K.DOMINIO}/landing/og.png"


def _html(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _meta(html: str, atributo: str, nombre: str) -> str | None:
    m = re.search(rf'<meta\s+{atributo}="{re.escape(nombre)}"\s+content="([^"]*)"',
                  html)
    return m.group(1) if m else None


@pytest.mark.parametrize("rel,canonica", PAGINAS)
def test_cada_pagina_publica_tiene_previsualizacion(rel, canonica):
    """Sin estas etiquetas el link se comparte sin imagen ni descripción."""
    html = _html(rel)
    for prop in ("og:type", "og:title", "og:description", "og:image", "og:url"):
        assert _meta(html, "property", prop), f"{rel}: falta {prop}"
    assert _meta(html, "name", "twitter:card") == "summary_large_image", rel
    assert _meta(html, "name", "description"), f"{rel}: falta la meta description"
    assert _meta(html, "property", "og:url") == canonica, rel
    assert f'<link rel="canonical" href="{canonica}">' in html, rel


@pytest.mark.parametrize("rel,_", PAGINAS)
def test_la_imagen_de_previsualizacion_es_una_url_absoluta(rel, _):
    """Regresión posible y silenciosa: una ruta relativa en `og:image` se ve
    bien en el navegador pero ningún scraper la resuelve, así que la
    previsualización queda sin imagen y nadie se entera."""
    html = _html(rel)
    for prop, atributo in (("og:image", "property"), ("twitter:image", "name")):
        url = _meta(html, atributo, prop)
        assert url and url.startswith("https://"), f"{rel}: {prop} no es absoluta"
        assert url == OG_IMAGEN, f"{rel}: {prop} apunta a otro lado ({url})"


@pytest.mark.parametrize("rel,_", PAGINAS)
def test_ninguna_pagina_publica_apunta_a_un_dominio_ajeno(rel, _):
    """Las URLs de preview de Vercel cambian con cada deploy: si una queda
    escrita en un meta tag, la previsualización apunta a un sitio muerto."""
    html = _html(rel)
    for atributo, nombre in (("property", "og:url"), ("property", "og:image"),
                             ("name", "twitter:image")):
        url = _meta(html, atributo, nombre) or ""
        assert "vercel.app" not in url and "localhost" not in url, f"{rel}: {nombre}"


def test_existe_la_imagen_de_previsualizacion_con_el_tamano_declarado():
    """El PNG tiene que existir en el repo (se sirve desde el sitio) y medir lo
    que dicen `og:image:width`/`height`: si no coinciden, algunas redes lo
    recortan mal o directamente lo descartan."""
    from PIL import Image
    ruta = os.path.join(ROOT, "landing", "og.png")
    assert os.path.exists(ruta), "falta landing/og.png"
    with Image.open(ruta) as im:
        assert im.size == (1200, 630), im.size
    html = _html(os.path.join("landing", "index.html"))
    assert _meta(html, "property", "og:image:width") == "1200"
    assert _meta(html, "property", "og:image:height") == "630"


def test_la_descripcion_no_menciona_precios():
    """Misma regla que el resto del material: el precio se conversa en la
    demo, no en la previsualización de un link."""
    for rel, _ in PAGINAS:
        html = _html(rel)
        for atributo, nombre in (("name", "description"),
                                 ("property", "og:description"),
                                 ("name", "twitter:description")):
            texto = (_meta(html, atributo, nombre) or "").lower()
            for termino in K.PROHIBIDO:
                assert termino not in texto, f"{rel}: {nombre} menciona {termino!r}"


def test_los_iconos_de_marca_miden_lo_que_dice_su_nombre():
    """Regresión: `mv_icon_256.png` era byte-idéntico al de 1024×1024 — el
    nombre mentía y quien lo eligiera por tamaño embebía 16 veces más peso."""
    from PIL import Image
    for nombre, lado in (("mv_icon_256.png", 256), ("mv_icon_128.png", 128),
                         ("mv_icon_64.png", 64), ("mv_icon_32.png", 32)):
        ruta = os.path.join(ROOT, "assets", "brand", nombre)
        with Image.open(ruta) as im:
            assert im.size == (lado, lado), f"{nombre} mide {im.size}"
