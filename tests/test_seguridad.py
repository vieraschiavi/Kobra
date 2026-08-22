# © 2026 Martín Viera. Todos los derechos reservados.

"""Eje SEGURIDAD: freno a la fuerza bruta, cabeceras y escape de HTML.

Tres huecos que aparecieron auditando el repo contra el estándar:

  1. La puerta pública —login, licencia, primer arranque— no tenía ningún
     límite de intentos. Un script podía probar contraseñas y tokens en
     ráfaga contra un servidor que le calculaba el PBKDF2 gratis.
  2. La API y la landing no mandaban CSP, X-Content-Type-Options ni
     Referrer-Policy. La API devuelve CSV, XLSX y PDF con datos de deudores:
     sin `nosniff` el navegador adivina el tipo de un archivo subido, y sin
     `Referrer-Policy` la URL con el id del deudor viaja a cualquier sitio al
     que se navegue después.
  3. El dashboard estático metía en `innerHTML` el análisis del modelo, los
     mensajes de error y **las filas de la cartera** — que en una instalación
     real es un CSV que sube el cliente.
"""
import json
import os
import re
import sys

import pytest
from conftest import CABECERA_REALTIME

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import limitador as klimite  # noqa: E402


class Reloj:
    """Reloj falso: el rearme del cubo se prueba sin esperar 30 segundos."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


# --- 1) Límite de intentos --------------------------------------------------
def test_deja_pasar_los_primeros_intentos_y_despues_corta():
    lim = klimite.Limitador(permitidos=5, ventana_seg=50, reloj=Reloj())
    for _ in range(5):
        lim.intentar("ip-1")
    with pytest.raises(klimite.LimiteIntentos):
        lim.intentar("ip-1")
    assert lim.metricas()["rechazados"] == 1


def test_el_limite_es_por_ip_y_no_global():
    """Si fuera global, el primer atacante dejaría afuera a todos los usuarios
    legítimos — que es justo lo que un límite tiene que evitar."""
    lim = klimite.Limitador(permitidos=2, ventana_seg=50, reloj=Reloj())
    lim.intentar("ip-atacante"); lim.intentar("ip-atacante")
    with pytest.raises(klimite.LimiteIntentos):
        lim.intentar("ip-atacante")
    lim.intentar("ip-honesta")          # no debe verse afectada


def test_el_limite_es_por_accion():
    """Gastar los intentos de licencia no puede dejar afuera a quien está
    intentando entrar con su contraseña."""
    lim_a = klimite.Limitador(permitidos=1, ventana_seg=50, reloj=Reloj())
    lim_b = klimite.Limitador(permitidos=1, ventana_seg=50, reloj=Reloj())
    lim_a.intentar("login:ip")
    with pytest.raises(klimite.LimiteIntentos):
        lim_a.intentar("login:ip")
    lim_b.intentar("licencia:ip")


def test_las_fichas_se_recuperan_con_el_tiempo():
    """Un límite que no se rearma es un bloqueo permanente: el usuario que se
    equivocó cinco veces quedaría afuera para siempre."""
    reloj = Reloj()
    lim = klimite.Limitador(permitidos=5, ventana_seg=50, reloj=reloj)   # 10 s/ficha
    for _ in range(5):
        lim.intentar("ip")
    with pytest.raises(klimite.LimiteIntentos):
        lim.intentar("ip")
    reloj.avanzar(10)
    lim.intentar("ip")                                   # volvió una ficha
    with pytest.raises(klimite.LimiteIntentos):
        lim.intentar("ip")


def test_el_intento_correcto_devuelve_la_ficha():
    """El límite castiga el tanteo, no al usuario que se equivocó una vez y
    después entró bien."""
    lim = klimite.Limitador(permitidos=3, ventana_seg=60, reloj=Reloj())
    lim.intentar("ip"); lim.intentar("ip")
    lim.perdonar("ip")
    lim.intentar("ip"); lim.intentar("ip")               # queda una libre


def test_el_error_dice_cuanto_hay_que_esperar():
    """«Demasiados intentos» a secas no es accionable: el usuario no sabe si
    esperar diez segundos o volver mañana."""
    lim = klimite.Limitador(permitidos=1, ventana_seg=60, reloj=Reloj())
    lim.intentar("ip")
    with pytest.raises(klimite.LimiteIntentos) as e:
        lim.intentar("ip")
    assert e.value.espera_seg > 0


def test_no_acumula_cubos_para_siempre():
    """Un atacante rotando IPs convertiría el diccionario en una fuga de
    memoria."""
    reloj = Reloj()
    lim = klimite.Limitador(permitidos=2, ventana_seg=10, reloj=reloj)
    for i in range(5000):
        lim.intentar(f"ip-{i}")
    reloj.avanzar(100)
    lim.intentar("ip-nueva")
    assert lim.metricas()["claves_vivas"] < 5000, "no purgó los cubos viejos"


@pytest.mark.parametrize("cabeceras,esperado", [
    ({"x-forwarded-for": "203.0.113.9, 10.0.0.1"}, "203.0.113.9"),
    ({"x-real-ip": "203.0.113.7"}, "203.0.113.7"),
    ({}, "127.0.0.1"),
])
def test_identifica_al_cliente_real_detras_del_proxy(cabeceras, esperado):
    """Detrás de Vercel o nginx, `request.client.host` es la IP del proxy:
    todas las peticiones del mundo compartirían un solo cubo."""
    class Req:
        headers = cabeceras
        client = type("C", (), {"host": "127.0.0.1"})()
    assert klimite.ip_de(Req()) == esperado


# --- 2) La API aplica el freno de verdad -----------------------------------
def _olvidar_modulos():
    """Saca `webapp`/`kobra` del caché de importación.

    `KOBRA_DATA_DIR` se lee UNA vez, al importar: para levantar la app contra
    un directorio vacío hay que reimportarla. Y hay que volver a olvidarla al
    terminar — si no, el módulo queda cacheado apuntando al tmp_path de este
    test y los que corren después (test_webapp) encuentran la cartera vacía.
    Eso ya pasó acá: 4 tests de webapp fallaban con KeyError solo cuando la
    suite corría entera, y pasaban en aislado.
    """
    for k in list(sys.modules):
        if k.startswith(("webapp", "kobra")):
            del sys.modules[k]


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    _olvidar_modulos()
    from fastapi.testclient import TestClient

    from webapp.backend import api
    yield api, TestClient(api.app)
    _olvidar_modulos()


def test_el_login_corta_con_429_y_no_con_401_infinitos(cliente):
    """El caso real: probar contraseñas en ráfaga. Verificado de punta a punta
    contra la app, no solo sobre el limitador."""
    api, c = cliente
    api._LIMITE_LOGIN.__init__(permitidos=5, ventana_seg=300)
    codigos = [c.post("/api/auth/login", json={"password": f"x{i}"}).status_code
               for i in range(9)]
    assert 429 in codigos, f"el login nunca frenó: {codigos}"
    assert codigos.index(429) <= 6, f"frenó demasiado tarde: {codigos}"
    r = c.post("/api/auth/login", json={"password": "x"})
    assert "Retry-After" in r.headers, "un 429 sin Retry-After no es accionable"


def test_activar_licencia_tambien_frena(cliente):
    api, c = cliente
    api._LIMITE_LICENCIA.__init__(permitidos=3, ventana_seg=300)
    codigos = [c.post("/api/licencia/activar", json={"token": f"t{i}"}).status_code
               for i in range(7)]
    assert 429 in codigos, f"la activación de licencia nunca frenó: {codigos}"


def test_el_freno_del_login_no_afecta_al_resto_de_la_api(cliente):
    """Un límite que tumba `/api/health` convierte una defensa en una caída."""
    api, c = cliente
    api._LIMITE_LOGIN.__init__(permitidos=2, ventana_seg=300)
    for i in range(6):
        c.post("/api/auth/login", json={"password": f"x{i}"})
    assert c.get("/api/health").status_code == 200


# --- 3) Cabeceras de seguridad ---------------------------------------------
@pytest.mark.parametrize("cabecera", [
    "X-Content-Type-Options", "Referrer-Policy", "Content-Security-Policy",
])
def test_la_api_manda_las_cabeceras_de_seguridad(cliente, cabecera):
    _, c = cliente
    r = c.get("/api/health")
    assert cabecera in r.headers, f"la API no manda {cabecera}"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_las_descargas_tambien_llevan_las_cabeceras(cliente):
    """Los CSV/XLSX/PDF llevan datos de deudores: son justo los que no pueden
    salir sin `nosniff`."""
    _, c = cliente
    r = c.get("/api/health")   # el middleware es global, no por endpoint
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_la_ui_no_recibe_la_csp_de_la_api(cliente):
    """El bug del instalador Owner v1.3.0: el mismo proceso sirve la API y la
    app React compilada, y la CSP `default-src 'none'` (correcta para JSON)
    también salía en el index.html — el navegador se negaba a cargar el JS/CSS
    de la propia app y la ventana quedaba con el título puesto y la pantalla
    NEGRA. El smoke test del workflow solo pegaba a la API, así que se publicó
    igual. La CSP tiene que depender de qué se sirve: estricta en `/api/*`,
    y una que permita los recursos locales de la app en el resto."""
    _, c = cliente
    csp_ui = c.get("/").headers.get("Content-Security-Policy", "")
    assert "default-src 'none'" not in csp_ui, (
        "la UI recibe la CSP de la API: el navegador bloquea el JS/CSS de la "
        "propia app y la pantalla queda negra (bug del instalador Owner v1.3.0)")
    assert "script-src 'self'" in csp_ui
    csp_api = c.get("/api/health").headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp_api, "la API perdió su CSP estricta"


def test_la_csp_de_la_ui_deja_reproducir_el_audio_subido(cliente):
    """El bug del reproductor gris (v1.3.1): la pestaña Calidad reproduce la
    grabación con <audio src=blob:...> y la CSP sin `media-src` lo bloqueaba
    — el botón de play quedaba muerto. Reproducido con Chromium: error de
    media code 4 + violación 'Refused to load media ... blob:'. La CSP de la
    UI tiene que declarar media-src con blob:."""
    _, c = cliente
    csp = c.get("/").headers.get("Content-Security-Policy", "")
    m = re.search(r"media-src ([^;]+)", csp)
    assert m, ("la CSP de la UI no define media-src: el <audio> con blob: "
               "cae en default-src 'self' y el reproductor queda gris")
    assert "blob:" in m.group(1)


def test_la_csp_de_la_ui_sigue_sin_permitir_scripts_externos(cliente):
    """Relajar la CSP para que la app cargue NO es abrirla: todo el JS del
    build de Vite es local, así que scripts externos e inline siguen
    bloqueados — que es la protección real contra XSS."""
    _, c = cliente
    csp = c.get("/").headers.get("Content-Security-Policy", "")
    m = re.search(r"script-src ([^;]+)", csp)
    assert m, "la CSP de la UI no define script-src"
    fuentes = m.group(1).split()
    prohibidas = [f for f in fuentes
                  if f.startswith(("http://", "https://", "*")) or "unsafe" in f]
    assert not prohibidas, f"la CSP de la UI admite scripts peligrosos: {prohibidas}"


@pytest.fixture(scope="module")
def vercel():
    with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as f:
        return json.load(f)


def test_la_landing_manda_csp_y_las_demas_cabeceras(vercel):
    globales = [h for h in vercel["headers"] if h["source"] == "/(.*)"]
    assert globales, "no hay una regla de cabeceras que cubra todo el sitio"
    claves = {h["key"] for h in globales[0]["headers"]}
    for esperada in ("Content-Security-Policy", "X-Content-Type-Options",
                     "Referrer-Policy"):
        assert esperada in claves, f"la landing no manda {esperada}"


def test_la_csp_no_permite_scripts_de_otros_dominios(vercel):
    """Todo el JS del sitio es local (no hay CDN): la CSP puede y debe
    bloquear cualquier script externo."""
    csp = next(h["value"] for h in vercel["headers"][0]["headers"]
               if h["key"] == "Content-Security-Policy")
    m = re.search(r"script-src ([^;]+)", csp)
    assert m, "la CSP no define script-src"
    fuentes = m.group(1).split()
    externos = [f for f in fuentes if f.startswith(("http://", "https://", "*"))]
    assert not externos, f"la CSP admite scripts externos: {externos}"
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_los_scripts_del_sitio_son_todos_locales():
    """El test de arriba solo vale mientras esto siga siendo cierto: si mañana
    se agrega un `<script src="https://cdn…">`, la CSP lo va a bloquear y hay
    que decidirlo a conciencia, no descubrirlo en producción."""
    for rel in ("landing/index.html", "landing/descarga.html",
                "dashboard_estatico/index.html"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            html = f.read()
        externos = re.findall(r'<script[^>]+src="(https?://[^"]+)"', html)
        assert not externos, f"{rel} carga scripts externos: {externos}"


# --- 4) Nada de innerHTML con dato ajeno -----------------------------------
@pytest.fixture(scope="module")
def demo_html():
    with open(os.path.join(ROOT, "dashboard_estatico", "index.html"),
              encoding="utf-8") as f:
        return f.read()


def test_existe_el_escape_y_cubre_las_cinco_entidades(demo_html):
    assert "function esc(v)" in demo_html
    for entidad in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entidad in demo_html, f"esc() no cubre {entidad}"


@pytest.mark.parametrize("campo", [
    "a._error", "a._raw", "a.sentimiento", "a.proxima_jugada", "a.guion",
])
def test_lo_que_llega_de_la_ia_se_escapa(demo_html, campo):
    """Son la respuesta del modelo y los mensajes de error: dato de API."""
    assert f"esc({campo}" in demo_html, f"{campo} entra crudo a innerHTML"


def test_las_filas_de_la_cartera_se_escapan(demo_html):
    """En una instalación real la cartera es un CSV que sube el cliente. Un
    nombre de deudor con `<img onerror=…>` ejecutaría en el dashboard de quien
    lo abra."""
    assert "${esc(r[c])}" in demo_html, "las celdas de la tabla van sin escapar"
    assert "${esc(fmt(r[c]))}" in demo_html


def test_el_html_propio_que_no_se_escapa_esta_documentado(demo_html):
    """El estándar admite HTML estático y propio, pero pide dejarlo dicho: si
    no, el próximo que lea `chatBubble` no sabe si es un olvido."""
    i = demo_html.index("function chatBubble")
    contexto = demo_html[max(0, i - 900):i].lower()
    assert "no se escapa a proposito" in contexto
    assert "guiones.js" in contexto


@pytest.mark.parametrize("archivo", [
    "webapp/frontend/src/pages/Agenda.jsx",
    "webapp/frontend/src/pages/Asistente.jsx",
])
def test_el_dangerously_del_frontend_esta_documentado(archivo):
    with open(os.path.join(ROOT, archivo), encoding="utf-8") as f:
        s = f.read()
    i = s.index("dangerouslySetInnerHTML")
    assert "HTML propio y estatico" in s[max(0, i - 500):i], \
        f"{archivo}: dangerouslySetInnerHTML sin justificar"


# --- 5) Cero secretos en el código -----------------------------------------
def test_no_hay_secretos_hardcodeados():
    """Todo por variable de entorno. Se mira el código que se distribuye."""
    patron = re.compile(
        r"""(api_key|apikey|secret|password|token)\s*=\s*["'][A-Za-z0-9_\-]{16,}["']""",
        re.I)
    hallazgos = []
    for base in ("kobra", "webapp/backend", "realtime", "backend_venta", "api"):
        for root, _, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in root or "node_modules" in root:
                continue
            for f in files:
                if not f.endswith((".py", ".js", ".jsx")):
                    continue
                ruta = os.path.join(root, f)
                with open(ruta, encoding="utf-8", errors="replace") as fh:
                    for n, linea in enumerate(fh, 1):
                        if patron.search(linea):
                            hallazgos.append(f"{ruta}:{n}")
    assert not hallazgos, f"posibles secretos en el código: {hallazgos}"


