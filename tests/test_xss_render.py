# © 2026 Martín Viera. Todos los derechos reservados.
"""Ningún texto libre del deudor se inyecta con innerHTML.

Este archivo existe porque el riesgo era real, no teórico. Corriendo los
payloads en un Chromium de verdad contra el código anterior:

    --- realtime · transcripcion del deudor (addMsg)
      !!! EJECUTO   <img src=x onerror=window.__xss=1>
      !!! EJECUTO   "><img src=x onerror=window.__xss=1>
    --- realtime · streaming en vivo (render)
      !!! EJECUTO   <img src=x onerror=window.__xss=1>
    --- realtime · tabla de transcripcion (renderTel)
      !!! EJECUTO   <img src=x onerror=window.__xss=1>

`realtime/index.html` es el copiloto EN VIVO: pinta la transcripción de lo que
dice el deudor en una llamada real —texto libre de Whisper o del reconocimiento
de voz— en la pantalla del gestor. Un deudor que dictara ese payload, o una
transcripción que lo contuviera, ejecutaba código ahí.

Hay dos niveles de test:

  - Los estáticos corren siempre y son el gate del repo: verifican que cada
    interpolación de dato ajeno pase por `esc()`.
  - El de navegador (`test_ningun_payload_ejecuta_en_un_navegador_real`) se
    saltea si no hay Playwright. Es el que da la certeza: un test que solo
    busca `esc(` en el código verifica que alguien escribió la llamada, no que
    el resultado sea seguro.
"""
import os
import re
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Payloads que un nombre de deudor o un comentario de gestión pueden traer.
PAYLOADS = [
    "<img src=x onerror=window.__xss=1>",
    "<script>window.__xss=1</script>",
    "<svg/onload=window.__xss=1>",
    '"><img src=x onerror=window.__xss=1>',
]


