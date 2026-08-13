# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Generador del kit de contenido para redes
=======================================================
Renderiza los banners de `kit_social.py` a PNG en tamaño real, los valida y
los empaqueta en ZIPs listos para publicar.

Por qué existe (y por qué valida en vez de solo renderizar)
------------------------------------------------------------
La primera versión de este kit se armó como un HTML suelto con las piezas
posicionadas en absoluto y unidades `cqw`. Se veía bien en el navegador del
diseño y salió mal al exportar: **el texto pisaba el mockup**. La causa no era
el CSS sino la tipografía — el diseño pedía `Segoe UI`/`Roboto`, la máquina de
render no las tiene, cayó a una fuente más ancha, los titulares crecieron y se
comieron el espacio del mockup. Con posicionamiento absoluto nada lo impide.

De ahí las tres decisiones de este módulo:

1. **Layout por CSS grid, nunca absoluto.** Cada pieza vive en su celda. Que
   el texto crezca no puede invadir el mockup: como mucho desborda su propia
   celda, y eso se detecta.
2. **Tipografía explícita y verificada.** Se exige una familia realmente
   instalada; si no está, el generador se planta en vez de exportar 5 PNG con
   la fuente equivocada.
3. **Validación geométrica automática.** Después de renderizar y antes de
   guardar, se mide el DOM: ninguna zona se superpone con otra y ningún texto
   desborda su caja. Un PNG roto no llega a publicarse.

Además se chequea el contenido: ninguna pieza puede mostrar precios ni URLs de
preview (ver `PROHIBIDO` y `DOMINIO` en `kit_social.py`).

Uso:
    python3 -m marketing.generar_kit_social
    python3 -m marketing.generar_kit_social --salida dist/social
