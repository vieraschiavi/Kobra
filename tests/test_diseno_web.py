# © 2026 Martín Viera. Todos los derechos reservados.

"""Eje DISEÑO: lo que el navegador y el buscador necesitan para no penalizar.

Dos cosas aparecieron auditando el repo contra el estándar:

  1. `landing/index.html` —la página más visitada— **no tenía `<html>`**. Ni
     `<!DOCTYPE>`, ni `lang`, ni `viewport`. El navegador la levanta igual, en
     modo quirks, pero un lector de pantalla no sabe en qué idioma leerla y el
     teléfono la renderiza a ancho de escritorio y después la achica: el texto
     queda ilegible. Lighthouse penaliza las dos cosas.
  2. `Cartera.jsx` no pintaba nada mientras cargaba: pantalla en blanco, sin
     spinner ni texto. El estándar pide que nada quede en blanco sin explicar.

Los meta de compartir (og/twitter) ya estaban en la landing, el demo y la
página de descarga; faltaban en la webapp, que también se comparte por link.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGINAS = [
    "landing/index.html",
    "landing/descarga.html",
    "dashboard_estatico/index.html",
    "webapp/frontend/index.html",
]


def _html(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _marcado(rel):
    """El HTML sin comentarios ni cuerpos de <script>/<style>.

    Hace falta porque estos archivos generan marcado desde JavaScript: un
    `ov.innerHTML='<div ...>'` dentro de un <script> en el <head> no es
    contenido en el head, es una cadena. Y un comentario que explica un riesgo
    de XSS puede contener un `<img onerror=...>` de ejemplo, que tampoco es una
    imagen real. Analizar el texto crudo daba las dos cosas como hallazgos.
    """
    html = _html(rel)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", html,
                  flags=re.S | re.I)
    html = re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", html,
                  flags=re.S | re.I)
    return html


# --- Estructura del documento ----------------------------------------------
@pytest.mark.parametrize("rel", PAGINAS)
def test_cada_pagina_declara_su_idioma(rel):
    """Sin `lang`, un lector de pantalla lee el castellano con fonética
    inglesa. Es el fallo `html-has-lang` de Lighthouse."""
    html = _html(rel)
    m = re.search(r"<html[^>]*\blang=[\"']([a-zA-Z-]+)[\"']", html)
    assert m, f"{rel}: <html> sin lang"
    assert m.group(1).lower().startswith(("es", "pt", "en")), m.group(1)


@pytest.mark.parametrize("rel", PAGINAS)
def test_cada_pagina_tiene_viewport(rel):
    """Sin viewport, el teléfono renderiza a ancho de escritorio y encoge todo.
    Es la penalización más grande de Lighthouse en móvil."""
    html = _html(rel)
    m = re.search(r'<meta[^>]+name=["\']viewport["\'][^>]*>', html, re.I)
    assert m, f"{rel}: sin meta viewport"
    assert "width=device-width" in m.group(0), m.group(0)


@pytest.mark.parametrize("rel", PAGINAS)
def test_cada_pagina_arranca_con_doctype(rel):
    """Sin `<!DOCTYPE html>` el navegador entra en modo quirks y el CSS se
    interpreta con reglas de hace veinte años."""
    assert _html(rel).lstrip().lower().startswith("<!doctype html>"), \
        f"{rel}: sin DOCTYPE"


@pytest.mark.parametrize("rel", PAGINAS)
def test_cada_pagina_tiene_favicon(rel):
    assert re.search(r'<link[^>]+rel=["\'][^"\']*icon', _html(rel), re.I), \
        f"{rel}: sin favicon"


@pytest.mark.parametrize("rel", PAGINAS)
def test_el_head_y_el_body_no_estan_mezclados(rel):
    """Agregar `<head>`/`<body>` a mano es fácil de hacer mal: una etiqueta de
    contenido dentro del head, o un `<meta>` suelto después del `<body>`."""
    html = _marcado(rel)
    if "</head>" not in html:
        pytest.skip(f"{rel} no separa head/body explícitamente")
    cabeza = html[:html.index("</head>")]
    permitidas = {"!doctype", "html", "head", "meta", "title", "link", "style",
                  "script", "base", "noscript"}
    intrusas = {t.lower() for t in re.findall(r"<(\w+)", cabeza)} - permitidas
    assert not intrusas, f"{rel}: contenido dentro de <head>: {sorted(intrusas)}"

    cuerpo = html[html.index("</head>"):]
    tardias = {t.lower() for t in re.findall(r"<(meta|title|link)\b", cuerpo, re.I)}
    assert not tardias, f"{rel}: {sorted(tardias)} después de </head>"


# --- Compartir el link ------------------------------------------------------
@pytest.mark.parametrize("rel", PAGINAS)
@pytest.mark.parametrize("etiqueta", [
    'name="description"', 'property="og:title"', 'property="og:description"',
    'property="og:image"', 'name="twitter:card"',
])
def test_cada_pagina_se_puede_compartir_con_vista_previa(rel, etiqueta):
    """Sin estas etiquetas el link se pega como texto pelado."""
    html = _html(rel).replace("'", '"')
    assert etiqueta in html, f"{rel}: falta {etiqueta}"


@pytest.mark.parametrize("rel", PAGINAS)
def test_la_imagen_de_vista_previa_es_una_url_absoluta(rel):
    """Ningún scraper (LinkedIn, WhatsApp, X) resuelve una ruta relativa: la
    vista previa saldría sin imagen."""
    html = _html(rel).replace("'", '"')
    m = re.search(r'property="og:image"[^>]*content="([^"]+)"', html) or \
        re.search(r'content="([^"]+)"[^>]*property="og:image"', html)
    assert m, f"{rel}: sin og:image"
    assert m.group(1).startswith("http"), f"{rel}: og:image relativa: {m.group(1)}"


# --- Accesibilidad de las imágenes -----------------------------------------
@pytest.mark.parametrize("rel", PAGINAS)
def test_todas_las_imagenes_tienen_alt(rel):
    faltan = [t for t in re.findall(r"<img\b[^>]*>", _marcado(rel), re.I)
              if not re.search(r"\balt=", t)]
    assert not faltan, f"{rel}: <img> sin alt: {faltan}"


@pytest.mark.parametrize("rel", PAGINAS)
def test_ningun_alt_esta_vacio_ni_dice_imagen(rel):
    """`alt=""` es válido solo para decoración pura, y `alt="imagen"` no le
    dice nada a nadie."""
    inutiles = []
    for t in re.findall(r"<img\b[^>]*>", _marcado(rel), re.I):
        m = re.search(r'alt="([^"]*)"', t)
        if m and m.group(1).strip().lower() in ("", "imagen", "image", "foto", "logo"):
            inutiles.append(t)
    assert not inutiles, f"{rel}: alt sin contenido útil: {inutiles}"


# --- Nada en blanco sin explicación ----------------------------------------
PAGINAS_REACT = [
    "webapp/frontend/src/pages/Cartera.jsx",
    "webapp/frontend/src/pages/Agenda.jsx",
    "webapp/frontend/src/pages/Gestores.jsx",
]


@pytest.mark.parametrize("rel", PAGINAS_REACT)
def test_las_pantallas_que_piden_datos_muestran_que_estan_cargando(rel):
    """`Cartera.jsx` arrancaba con `datos = null` y no pintaba nada hasta que
    llegaba la respuesta: pantalla en blanco, sin spinner ni texto, y sin
    forma de distinguirla de un error."""
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        s = f.read()
    assert re.search(r"!datos && !error|!d && !error", s), \
        f"{rel}: no hay estado de carga visible"


@pytest.mark.parametrize("rel", PAGINAS_REACT)
def test_las_pantallas_muestran_el_error_en_vez_de_tragarselo(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        s = f.read()
    assert "{error}" in s, f"{rel}: el error no se muestra"
    assert ".catch(" in s, f"{rel}: la promesa no captura el fallo"


def test_la_app_avisa_si_el_navegador_no_tiene_javascript():
    """Sin JS el `<div id=root>` queda vacío: pantalla en blanco absoluta y el
    usuario no tiene forma de saber qué pasó."""
    html = _html("webapp/frontend/index.html")
    assert "<noscript>" in html
    assert "JavaScript" in html


# --- La app en un celular ---------------------------------------------------
# Todo esto salió de medir con un navegador de verdad: doce pantallas a diez
# anchos distintos, de 320 a 1440px. El defecto era siempre el mismo —un ancho
# mínimo pensado para el escritorio— y se veía siempre igual: la página entera
# corrida al costado, con el contenido moviéndose al hacer scroll vertical.
_THEME = "webapp/frontend/src/theme.css"


def _css():
    with open(os.path.join(ROOT, _THEME), encoding="utf-8") as f:
        return f.read()


def _bloques_media_angostos(css):
    """Los cuerpos de los `@media (max-width: …)` que apuntan a pantalla
    chica, concatenados. Sirve para preguntar "¿esto se corrige en móvil?"."""
    cuerpos = []
    for m in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", css):
        if int(m.group(1)) > 900:
            continue
        i, prof = m.end(), 1
        while i < len(css) and prof:
            prof += (css[i] == "{") - (css[i] == "}")
            i += 1
        cuerpos.append(css[m.end():i])
    return "\n".join(cuerpos)


def test_la_barra_lateral_se_colapsa_en_pantalla_chica():
    """232px de barra fija sobre 390px de pantalla dejan 158px de contenido:
    no entra nada. En móvil queda un rail de iconos."""
    movil = _bloques_media_angostos(_css())
    assert ".sidebar" in movil, "ninguna media query angosta toca .sidebar"
    assert re.search(r"\.sidebar\s*\{[^}]*width:\s*(?:[1-9]\d?|1\d\d)px", movil), \
        "la barra lateral no se angosta en pantalla chica"
    assert ".nav-item .txt" in movil, \
        "el texto de la navegación no se oculta: no hay lugar para él"


def test_los_botones_de_navegacion_tienen_nombre_accesible():
    """Corolario del test anterior: si el `.txt` se oculta por CSS, el botón se
    queda sin contenido y un lector de pantalla lo anuncia como "botón" a
    secas. El nombre tiene que estar en un atributo, no en el texto."""
    with open(os.path.join(ROOT, "webapp/frontend/src/App.jsx"), encoding="utf-8") as f:
        app = f.read()
    nav = app[app.index("function Sidebar"):]
    nav = nav[:nav.index("\n}\n")]
    for boton in re.finditer(r"<button[^>]*className=\{?\"?nav-item", nav):
        # El `>` que cierra la etiqueta no sirve de corte: los `onClick` traen
        # funciones flecha (`=>`) adentro. El primer `<span` sí — es el icono,
        # el primer hijo de todos estos botones.
        resto = nav[boton.start():boton.start() + 500]
        atributos = resto.split("<span")[0]
        assert "aria-label=" in atributos, \
            "un botón de la barra lateral no tiene aria-label:\n" + atributos[:120]


@pytest.mark.parametrize("rejilla", ["charts-grid", "grid-2", "kpi-grid"])
def test_las_rejillas_anchas_tienen_salida_en_movil(rejilla):
    """`repeat(auto-fit, minmax(380px, 1fr))` en una pantalla con ~310px de
    ancho útil desborda 70px. El mínimo tiene que poder achicarse: `minmax(0,
    …)` o `minmax(min(Npx, 100%), …)`. Sin el 0 explícito el mínimo implícito
    de una pista de grilla es `auto`, y vuelve a desbordar."""
    css = _css()
    anchos = re.findall(rf"\.{rejilla}\s*\{{[^}}]*minmax\((\d+)px", css)
    if not anchos or max(int(a) for a in anchos) < 340:
        return                      # ya entra en cualquier celular
    movil = _bloques_media_angostos(css)
    regla = re.search(rf"\.{rejilla}\s*\{{[^}}]*grid-template-columns:([^;]+);", movil)
    assert regla, f".{rejilla} usa un mínimo de {max(anchos)}px y no lo corrige en móvil"
    assert "minmax(0" in regla.group(1) or "min(" in regla.group(1), \
        f".{rejilla} en móvil sigue con un mínimo rígido: {regla.group(1).strip()}"


# Las pantallas sueltas: no viven dentro del layout con barra lateral y por
# eso no llevan el encabezado común.
_SIN_LAYOUT = {"Login.jsx", "Activacion.jsx", "PortalPago.jsx"}


def test_todas_las_pantallas_usan_el_mismo_encabezado():
    """`CuentasPorCobrar.jsx` traía un `<h2>` suelto con estilos en línea: otro
    tamaño de título y otro margen que sus once hermanas, en la misma app."""
    import glob
    sueltas = []
    for ruta in sorted(glob.glob(os.path.join(ROOT, "webapp/frontend/src/pages/*.jsx"))):
        if os.path.basename(ruta) in _SIN_LAYOUT:
            continue
        with open(ruta, encoding="utf-8") as f:
            if "page-title" not in f.read():
                sueltas.append(os.path.basename(ruta))
    assert not sueltas, ("estas pantallas no usan la clase `page-title` del "
                         "resto de la app: " + ", ".join(sueltas))