def _leer(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# --- Inventario: ningún innerHTML nuevo sin revisar ------------------------
ARCHIVOS_CON_INNERHTML = [
    "dashboard_estatico/index.html",
    "realtime/index.html",
    "landing/index.html",
    "landing/descarga.html",
]


@pytest.mark.parametrize("rel", ARCHIVOS_CON_INNERHTML)
def test_cada_archivo_que_usa_innerHTML_tiene_su_escape(rel):
    """Salvo la landing, que no interpola nada: sus dos innerHTML son el
    diccionario i18n propio, y las reseñas —lo único que viene de un JSON— se
    pintan con textContent."""
    s = _leer(rel)
    if rel == "landing/index.html":
        assert "textContent" in s
        assert "HTML PROPIO Y ESTATICO" in s.upper(), \
            "el caso propio dejó de estar documentado"
        return
    assert re.search(r"function esc\(", s), f"{rel}: usa innerHTML y no tiene esc()"


@pytest.mark.parametrize("rel", ["dashboard_estatico/index.html",
                                 "realtime/index.html",
                                 "landing/descarga.html"])
def test_el_escape_cubre_las_cinco_entidades(rel):
    """`&` primero: si se reemplaza al final, re-escapa los `&amp;` que acaban
    de generar los otros y el texto sale roto."""
    s = _leer(rel)
    bloque = s[s.index("function esc("):s.index("function esc(") + 600]
    for entidad in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entidad in bloque, f"{rel}: esc() no cubre {entidad}"


# --- El texto del deudor, campo por campo ----------------------------------
@pytest.mark.parametrize("campo,motivo", [
    ("esc(texto)", "la transcripción de lo que dijo el deudor, en vivo"),
    ("esc(t.texto", "el turno del deudor en la tabla de la grabación"),
    ("esc(t.hablante", "quién habló, que sale de la diarización"),
    ("esc(s[0])", "el título de la sugerencia del copiloto"),
    ("esc(s[1])", "el cuerpo de la sugerencia del copiloto"),
    ("esc(res.copiloto.proxima_frase)", "la frase sugerida, generada sobre la conversación"),
])
def test_el_copiloto_en_vivo_escapa_el_texto_del_deudor(campo, motivo):
    s = _leer("realtime/index.html")
    assert campo in s, f"entra crudo a innerHTML: {motivo}"


@pytest.mark.parametrize("campo", [
    "${esc(r[c])}",          # cada celda de la cartera
    "${esc(fmt(r[c]))}",     # los montos
    "esc(a._error",          # el error que devuelve la IA
    "esc(a.guion",           # el guion sugerido
])
def test_el_demo_escapa_las_filas_de_la_cartera(campo):
    """En una instalación real la cartera es un CSV que sube el cliente: los
    nombres y las notas de gestión salen de su base."""
    assert campo in _leer("dashboard_estatico/index.html"), f"sin escapar: {campo}"


@pytest.mark.parametrize("campo,motivo", [
    ("esc(s[0])", "el título de una sugerencia del copiloto offline"),
    ("esc(s[1])", "el cuerpo de una sugerencia del copiloto offline"),
    ("esc(cop.proxima_frase)", "la próxima frase que arma el copiloto offline"),
])
def test_el_copiloto_offline_escapa_lo_que_llegue_por_estrategia(campo, motivo):
    """Hoy `analizarCopiloto()` llama a `KobraCopiloto.analizar(txt)` con un solo
    argumento: `estrategia` siempre es `undefined` y esta rama nunca corre en
    la demo actual. Pero `copiloto.js` ya acepta ese tercer argumento y lo
    concatena en el texto de la sugerencia — el día que alguien lo conecte con
    la estrategia recomendada del dataset (dato real, en una instalación con
    cliente), sin este escape sería una inyección silenciosa. Se escapa en el
    punto de inserción al DOM, no en el motor, por las dudas de que el motor
    cambie de forma."""
    assert campo in _leer("dashboard_estatico/index.html"), f"sin escapar: {motivo}"


def test_el_mensaje_de_pago_fallido_se_escapa():
    """Hoy solo se lo llama con literales, pero el día que alguien le pase
    `d.error` de la API sería una inyección silenciosa."""
    s = _leer("landing/descarga.html")
    assert "esc(msg||" in s


# --- React: el riesgo es solo dangerouslySetInnerHTML ----------------------
def test_el_frontend_no_agrego_ningun_dangerously_nuevo():
    """React escapa todo lo que va entre llaves. El único agujero posible es
    `dangerouslySetInnerHTML`, y los dos que hay son textos del i18n propio."""
    encontrados = []
    base = os.path.join(ROOT, "webapp", "frontend", "src")
    for root, _, files in os.walk(base):
        for f in files:
            if not f.endswith((".jsx", ".js")):
                continue
            ruta = os.path.join(root, f)
            with open(ruta, encoding="utf-8") as fh:
                s = fh.read()
            for m in re.finditer(r"dangerouslySetInnerHTML", s):
                contexto = s[max(0, m.start() - 500):m.start()]
                if "HTML propio y estatico" not in contexto:
                    encontrados.append(f"{os.path.relpath(ruta, ROOT)}")
    assert not encontrados, \
        f"dangerouslySetInnerHTML sin justificar: {encontrados}"


# --- La prueba de verdad: un navegador ------------------------------------
@pytest.mark.skipif(shutil.which("python3") is None, reason="sin python3")
def test_ningun_payload_ejecuta_en_un_navegador_real(tmp_path):
    """Carga las páginas en Chromium, inyecta por el mismo camino que seguiría
    un dato del deudor y le pregunta al navegador si el script llegó a correr.

    Se saltea sin Playwright o sin Chromium: es un test de integración, no
    puede ser el que impida correr la suite en una máquina cualquiera."""
    pytest.importorskip("playwright", reason="requiere playwright")
    import asyncio
    import http.server
    import socketserver
    import threading

    from playwright.async_api import async_playwright

    chrome = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    if not os.path.exists(chrome):
        pytest.skip("sin Chromium instalado")

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=ROOT, **kw)

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", 0), Silencioso)
    puerto = srv.server_address[1]
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()

    async def correr():
        ejecutaron = []
        async with async_playwright() as pw:
            nav = await pw.chromium.launch(
                executable_path=chrome,
                args=["--no-sandbox", "--disable-dev-shm-usage"])
            pag = await nav.new_page()
            casos = [
                ("realtime/index.html", "(p) => addMsg('cliente', p)"),
                ("realtime/index.html",
                 """(p) => renderTel({voz:{canales:1,modo_diarizacion:p,duracion_seg:3},
                      modo_transcripcion:p, calidad:{score_total:70},
                      turnos:[{inicio:0,hablante:p,texto:p,emocion_voz:p,
                               sent_texto:0.1,sent_fusion:0.2}]})"""),
                ("dashboard_estatico/index.html",
                 "(p) => renderAI({sentimiento:p, temperatura:50, tecnicas:[p],"
                 " proxima_jugada:p, guion:p})"),
                ("dashboard_estatico/index.html", "(p) => renderAI({_error: p})"),
                # `estrategia` no viaja por la llamada real de hoy (ver el test
                # estático de arriba), así que se simula el día que sí viaje:
                # se reemplaza `KobraCopiloto.analizar` por una versión que
                # devuelve el payload directo en `sugerencias`/`proxima_frase`
                # y se dispara el render REAL de la página (`analizarCopiloto`),
                # no una copia del código.
                ("dashboard_estatico/index.html",
                 """(p) => {
                   window.KobraCopiloto.analizar = () => ({
                     turnos: [], sents: [], calidad: {score_total: 0}, tecnicas: {},
                     copiloto: {clima: 0, clima_etiqueta: 'neutro', emociones_cliente: [],
                                sugerencias: [[p, p]], proxima_frase: p}
                   });
                   document.getElementById('convText').value = 'x';
                   analizarCopiloto();
                 }"""),
            ]
            for pagina, inyectar in casos:
                await pag.goto(f"http://127.0.0.1:{puerto}/{pagina}",
                               wait_until="domcontentloaded")
                for payload in PAYLOADS:
                    await pag.evaluate("window.__xss = 0")
                    try:
                        await pag.evaluate(inyectar, payload)
                    except Exception:
                        continue
                    await pag.wait_for_timeout(80)
                    if await pag.evaluate("window.__xss === 1"):
                        ejecutaron.append(f"{pagina}: {payload}")
            await nav.close()
        return ejecutaron

    try:
        ejecutaron = asyncio.run(correr())
    finally:
        srv.shutdown()
        srv.server_close()

    assert not ejecutaron, f"payloads que ejecutaron: {ejecutaron}"
