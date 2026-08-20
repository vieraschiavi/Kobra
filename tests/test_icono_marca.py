# © 2026 Martín Viera. Todos los derechos reservados.

"""El isotipo MV: que esté en todas las superficies y que no apunte al vacío.

El ícono está copiado en seis lugares (la landing, la demo, el realtime, la
webapp, el build del owner) porque cada superficie se sirve desde una raíz
distinta. Esa duplicación es deliberada, pero deja tres formas de romperse en
silencio:

  * un `href` que apunta a un archivo que no existe — el navegador no protesta,
    simplemente no dibuja nada. Pasó de verdad: la webapp declaraba
    `og:image` → `/landing/og-mvkobraai.png`, un archivo que nunca existió, así
    que el link de la app se compartía sin imagen. Los tests de
    `test_meta_social.py` no lo vieron porque solo miran las tres páginas de la
    landing y la demo;
  * una copia que se actualiza y las otras cinco no, y la marca queda distinta
    según por dónde entres;
  * una pantalla visible que nunca recibió el isotipo.

Este archivo verifica lo que `test_diseno_web.py` no: que cada `href` de ícono
RESUELVA a un archivo real, no solo que la etiqueta exista.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CANONICO = os.path.join(ROOT, "assets", "brand", "mv_icon.png")

# Cada superficie sirve el ícono desde su propia raíz: la landing desde el
# repo entero, la demo desde `dashboard_estatico/`, la webapp desde
# `webapp/frontend/public/`. Para saber si un href resuelve hay que saber
# contra qué raíz se sirve cada página.
#   (html, raíz web → carpeta del repo)
SUPERFICIES = [
    (os.path.join("landing", "index.html"), {"/": ""}),
    (os.path.join("landing", "en", "index.html"), {"/": ""}),
    (os.path.join("landing", "pt", "index.html"), {"/": ""}),
    (os.path.join("landing", "descarga.html"), {"/": ""}),
    (os.path.join("dashboard_estatico", "index.html"),
     {"/demo/": "dashboard_estatico", "": "dashboard_estatico"}),
    (os.path.join("dashboard_estatico", "en", "index.html"),
     {"/demo/": "dashboard_estatico"}),
    (os.path.join("dashboard_estatico", "pt", "index.html"),
     {"/demo/": "dashboard_estatico"}),
    (os.path.join("realtime", "index.html"), {"/": "realtime"}),
    (os.path.join("webapp", "frontend", "index.html"),
     {"/": os.path.join("webapp", "frontend", "public")}),
    (os.path.join("owner", "ui_dist", "index.html"), {"/": os.path.join("owner", "ui_dist")}),
]

# Las copias del isotipo que tienen que seguir siendo el mismo bitmap.
COPIAS_1024 = [
    os.path.join("landing", "mv_icon.png"),
    os.path.join("dashboard_estatico", "mv_icon.png"),
    os.path.join("realtime", "mv_icon.png"),
]
COPIAS_128 = [
    os.path.join("webapp", "frontend", "public", "mv_icon.png"),
    os.path.join("owner", "ui_dist", "mv_icon.png"),
]

_RE_LINK_ICONO = re.compile(
    r'<link[^>]*rel="(icon|apple-touch-icon)"[^>]*href="([^"]+)"', re.I)


def _html(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _resolver(href: str, raices: dict) -> str | None:
    """Traduce un href de la página a una ruta del repo, o None si no aplica."""
    if href.startswith(("http://", "https://", "data:")):
        return None
    # El prefijo más largo primero: "/demo/" tiene que ganarle a "/".
    for prefijo in sorted(raices, key=len, reverse=True):
        if href.startswith(prefijo):
            resto = href[len(prefijo):]
            return os.path.join(ROOT, raices[prefijo], resto)
    return None


# ---------------------------------------------------------------------------
# Que los href resuelvan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel,raices", SUPERFICIES)
def test_cada_icono_declarado_apunta_a_un_archivo_que_existe(rel, raices):
    """Un `<link rel=icon>` con href roto no da error en ningún lado: la
    pestaña simplemente muestra el ícono genérico y nadie se entera."""
    encontrados = _RE_LINK_ICONO.findall(_html(rel))
    assert encontrados, f"{rel}: no declara ningún ícono"
    for tipo, href in encontrados:
        ruta = _resolver(href, raices)
        assert ruta is not None, f"{rel}: no sé resolver {href!r}"
        assert os.path.exists(ruta), \
            f"{rel}: rel={tipo} apunta a {href!r} y ese archivo no existe"


@pytest.mark.parametrize("rel,raices", SUPERFICIES)
def test_cada_pagina_ofrece_icono_para_la_pantalla_de_inicio(rel, raices):
    """Sin `apple-touch-icon`, guardar la página en el inicio de un iPhone deja
    una captura de pantalla recortada en vez del isotipo. Importa sobre todo en
    el portal del deudor, que llega por link o QR al teléfono."""
    tipos = {t for t, _ in _RE_LINK_ICONO.findall(_html(rel))}
    assert "apple-touch-icon" in tipos, f"{rel}: falta apple-touch-icon"


def test_las_imagenes_de_preview_apuntan_a_un_archivo_del_repo():
    """El defecto que motivó este archivo: la webapp declaraba una `og:image`
    que no existía. `test_meta_social.py` no la mira porque solo cubre landing
    y demo, así que el link de la app se compartió sin imagen sin que ningún
    test se quejara."""
    from marketing import kit_social as K
    for rel, _ in SUPERFICIES:
        html = _html(rel)
        for atributo, nombre in (("property", "og:image"), ("name", "twitter:image")):
            m = re.search(
                rf'<meta\s+{atributo}="{re.escape(nombre)}"\s+content="([^"]*)"', html)
            if not m:
                continue
            url = m.group(1)
            prefijo = f"https://{K.DOMINIO}/"
            assert url.startswith(prefijo), f"{rel}: {nombre} apunta afuera ({url})"
            ruta = os.path.join(ROOT, url[len(prefijo):])
            assert os.path.exists(ruta), \
                f"{rel}: {nombre} apunta a {url!r} y ese archivo no está en el repo"


# ---------------------------------------------------------------------------
# Que las copias no se separen
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel", COPIAS_1024)
def test_las_copias_grandes_son_el_mismo_isotipo(rel):
    """Seis copias del mismo bitmap y ningún proceso que las sincronice: si
    alguien actualiza la marca en una sola, el ícono cambia según por dónde
    entres al producto."""
    ruta = os.path.join(ROOT, rel)
    assert os.path.exists(ruta), f"falta {rel}"
    with open(CANONICO, "rb") as f:
        esperado = f.read()
    with open(ruta, "rb") as f:
        assert f.read() == esperado, \
            f"{rel} ya no es el mismo bitmap que assets/brand/mv_icon.png"


@pytest.mark.parametrize("rel", COPIAS_128)
def test_las_copias_chicas_son_el_derivado_de_128(rel):
    ruta = os.path.join(ROOT, rel)
    assert os.path.exists(ruta), f"falta {rel}"
    with open(os.path.join(ROOT, "assets", "brand", "mv_icon_128.png"), "rb") as f:
        esperado = f.read()
    with open(ruta, "rb") as f:
        assert f.read() == esperado, \
            f"{rel} se separó de assets/brand/mv_icon_128.png"


def test_el_icono_de_pantalla_de_inicio_mide_los_180_que_pide_ios():
    """iOS escala lo que le den, pero por debajo de 180 el ícono del inicio
    sale borroneado — que es justo donde se lo mira de cerca."""
    from PIL import Image
    for rel in (os.path.join("assets", "brand", "mv_icon_180.png"),
                os.path.join("webapp", "frontend", "public", "mv_icon_180.png"),
                os.path.join("owner", "ui_dist", "mv_icon_180.png")):
        ruta = os.path.join(ROOT, rel)
        assert os.path.exists(ruta), f"falta {rel}"
        with Image.open(ruta) as im:
            assert im.size == (180, 180), f"{rel} mide {im.size}"


# ---------------------------------------------------------------------------
# Producto de escritorio y portal del deudor
# ---------------------------------------------------------------------------
def test_el_splash_de_electron_lleva_el_isotipo_embebido():
    """Es la primera pantalla del producto de escritorio. El isotipo va como
    data URI a propósito: `files` en electron/package.json es una lista
    explícita (main.js, preload.js, splash.html), así que un PNG al lado se
    vería en desarrollo y saldría roto en el instalador."""
    import json
    html = _html(os.path.join("electron", "splash.html"))
    assert "<img" in html, "el splash no muestra el isotipo"
    assert 'src="data:image/png;base64,' in html, \
        "el isotipo del splash no está embebido: dependería del empaquetado"

    with open(os.path.join(ROOT, "electron", "package.json"), encoding="utf-8") as f:
        archivos = json.load(f)["build"]["files"]
    sueltos = [h for h in _RE_LINK_ICONO.findall(html)
               if not h[1].startswith("data:")]
    for _tipo, href in sueltos:
        assert href.lstrip("./") in archivos, \
            f"el splash referencia {href!r}, que no está en build.files y no se empaqueta"


def test_el_portal_del_deudor_muestra_la_marca():
    """`/pagar` es la única pantalla que ve alguien de afuera de la empresa
    cliente, y llega por un link o un QR. Se renderiza fuera del shell de
    App.jsx, así que no hereda el header con el logo: si no lo lleva propio,
    el deudor pone plata en una pantalla sin identificar."""
    ruta = os.path.join(ROOT, "webapp", "frontend", "src", "pages", "PortalPago.jsx")
    with open(ruta, encoding="utf-8") as f:
        jsx = f.read()
    assert 'src="/mv_icon.png"' in jsx, \
        "el portal del deudor no muestra el isotipo en su header"