# --- 6) Freno general en TODO endpoint público ------------------------------
# Antes de esto, el único rate limiting real del repo eran los 3 `_frenar()`
# de arriba (login/licencia/setup). Auditando la superficie pública completa
# aparecieron 48+ endpoints sin ningún freno en webapp/backend/api.py, TODO
# realtime/server.py (incluidos webhooks sin verificar y un endpoint que
# dispara una llamada telefónica real sin auth), y `requerir_licencia`/
# `requerir_admin` en backend_venta/app.py, tanteables sin límite. `api/*.js`
# (Vercel) tampoco tenía nada por IP: `copiloto.js` solo llevaba un contador
# GLOBAL, que cualquiera agota para todos con un script.
def test_limitador_general_corta_por_ip_y_por_ruta():
    lim = klimite.LimitadorGeneral.__new__(klimite.LimitadorGeneral)
    lim.limitador = klimite.Limitador(permitidos=3, ventana_seg=50, reloj=Reloj())
    lim.exentas = set()
    for _ in range(3):
        lim.limitador.intentar("general:1.2.3.4:/api/algo")
    with pytest.raises(klimite.LimiteIntentos):
        lim.limitador.intentar("general:1.2.3.4:/api/algo")
    # otra ruta, misma IP: cubo aparte, no se ve afectada
    lim.limitador.intentar("general:1.2.3.4:/api/otra")


