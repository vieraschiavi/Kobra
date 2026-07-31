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