"""
from __future__ import annotations

import base64
import glob
import html as _html
import io
import os
import re
import shutil
import zipfile

from marketing import kit_social as K

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SALIDA_DEFAULT = os.path.join(ROOT, "dist", "social")

# Familias aceptables, en orden de preferencia. Tienen que estar INSTALADAS:
# si el render cae a una fuente de fallback, las métricas cambian y el diseño
# se rompe de la misma forma que rompió la primera vez.
#
# DejaVu Sans SALIÓ de la lista, y no por gusto: es la única que suele estar en
# un Linux pelado, así que colarla acá hacía que el generador se diera por
# satisfecho y exportara igual. Medido en una máquina con solo DejaVu, el
# banner `linkedin_feed` sale con la marca encima del texto — exactamente el
# defecto que este módulo existe para evitar. Es notablemente más ancha que
# Inter/Roboto: los titulares ocupan más líneas y desbordan su celda.
#
# Sin ninguna de estas instalada, `fuente_disponible()` devuelve '' y el
# generador se planta, que es lo correcto: mejor no generar el kit que publicar
# cinco PNG rotos. Para habilitarlo:
#     Debian/Ubuntu: sudo apt-get install -y fonts-inter   (o fonts-roboto)
#     macOS        : brew install --cask font-inter
FUENTES = ("Inter", "Roboto", "Open Sans", "Lato")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _b64(ruta: str) -> str:
    """Imagen como data URI. Todo va embebido: el HTML se renderiza sin
    servidor y el PNG no depende de rutas relativas."""
    with open(ruta, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def _alto_franja_clara(im, umbral: int = 200, tope: float = 0.15) -> int:
    """Alto en píxeles de la franja clara que encabeza la captura.

    Las capturas del dashboard traen arriba la barra de herramientas de
    Streamlit, que es blanca: sobre una pieza oscura queda como un tajo. En vez
    de hardcodear cuántos píxeles mide — cambia si cambia la captura — se mide
    cuántas filas seguidas desde arriba son claras. Se busca solo en el primer
    `tope` del alto para no comerse un gráfico de fondo claro.
    """
    ancho, alto = im.size
    limite = int(alto * tope)
    gris = im.convert("L").crop((0, 0, ancho, limite))
    pixeles = list(gris.tobytes())
    filas = 0
    for y in range(limite):
        fila = pixeles[y * ancho:(y + 1) * ancho]
        if sum(fila) / ancho <= umbral:
            break
        filas = y + 1
    return filas


def captura_recortada(ruta: str, izquierda: float = 0.0) -> str:
    """Data URI de una captura, sin la barra lateral ni la franja del toolbar.

    El recorte se hace acá y no con CSS por dos motivos. Se saca de la captura
    lo que a tamaño de banner es ruido: la barra de filtros del dashboard —
    `izquierda` es qué fracción cortarle — queda como un amontonamiento de
    chips ilegible, y la franja blanca del toolbar rompe una pieza oscura. Y
    hacerlo sobre el píxel, en vez de con márgenes negativos dentro de un
    contenedor con `overflow:hidden`, deja la imagen lista para que el CSS solo
    tenga que escalarla: menos superficie donde el layout se descuadre.
    """
    from PIL import Image
    with Image.open(ruta) as im:
        w, h = im.size
        recorte = im.crop((int(w * izquierda), 0, w, h)) if izquierda else im.copy()
        franja = _alto_franja_clara(recorte)
        if franja:
            recorte = recorte.crop((0, franja, recorte.width, recorte.height))
        buf = io.BytesIO()
        recorte.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def fuente_disponible() -> str:
    """Primera familia de `FUENTES` realmente instalada, o '' si no hay
    ninguna. Se consulta a fontconfig, que es lo que ve el navegador."""
    import subprocess
    try:
        salida = subprocess.run(["fc-list", ":", "family"], capture_output=True,
                                text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    familias = {f.strip().lower() for linea in salida.splitlines()
                for f in linea.split(",")}
    for nombre in FUENTES:
        if nombre.lower() in familias:
            return nombre
    return ""


def _chromium() -> str | None:
    """Ruta del Chromium preinstalado. Devuelve None para que Playwright
    resuelva solo cuando no hay uno en la ubicación conocida."""
    for patron in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   "/opt/pw-browsers/chromium/chrome-linux/chrome"):
        encontrados = sorted(glob.glob(patron))
        if encontrados:
            return encontrados[-1]
    return None


# --------------------------------------------------------------------------
# HTML de un banner
# --------------------------------------------------------------------------
def _escalas(banner: dict) -> dict:
    """Tamaños en píxeles, derivados del ancho de la pieza.

    Se calculan acá y no con unidades de contenedor (`cqw`) porque así el
    render es determinístico y las medidas se pueden testear sin navegador.
    """
    a = banner["ancho"]
    mult = {
        "split": dict(hl=.055, sub=.021, eye=.0165, cta=.021, chip=.0165, pad=.055),
        "stack": dict(hl=.078, sub=.030, eye=.022, cta=.030, chip=.022, pad=.070),
        "banda": dict(hl=.045, sub=.020, eye=.016, cta=.020, chip=.016, pad=.055),
    }[banner["layout"]]
    return {k: round(a * v, 1) for k, v in mult.items()}


def html_banner(banner: dict, fuente: str) -> str:
    """HTML autocontenido de una pieza, del tamaño exacto del entregable.

    Cada bloque lleva `data-zona`: es lo que después mide el validador para
    comprobar que ninguna zona invade a otra.
    """
    e = _escalas(banner)
    c = K.COLORES
    icono = _b64(os.path.join(ASSETS, "brand", "mv_icon.png"))
    captura = (captura_recortada(os.path.join(ASSETS, banner["captura"]),
                                 izquierda=float(banner.get("recorte") or 0))
               if banner.get("captura") else "")

    marca = f"""
      <div class="lock">
        <img src="{icono}" alt="MV Kobra AI">
        <div>
          <div class="wm">MV KOBRA <i>AI</i></div>
          <div class="tg">{K.BAJADA}</div>
        </div>
      </div>"""

    cta = (f'<div class="cta">{_html.escape(K.CTA)} →</div>'
           if banner.get("cta") else "")
    chips = ("".join(f'<span class="chip">{_html.escape(t)}</span>'
                     for t in banner.get("chips", [])))
    chips = f'<div class="chips">{chips}</div>' if chips else ""
    sub = (f'<div class="sub">{_html.escape(banner["sub"])}</div>'
           if banner.get("sub") else "")

    texto = f"""
      <div class="txt" data-zona="texto">
        <div class="eyeb">{_html.escape(banner["eyebrow"])}</div>
        <div class="hl" data-fit>{banner["headline"]}</div>
        {sub}{chips}{cta}
      </div>"""

    shot = (f"""
      <div class="shot" data-zona="mockup">
        <div class="frame">
          <div class="bar"><i></i><i></i><i></i></div>
          <div class="win"><img src="{captura}" alt="Tablero MV Kobra AI"></div>
        </div>
      </div>""" if captura else "")

    pie = f'<div class="pie" data-zona="pie">{K.DOMINIO}</div>'

    # --- composición por layout (grid en todos los casos) ---
    if banner["layout"] == "split":
        cuerpo = f'<div class="g split">{texto}{shot}</div>'
        cabecera = f'<div class="top" data-zona="marca">{marca}{pie}</div>'
        grid = "grid-template-rows:auto 1fr"
        orden = cabecera + cuerpo
    elif banner["layout"] == "stack":
        cabecera = f'<div class="top" data-zona="marca">{marca}</div>'
        cuerpo = f'<div class="g stack">{texto}{shot}</div>'
        grid = "grid-template-rows:auto 1fr auto"
        orden = cabecera + cuerpo + f'<div class="bot">{pie}</div>'
    else:  # banda
        cuerpo = f'<div class="g banda">{texto}</div>'
        cabecera = f'<div class="top" data-zona="marca">{marca}{pie}</div>'
        grid = "grid-template-rows:auto 1fr"
        orden = cabecera + cuerpo

    return f"""<!doctype html><meta charset="utf-8">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{banner["ancho"]}px;height:{banner["alto"]}px;overflow:hidden}}
  body{{font-family:"{fuente}",sans-serif;color:{c["ink"]};
    background:
      radial-gradient(120% 130% at 82% 8%,rgba(0,200,150,.20),transparent 46%),
      radial-gradient(120% 120% at 10% 100%,rgba(47,116,192,.28),transparent 52%),
      linear-gradient(150deg,{c["navy2"]} 0%,{c["navy"]} 60%,#060f1d 100%);
    display:grid;{grid};padding:{e["pad"]}px;gap:{e["pad"] * .5}px}}
  .top{{display:flex;align-items:center;justify-content:space-between;gap:16px;min-width:0}}
  .bot{{display:flex;justify-content:center}}
  .lock{{display:flex;align-items:center;gap:{e["eye"] * .8}px;min-width:0}}
  .lock img{{width:{e["hl"] * .8}px;height:{e["hl"] * .8}px;border-radius:{e["hl"] * .16}px;flex:none}}
  .wm{{font-weight:800;letter-spacing:-.02em;font-size:{e["eye"] * 1.5}px;line-height:1.1;white-space:nowrap}}
  .wm i{{color:{c["green"]};font-style:normal}}
  .tg{{font-size:{e["eye"] * .95}px;color:{c["muted"]};white-space:nowrap}}
  .pie{{font-size:{e["eye"] * .95}px;color:{c["muted"]};white-space:nowrap;flex:none}}
  .g{{display:grid;gap:{e["pad"] * .6}px;min-height:0;min-width:0}}
  .split{{grid-template-columns:54fr 46fr;align-items:center}}
  /* El mockup tiene alto reservado: si se lo deja crecer con lo que sobre, el
     texto se lo come y en el cuadrado queda una tira ilegible al pie. El
     texto se achica solo para entrar en lo que queda. */
  .stack{{grid-template-rows:1fr {round(banner["alto"] * float(banner.get("mockup") or .34))}px}}
  .banda{{align-items:center}}
  .txt{{display:flex;flex-direction:column;justify-content:safe center;
    gap:{e["pad"] * .42}px;min-width:0;min-height:0;overflow:hidden}}
  .eyeb{{font-size:{e["eye"]}px;letter-spacing:.16em;text-transform:uppercase;
    color:{c["green_hi"]};font-weight:600}}
  .hl{{font-size:{e["hl"]}px;font-weight:800;letter-spacing:-.03em;line-height:1.04;
    text-wrap:balance}}
  .hl b{{color:{c["green"]}}}
  .sub{{font-size:{e["sub"]}px;color:{c["sub"]};line-height:1.4;max-width:26ch}}
  .cta{{align-self:start;background:{c["green"]};color:#062018;font-weight:800;
    border-radius:999px;padding:{e["cta"] * .72}px {e["cta"] * 1.5}px;
    font-size:{e["cta"]}px;white-space:nowrap}}
  .chips{{display:flex;flex-wrap:wrap;gap:{e["chip"] * .55}px}}
  .chip{{border:1px solid rgba(255,255,255,.18);border-radius:999px;
    padding:{e["chip"] * .42}px {e["chip"] * .95}px;font-size:{e["chip"]}px;
    color:#cdd9e8;background:rgba(255,255,255,.04);white-space:nowrap}}
  .shot{{display:flex;align-items:center;justify-content:flex-end;
    min-width:0;min-height:0;overflow:hidden}}
  /* En vertical el mockup ocupa todo el alto que sobra y se recorta abajo:
     si se lo deja a su altura natural queda un hueco muerto al pie. */
  .stack .shot{{align-items:stretch;justify-content:center}}
  .frame{{width:100%;border-radius:{e["pad"] * .28}px;overflow:hidden;
    display:flex;flex-direction:column;min-height:0;
    border:1px solid rgba(255,255,255,.14);background:#0b1626;
    box-shadow:0 {e["pad"] * .5}px {e["pad"]}px rgba(0,0,0,.5)}}
  .win{{overflow:hidden;min-height:0}}
  /* En vertical la ventana llena el alto sobrante y la captura la cubre
     desde arriba a la izquierda: si no, queda una franja vacía al pie. */
  .stack .win{{flex:1}}
  .stack .win img{{height:100%;object-fit:cover;object-position:left top}}
  .bar{{height:{e["eye"] * 1.6}px;display:flex;align-items:center;
    gap:{e["eye"] * .45}px;padding:0 {e["eye"] * .7}px;background:#0e2036;
    border-bottom:1px solid rgba(255,255,255,.08)}}
  .bar i{{width:{e["eye"] * .5}px;height:{e["eye"] * .5}px;border-radius:50%;
    background:#33507a;display:block}}
  .frame img{{width:100%;display:block}}
</style>
{orden}
"""


# --------------------------------------------------------------------------
# Validación geométrica
# --------------------------------------------------------------------------
# Se corre dentro de la página, con el layout ya resuelto: es la única forma
# de saber qué pasó de verdad con la tipografía real.
_JS_AJUSTAR = """() => {
  // Achica el titular hasta que su CONTENEDOR deje de recortar.
  //
  // La tolerancia no es un parche: una caja de texto casi siempre reporta uno
  // o dos píxeles más de scroll que de client, porque las tildes y las colas
  // de las letras sobresalen de la caja de línea. Sin tolerancia el bucle
  // persigue esa diferencia inalcanzable y encoge el titular hasta dejarlo
  // ilegible — con el encabezado de mail lo bajó de 54 px a 20 px.
  const TOL = 3;
  for (const el of document.querySelectorAll('[data-fit]')) {
    let px = parseFloat(getComputedStyle(el).fontSize);
    const caja = el.parentElement;
    for (let i = 0; i < 22; i++) {
      const desborda = caja.scrollHeight > caja.clientHeight + TOL ||
                       caja.scrollWidth > caja.clientWidth + TOL;
      if (!desborda || px < 12) break;
      px *= 0.94;
      el.style.fontSize = px + 'px';
    }
  }
  return true;
}"""

_JS_VALIDAR = """() => {
  const problemas = [];
  const zonas = [...document.querySelectorAll('[data-zona]')];
  const r = el => el.getBoundingClientRect();
  const solapan = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 &&
                            a.top < b.bottom - 1 && b.top < a.bottom - 1;
  for (let i = 0; i < zonas.length; i++)
    for (let j = i + 1; j < zonas.length; j++) {
      // Una zona anidada dentro de otra se superpone por definición: eso no
      // es un defecto, es la jerarquía del documento.
      if (zonas[i].contains(zonas[j]) || zonas[j].contains(zonas[i])) continue;
      if (solapan(r(zonas[i]), r(zonas[j])))
        problemas.push(`se superponen las zonas "${zonas[i].dataset.zona}" y ` +
                       `"${zonas[j].dataset.zona}"`);
    }

  const W = document.documentElement.clientWidth;
  const H = document.documentElement.clientHeight;
  for (const el of zonas) {
    const b = r(el);
    if (b.left < -1 || b.top < -1 || b.right > W + 1 || b.bottom > H + 1)
      problemas.push(`la zona "${el.dataset.zona}" se sale del lienzo`);
  }
  // Recorte real. Se miden los CONTENEDORES que recortan (`.txt`), no cada
  // bloque de texto: un bloque casi siempre reporta uno o dos píxeles de más
  // porque las tildes sobresalen de la caja de línea, y eso no recorta nada.
  // La imagen del mockup se recorta a propósito, así que no entra acá.
  const TOL = 3;
  for (const el of document.querySelectorAll('.txt')) {
    if (el.scrollWidth > el.clientWidth + TOL)
      problemas.push('el texto no entra a lo ancho de su columna');
    if (el.scrollHeight > el.clientHeight + TOL)
      problemas.push('el texto no entra a lo alto de su columna');
  }
  // Y cada bloque de texto tiene que quedar dentro de su contenedor: si se
  // sale, algo lo va a tapar aunque el contenedor no reporte scroll.
  for (const el of document.querySelectorAll('.hl,.sub,.eyeb,.cta,.chips')) {
    const caja = r(el.closest('.txt') || document.body), b = r(el);
    if (b.left < caja.left - TOL || b.right > caja.right + TOL ||
        b.top < caja.top - TOL || b.bottom > caja.bottom + TOL)
      problemas.push(`se sale de su columna el bloque .${el.className}`);
  }
  return problemas;
}"""


def _texto_visible(page) -> str:
    return page.evaluate("() => document.body.innerText")


def revisar_contenido(texto: str) -> list[str]:
    """Términos prohibidos y URLs indebidas en el texto que se ve en la pieza.

    Se aplica al texto renderizado y no al código fuente: lo que importa es lo
    que termina publicado."""
    problemas = []
    bajo = texto.lower()
    for termino in K.PROHIBIDO:
        if termino in bajo:
            problemas.append(f"aparece un término prohibido: {termino!r}")
    for url in re.findall(r"[a-z0-9.-]+\.(?:com|app|io|net|uy)\b", bajo):
        if url != K.DOMINIO:
            problemas.append(f"URL que no es el dominio oficial: {url!r}")
    return problemas


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
def renderizar(out_dir: str, fuente: str | None = None,
               solo: set[str] | None = None) -> list[dict]:
    """Renderiza cada banner a PNG en tamaño real y lo valida.

    `solo` limita el render a esos ids (levantar el navegador para una sola
    pieza es mucho más rápido que rehacer las seis).

    Devuelve una lista de {id, archivo, ancho, alto, problemas}. Un banner con
    problemas se guarda igual (sirve para ver qué salió mal) pero se reporta,
    y `main()` termina con código distinto de cero.
    """
    from playwright.sync_api import sync_playwright

    fuente = fuente or fuente_disponible()
    if not fuente:
        raise RuntimeError(
            "No hay ninguna tipografía aceptable instalada "
            f"({', '.join(FUENTES)}). Renderizar con la fuente de fallback "
            "cambia las métricas y descuadra el diseño — que es exactamente "
            "el bug que este generador existe para no repetir. "
            "Instalá una: apt-get install -y fonts-inter")

    os.makedirs(out_dir, exist_ok=True)
    resultados = []
    ejecutable = _chromium()
    with sync_playwright() as p:
        navegador = p.chromium.launch(
            **({"executable_path": ejecutable} if ejecutable else {}))
        for b in K.BANNERS:
            if solo and b["id"] not in solo:
                continue
            page = navegador.new_page(
                viewport={"width": b["ancho"], "height": b["alto"]},
                device_scale_factor=1)
            page.set_content(html_banner(b, fuente), wait_until="load")
            page.evaluate(_JS_AJUSTAR)
            problemas = list(page.evaluate(_JS_VALIDAR))
            problemas += revisar_contenido(_texto_visible(page))
            archivo = f"{b['id']}_{b['ancho']}x{b['alto']}.png"
            page.screenshot(path=os.path.join(out_dir, archivo))
            page.close()
            resultados.append({"id": b["id"], "titulo": b["titulo"],
                               "archivo": archivo, "ancho": b["ancho"],
                               "alto": b["alto"], "problemas": problemas})
        navegador.close()
    return resultados


# --------------------------------------------------------------------------
# Textos del kit
# --------------------------------------------------------------------------
def copy_markdown() -> str:
    partes = ["# MV Kobra AI · Copy por red\n",
              f"CTA único: **{K.CTA}** · Dominio: **{K.DOMINIO}**\n",
              "> Ninguna pieza menciona precios: el precio se conversa en la "
              "demo, no en el feed.\n"]
    for c in K.COPY:
        partes.append(f"\n## {c['red']} — {c['formato']}\n")
        partes.append("```\n" + c["texto"].format(cta=K.CTA, dominio=K.DOMINIO)
                      + "\n```\n")
    return "".join(partes)


def reels_markdown() -> str:
    partes = ["# MV Kobra AI · Storyboards de reels\n",
              "Formato vertical 1080×1920. Cada cuadro indica tiempo, texto "
              "en pantalla y qué se ve.\n"]
    for r in K.REELS:
        partes.append(f"\n## {r['titulo']}\n\n")
        partes.append("| Tiempo | Texto en pantalla | Qué se ve |\n")
        partes.append("|---|---|---|\n")
        for t, txt, nota in r["cuadros"]:
            partes.append(f"| {t} | {txt.replace(chr(10), ' / ')} | {nota} |\n")
    return "".join(partes)


def leeme(resultados: list[dict]) -> str:
    filas = "\n".join(f"- `{r['archivo']}` — {r['titulo']} "
                      f"({r['ancho']}×{r['alto']} px)" for r in resultados)
    return f"""# MV Kobra AI · Kit de contenido para redes

Generado por `marketing/generar_kit_social.py`. Para regenerarlo:

    python3 -m marketing.generar_kit_social

## Banners

{filas}

## Reglas de uso

- **Ninguna pieza muestra precios.** El precio se conversa en la demo.
- Las cifras del producto son **ilustrativas**, sobre datos sintéticos: no se
  publican como resultados reales de un cliente.
- Dominio único en todas las piezas: **{K.DOMINIO}**. Las URLs de preview de
  Vercel cambian con cada deploy y no van en material publicado.
- CTA único: **{K.CTA}**.

## Contenido

- `banners/` — PNG en tamaño real, listos para subir.
- `copy.md` — texto por red, editable.
- `reels.md` — storyboards cuadro por cuadro.
"""


# --------------------------------------------------------------------------
# Empaquetado
# --------------------------------------------------------------------------
def generar(out_dir: str | None = None, fuente: str | None = None) -> dict:
    """Genera el kit completo: PNGs, textos y ZIPs. Devuelve un resumen."""
    out_dir = out_dir or SALIDA_DEFAULT
    shutil.rmtree(out_dir, ignore_errors=True)
    banners_dir = os.path.join(out_dir, "banners")
    resultados = renderizar(banners_dir, fuente=fuente)

    with open(os.path.join(out_dir, "copy.md"), "w", encoding="utf-8") as f:
        f.write(copy_markdown())
    with open(os.path.join(out_dir, "reels.md"), "w", encoding="utf-8") as f:
        f.write(reels_markdown())
    with open(os.path.join(out_dir, "LEEME.md"), "w", encoding="utf-8") as f:
        f.write(leeme(resultados))

    # Un ZIP con todo, y uno solo de banners para mandar al diseñador o subir
    # rápido sin arrastrar los textos.
    zips = {}
    completo = os.path.join(out_dir, "MVKobraAI_Kit_Social.zip")
    with zipfile.ZipFile(completo, "w", zipfile.ZIP_DEFLATED) as z:
        for r in resultados:
            z.write(os.path.join(banners_dir, r["archivo"]),
                    f"banners/{r['archivo']}")
        for nombre in ("copy.md", "reels.md", "LEEME.md"):
            z.write(os.path.join(out_dir, nombre), nombre)
    zips["completo"] = completo

    solo_banners = os.path.join(out_dir, "MVKobraAI_Banners.zip")
    with zipfile.ZipFile(solo_banners, "w", zipfile.ZIP_DEFLATED) as z:
        for r in resultados:
            z.write(os.path.join(banners_dir, r["archivo"]), r["archivo"])
    zips["banners"] = solo_banners

    problemas = {r["id"]: r["problemas"] for r in resultados if r["problemas"]}
    return {"banners": resultados, "zips": zips, "problemas": problemas,
            "salida": out_dir}


OG_DESTINO = os.path.join(ROOT, "landing", "og.png")


def publicar_og(destino: str | None = None) -> str:
    """Renderiza la tarjeta de previsualización y la deja en `landing/`.

    A diferencia del resto del kit, este PNG **sí se versiona**: es un asset
    servido por el sitio (`https://<dominio>/landing/og.png`), no material que
    se baja a mano. Sin él, compartir el link en LinkedIn o WhatsApp no
    muestra ninguna previsualización.
    """
    destino = destino or OG_DESTINO
    banner = next(b for b in K.BANNERS if b["id"] == "og_card")
    carpeta = os.path.dirname(destino)
    os.makedirs(carpeta, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        resultados = renderizar(tmp, solo={banner["id"]})
        r = resultados[0]
        if r["problemas"]:
            raise RuntimeError(f"la tarjeta OG salió mal: {r['problemas']}")
        shutil.copyfile(os.path.join(tmp, r["archivo"]), destino)
    return destino


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", default=SALIDA_DEFAULT)
    ap.add_argument("--publicar-og", action="store_true",
                    help="además, actualiza landing/og.png (asset versionado)")
    args = ap.parse_args(argv)

    r = generar(args.salida)
    if args.publicar_og:
        print(f"[OK] tarjeta OG actualizada: "
              f"{os.path.relpath(publicar_og(), ROOT)}")
    for b in r["banners"]:
        estado = "OK " if not b["problemas"] else "MAL"
        print(f"[{estado}] {b['archivo']:44s} {b['titulo']}")
        for p in b["problemas"]:
            print(f"        · {p}")
    print(f"\nZIPs: {os.path.relpath(r['zips']['completo'], ROOT)} · "
          f"{os.path.relpath(r['zips']['banners'], ROOT)}")
    if r["problemas"]:
        print(f"\n[FALLA] {len(r['problemas'])} banner(s) con problemas. "
              "No publicar hasta corregir.")
        return 1
    print(f"[OK] {len(r['banners'])} banners validados, sin precios y con "
          f"el dominio {K.DOMINIO}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