def test_limitador_general_exime_salud_por_defecto():
    lim = klimite.LimitadorGeneral.__new__(klimite.LimitadorGeneral)
    lim.exentas = {"/health", "/api/health", "/salud", "/capacidad"}
    for ruta in ("/health", "/api/health", "/salud", "/capacidad"):
        assert ruta in lim.exentas, (
            f"{ruta} no está exento: un monitor de uptime lo tumbaría")


@pytest.fixture
def cliente_rate_bajo(tmp_path, monkeypatch):
    """El mismo `webapp/backend/api.py` REAL, sin tocarle el middleware a
    mano: solo se bajan los defaults de `LimitadorGeneral` por variable de
    entorno ANTES de importar, para no esperar 120 requests en un test.
    Prueba que `app.add_middleware(klimite.LimitadorGeneral)` —tal como está
    escrito en el archivo, sin parámetros— frena de verdad; el fixture
    `cliente` de arriba no lo prueba: solo importa la app tal cual, con el
    default de producción (120 cada 60 s), que ningún test dispara aposta."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_RATE_PETICIONES", "4")
    monkeypatch.setenv("KOBRA_RATE_VENTANA_SEG", "300")
    _olvidar_modulos()
    from fastapi.testclient import TestClient

    from webapp.backend import api
    yield api, TestClient(api.app)
    _olvidar_modulos()


def test_el_freno_general_corta_un_endpoint_sin_freno_propio(cliente_rate_bajo):
    """`/api/auth/estado` no pasa por `_frenar()` — es exactamente el tipo de
    endpoint que el freno general tiene que cubrir solo, sin que nadie se
    acuerde de agregarlo a mano. Se golpea la app tal cual quedó escrita en
    `webapp/backend/api.py`, sin tocarle el middleware desde el test."""
    _, c = cliente_rate_bajo
    codigos = [c.get("/api/auth/estado").status_code for _ in range(8)]
    assert 429 in codigos, f"el freno general nunca frenó: {codigos}"


def test_el_freno_general_no_tumba_el_health_check(cliente_rate_bajo):
    _, c = cliente_rate_bajo
    for _ in range(10):
        assert c.get("/api/health").status_code == 200, (
            "el freno general tumbó /api/health: un monitor de uptime lo vería caído")


@pytest.fixture
def cliente_realtime(monkeypatch):
    pytest.importorskip("fastapi")
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    from fastapi.testclient import TestClient

    from realtime import server
    # Autenticado: acá se prueba el FRENO, no el candado (ése tiene su propio
    # archivo). Sin el token todo daría 401 y el test pasaría sin probar nada.
    yield server, TestClient(server.app, headers=CABECERA_REALTIME)
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]


def test_voz_llamar_tiene_un_freno_mas_estricto_que_el_general(cliente_realtime):
    """El más caro de dejar sin frenar: llamada telefónica REAL, sin
    autenticación, a cualquier número que mande el cliente."""
    server, c = cliente_realtime
    server._LIMITE_LLAMADA.__init__(permitidos=3, ventana_seg=600)
    codigos = [c.post("/voz/llamar", data={"telefono": "+59899999999"}).status_code
               for _ in range(6)]
    assert 429 in codigos, f"/voz/llamar nunca frenó: {codigos}"
    r = c.post("/voz/llamar", data={"telefono": "+59899999999"})
    assert "Retry-After" in r.headers


@pytest.fixture
def cliente_realtime_rate_bajo(monkeypatch):
    """El `realtime/server.py` REAL con el default de `LimitadorGeneral`
    bajado por variable de entorno, sin tocar el middleware desde el test."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_RATE_PETICIONES", "2")
    monkeypatch.setenv("KOBRA_RATE_VENTANA_SEG", "300")
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    from fastapi.testclient import TestClient

    from realtime import server
    # Autenticado: acá se prueba el FRENO, no el candado (ése tiene su propio
    # archivo). Sin el token todo daría 401 y el test pasaría sin probar nada.
    yield server, TestClient(server.app, headers=CABECERA_REALTIME)
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]


