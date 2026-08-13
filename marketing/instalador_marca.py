# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Imágenes de marca del instalador de Windows
==========================================================
El instalador NSIS mostraba las imágenes genéricas de electron-builder: un
degradado azul de fábrica que no dice nada. Un programa que se cobra tiene que
verse como tal desde la primera pantalla — el asistente de instalación es lo
primero que ve el cliente, antes que el producto.

Genera las dos piezas que consume electron-builder:

* `installerSidebar.bmp` — 164×314, la franja de la izquierda en la primera y
  la última pantalla del asistente.
* `installerHeader.bmp` — 150×57, la banda de arriba en las pantallas
  intermedias.

**Tienen que ser BMP.** NSIS usa `MUI_WELCOMEFINISHPAGE_BITMAP` y
`MUI_HEADERIMAGE_BITMAP`, que solo aceptan mapas de bits sin comprimir; un PNG
con extensión .bmp hace fallar la compilación del instalador. Y los tamaños son
exactos, no orientativos: NSIS no escala, recorta.

Uso:
    python3 -m marketing.instalador_marca
"""
from __future__ import annotations

import base64
import os

from marketing import marca as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "electron", "build")
BRAND = os.path.join(ROOT, "assets", "brand")

# Tamaños que espera NSIS. No son negociables: no escala, recorta.
SIDEBAR = (164, 314)
HEADER = (150, 57)


def _icono_svg() -> str:
    """El isotipo vectorial, embebido. Se usa el SVG y no el PNG porque estas
    piezas son chicas y un raster reducido se ve blando justo donde el cliente
    mira de cerca."""
    with open(os.path.join(BRAND, "mv_icon.svg"), encoding="utf-8") as f:
        svg = f.read()
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def html_sidebar() -> str:
    c = M.MARCA
    return f"""<!doctype html><meta charset="utf-8">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{SIDEBAR[0]}px;height:{SIDEBAR[1]}px;overflow:hidden}}
  body{{font-family:"Inter",sans-serif;color:{c["ink"]};
    display:flex;flex-direction:column;justify-content:space-between;
    padding:20px 16px;
    background:
      radial-gradient(120% 60% at 50% 0%,rgba(0,200,150,.22),transparent 55%),
      linear-gradient(170deg,{c["navy2"]} 0%,{c["navy"]} 100%)}}
  .top{{display:flex;flex-direction:column;align-items:center;gap:14px;margin-top:26px}}
  .top img{{width:74px;height:74px;border-radius:16px}}
  .n{{font-size:17px;font-weight:800;letter-spacing:-.02em;text-align:center;line-height:1.15}}
  .n i{{color:{c["green"]};font-style:normal}}
  .t{{font-size:11px;color:{c["muted"]};text-align:center;line-height:1.35}}
  .pie{{font-size:9.5px;color:{c["faint"]};text-align:center;line-height:1.4}}
</style>
<div class="top">
  <img src="{_icono_svg()}" alt="">
  <div>
    <div class="n">MV KOBRA <i>AI</i></div>
    <div class="t" style="margin-top:5px">Cobranzas inteligentes</div>
  </div>
</div>
<div class="pie">Predicción de pago<br>Agente negociador<br>Copiloto de calidad</div>
"""


def html_header() -> str:
    c = M.MARCA
    return f"""<!doctype html><meta charset="utf-8">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{HEADER[0]}px;height:{HEADER[1]}px;overflow:hidden}}
  /* La banda del encabezado va sobre el fondo CLARO del asistente: si se la
     pinta oscura queda un rectángulo pegado que se nota. */
  body{{font-family:"Inter",sans-serif;background:#ffffff;color:{c["navy"]};
    display:flex;align-items:center;gap:8px;padding:0 10px}}
  img{{width:32px;height:32px;border-radius:8px;flex:none}}
  /* Ajustado a ojo NO: se mide el margen derecho del render. Con 13px/8.5px
     el texto quedaba a 3 px del borde y en pantallas con escalado se cortaba. */
  .n{{font-size:12px;font-weight:800;letter-spacing:-.02em;line-height:1.1;white-space:nowrap}}
  .n i{{color:{c["green"]};font-style:normal}}
  .t{{font-size:7.8px;color:{c["muted"]};white-space:nowrap;margin-top:2px}}
</style>
<img src="{_icono_svg()}" alt="">
<div>
  <div class="n">MV KOBRA <i>AI</i></div>
  <div class="t">Cobranzas inteligentes</div>
</div>
"""


def _render(html: str, tamano: tuple[int, int], destino: str) -> str:
    """Renderiza y guarda como BMP de 24 bits, que es lo que traga NSIS."""
    import tempfile

    from PIL import Image
    from playwright.sync_api import sync_playwright

    from marketing.generar_kit_social import _chromium, fuente_disponible
    if not fuente_disponible():
        raise RuntimeError(
            "No hay una tipografía del diseño instalada; el instalador saldría "
            "con la fuente equivocada. Instalá una: apt-get install -y fonts-inter")

    ejecutable = _chromium()
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "pieza.png")
        with sync_playwright() as p:
            navegador = p.chromium.launch(
                **({"executable_path": ejecutable} if ejecutable else {}))
            pagina = navegador.new_page(
                viewport={"width": tamano[0], "height": tamano[1]},
                device_scale_factor=1)
            pagina.set_content(html, wait_until="load")
            pagina.screenshot(path=png)
            navegador.close()
        with Image.open(png) as im:
            # NSIS no entiende transparencia en estos bitmaps: se aplana sobre
            # blanco antes de guardar, si no el fondo sale negro.
            plano = Image.new("RGB", im.size, "#ffffff")
            plano.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            plano.save(destino, format="BMP")
    return destino


def generar(destino: str | None = None) -> dict[str, str]:
    destino = destino or BUILD
    piezas = {
        "installerSidebar.bmp": (html_sidebar(), SIDEBAR),
        "installerHeader.bmp": (html_header(), HEADER),
    }
    salida = {}
    for nombre, (html, tamano) in piezas.items():
        salida[nombre] = _render(html, tamano, os.path.join(destino, nombre))
    return salida


if __name__ == "__main__":
    from PIL import Image
    for nombre, ruta in generar().items():
        with Image.open(ruta) as im:
            print(f"[OK] {nombre:24s} {im.size[0]}×{im.size[1]} {im.format} "
                  f"{os.path.getsize(ruta) / 1024:.1f} KB")