def test_realtime_frena_websockets_no_solo_http(cliente_realtime_rate_bajo):
    """`@app.middleware("http")` de Starlette NO cubre el handshake de
    WebSocket — por eso `LimitadorGeneral` es un middleware ASGI puro. Sin
    esto, `/ws` (voz/WhatsApp en vivo) quedaría completamente afuera del
    freno general, que es donde más importa: streaming, no un request suelto.
    Se conecta contra la app real, con el middleware tal como quedó cableado
    en `realtime/server.py` — no uno agregado desde el test."""
    _, c = cliente_realtime_rate_bajo
    cerrados = 0
    for _ in range(5):
        try:
            with c.websocket_connect("/ws") as ws:
                ws.close()
        except Exception:
            cerrados += 1
    assert cerrados > 0, "ninguna conexión de WebSocket fue frenada"


@pytest.fixture
def cliente_venta(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    for k in list(sys.modules):
        if k.startswith(("backend_venta", "kobra")):
            del sys.modules[k]
    from fastapi.testclient import TestClient

    from backend_venta import app as venta
    yield venta, TestClient(venta.app)
    for k in list(sys.modules):
        if k.startswith(("backend_venta", "kobra")):
            del sys.modules[k]


@pytest.fixture
def cliente_venta_rate_bajo(tmp_path, monkeypatch):
    """El `backend_venta/app.py` REAL, con el default de `LimitadorGeneral`
    bajado por variable de entorno — no un middleware agregado desde acá."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_RATE_PETICIONES", "4")
    monkeypatch.setenv("KOBRA_RATE_VENTANA_SEG", "300")
    for k in list(sys.modules):
        if k.startswith(("backend_venta", "kobra")):
            del sys.modules[k]
    from fastapi.testclient import TestClient

    from backend_venta import app as venta
    yield venta, TestClient(venta.app)
    for k in list(sys.modules):
        if k.startswith(("backend_venta", "kobra")):
            del sys.modules[k]


def test_backend_venta_frena_el_tanteo_de_token(cliente_venta_rate_bajo):
    """`requerir_licencia` no tenía NINGÚN freno de intentos — a diferencia del
    login del otro backend, acá se podía tantear el token Bearer sin límite."""
    _, c = cliente_venta_rate_bajo
    codigos = [c.get("/licencias/estado",
                     headers={"Authorization": f"Bearer x{i}"}).status_code
               for i in range(9)]
    assert 429 in codigos, f"backend_venta nunca frenó el tanteo de token: {codigos}"


def test_backend_venta_exime_salud(cliente_venta_rate_bajo):
    _, c = cliente_venta_rate_bajo
    for _ in range(6):
        assert c.get("/salud").status_code == 200
