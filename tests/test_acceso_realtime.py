# © 2026 Martín Viera. Todos los derechos reservados.

"""El servicio de tiempo real no le abre la puerta a cualquiera.

Antes sí. `realtime/server.py` tenía freno por IP y candado de plan —dos cosas
que no son autenticación— y cualquiera que llegara al puerto tenía:

  * `GET /brief/KB-100000`, `KB-100001`, … : monto de la deuda, probabilidad
    de pago y **el descuento autorizado**, con identificadores correlativos.
    Un `for` de tres líneas se baja la cartera entera de una financiera.
  * `POST /voz/llamar`: una llamada telefónica de verdad, a cualquier número.
  * `POST /voz/turno`: postear turnos inventados en una llamada EN CURSO, con
    el `call` a la vista en la URL, y que quede registrado como lo que dijo
    el deudor.

Y no alcanzaba con "está en la red interna": el servicio tiene que ser
alcanzable desde afuera para que Twilio postee los webhooks, así que el mismo
túnel que deja entrar a Twilio deja entrar a cualquiera.

Este archivo prueba las dos credenciales que ahora hay —el token de operación
y la firma de Twilio— y, sobre todo, que la lista sea de lo ABIERTO: un
endpoint nuevo nace cerrado aunque nadie se acuerde de nada.
"""
import sys

import pytest
from conftest import CABECERA_REALTIME, TOKEN_REALTIME, firma_twilio

from realtime import acceso

AUTH_TWILIO = "auth-token-de-twilio-de-prueba"
BASE = "https://kobra.example.com"


@pytest.fixture()
def cli(monkeypatch):
    """El `realtime/server.py` real, sin credenciales puestas en el cliente."""
    pytest.importorskip("fastapi")
    previos = dict(sys.modules)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TWILIO)
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    from fastapi.testclient import TestClient

    from realtime import server
    yield TestClient(server.app)
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    sys.modules.update(previos)


# ---------------------------------------------------------------------------
# 1) La cartera no sale sin credencial
# ---------------------------------------------------------------------------
def test_la_cartera_no_se_baja_sin_token(cli):
    """El peor de los agujeros: los ids son correlativos."""
    r = cli.get("/brief/KB-100000")
    assert r.status_code == 401, "la cartera del cliente sale por HTTP sin auth"
    assert r.json()["motivo"] == "sin_token"
    # Y el 401 no filtra si el deudor existe o no — mismo código para los dos.
    assert cli.get("/brief/KB-999999").status_code == 401


def test_con_token_la_cartera_sí_sale(cli):
    """El candado no puede ser un muro para el que sí tiene la credencial."""
    r = cli.get("/brief/KB-100000", headers=CABECERA_REALTIME)
    assert r.status_code in (200, 404), r.text   # 404 si no se generó el dataset


@pytest.mark.parametrize("ruta", ["/transcribe", "/analizar_audio",
                                  "/copiloto_audio", "/voz/llamar"])
def test_lo_que_gasta_plata_pide_token(cli, ruta):
    """Estos tres procesan audio con la API del cliente y el cuarto marca un
    teléfono. Sin token, cualquiera le gasta la cuenta al cliente."""
    assert cli.post(ruta).status_code == 401


def test_el_websocket_del_copiloto_tambien_pide_token(cli):
    """El candado es middleware ASGI y no `@app.middleware("http")` justamente
    por esto: el decorador HTTP de Starlette no envuelve el handshake de
    WebSocket, y `/ws` y `/ws_audio` —por donde pasa el audio de las llamadas—
    quedarían afuera."""
    from starlette.websockets import WebSocketDisconnect
    for ruta in ("/ws", "/ws_audio"):
        with pytest.raises(WebSocketDisconnect):
            with cli.websocket_connect(ruta) as ws:
                ws.receive()


def test_con_token_el_websocket_abre(cli):
    with cli.websocket_connect(f"/ws?t={TOKEN_REALTIME}"):
        pass


# ---------------------------------------------------------------------------
# 2) Formas de presentar el token
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("como", ["bearer", "cabecera", "query"])
def test_las_tres_formas_de_traer_el_token(cli, como):
    """Tres clientes distintos: el CTI manda Authorization, una integración
    que no quiere tocar esa cabecera manda la nuestra, y una página se abre
    desde un link con `?t=`."""
    kw = {"bearer": {"headers": {"Authorization": f"Bearer {TOKEN_REALTIME}"}},
          "cabecera": {"headers": CABECERA_REALTIME},
          "query": {}}[como]
    ruta = f"/brief/X?t={TOKEN_REALTIME}" if como == "query" else "/brief/X"
    assert cli.get(ruta, **kw).status_code != 401


def test_abrir_con_t_deja_cookie_para_los_fetch_siguientes(cli):
    """La página se abre una vez con `?t=` y después hace sus `fetch` sin
    arrastrar el token en cada URL — donde queda en el historial del navegador
    y en el log de cualquier proxy."""
    r = cli.get(f"/llamar?t={TOKEN_REALTIME}")
    assert r.status_code == 200
    assert r.cookies.get("kobra_rt") == TOKEN_REALTIME
    assert cli.get("/brief/X").status_code != 401, "la cookie no sirvió de nada"


def test_un_token_parecido_no_entra(cli):
    for malo in (TOKEN_REALTIME[:-1], TOKEN_REALTIME + "x", "", "null",
                 TOKEN_REALTIME.upper()):
        r = cli.get("/brief/X", headers={"X-Kobra-Token": malo})
        assert r.status_code == 401, f"entró con {malo!r}"


# ---------------------------------------------------------------------------
# 3) Lo que queda abierto, y por qué
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ruta", ["/health", "/capacidad"])
def test_el_monitoreo_sigue_entrando(cli, ruta):
    """Pedirle token al health-check apaga las alertas justo cuando algo anda
    mal, y no expone ningún dato del cliente."""
    assert cli.get(ruta).status_code == 200


def test_una_ruta_nueva_nace_cerrada():
    """La propiedad que importa: la lista es de lo ABIERTO. Un endpoint que se
    agregue mañana y del que nadie se acuerde pide token igual."""
    assert not acceso.autorizado("/endpoint/que/nadie/penso", {}, {}, {})


def test_las_paginas_estaticas_no_filtran_nada(cli):
    """`/` y `/llamar` se dejan abiertas para no devolver un 401 en blanco que
    no le dice nada a nadie. Son HTML sin datos: lo que piden después, sí pide
    token."""
    for ruta in ("/", "/llamar"):
        assert cli.get(ruta).status_code == 200


# ---------------------------------------------------------------------------
# 4) Los webhooks de Twilio: firma, no token
# ---------------------------------------------------------------------------
def test_el_webhook_de_voz_sin_firma_no_abre_sesion(cli):
    """Sin esto, cualquiera abre conversaciones a nombre de deudores ajenos y
    las deja registradas como gestiones reales en la base del cliente."""
    r = cli.post("/voz/entrante", data={"CallSid": "CA1"})
    assert r.status_code == 403
    assert "Hangup" in r.text, "corta con TwiML válido, no con un error crudo"


def test_el_webhook_de_voz_con_firma_de_twilio_pasa(cli):
    form = {"CallSid": "CA-ok", "From": "+59899000000"}
    r = cli.post("/voz/entrante", data=form,
                 headers=firma_twilio(f"{BASE}/voz/entrante", form, AUTH_TWILIO))
    assert r.status_code == 200, r.text


def test_no_se_puede_meter_un_turno_en_una_llamada_ajena(cli):
    """El `call` va en la URL, a la vista. Sin firma, un tercero postea el
    turno que quiera y el resultado de la negociación —promesa, monto,
    descuento aceptado— queda persistido como si lo hubiera dicho el deudor."""
    r = cli.post("/voz/turno?call=CA-ok",
                 data={"SpeechResult": "acepto pagar cien pesos"})
    assert r.status_code == 403


def test_una_firma_de_otra_url_no_sirve(cli):
    """La firma es sobre la URL exacta: sin eso, una firma capturada de un
    webhook viejo revalida cualquier otro."""
    form = {"CallSid": "CA-ok"}
    ajena = firma_twilio(f"{BASE}/voz/turno?call=OTRA", form, AUTH_TWILIO)
    assert cli.post("/voz/entrante", data=form, headers=ajena).status_code == 403


def test_sin_TWILIO_AUTH_TOKEN_se_falla_cerrado(monkeypatch):
    """No poder verificar no puede significar aceptar. Y no rompe a nadie: sin
    ese token no se pueden hacer llamadas de todos modos."""
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    assert not acceso.verificar_twilio("https://x/y", {}, "cualquier-firma")


def test_la_firma_se_arma_como_la_documenta_twilio():
    """URL completa + pares clave/valor ORDENADOS POR CLAVE y concatenados sin
    separador, HMAC-SHA1 con el auth token, base64.

    Se comprueba contra el algoritmo escrito acá aparte, no contra una
    constante: un vector de prueba de Twilio anotado de memoria puede estar
    mal, y un test que compara contra un número inventado no prueba nada.
    Lo que se protege es la forma exacta del string firmado — si el día de
    mañana alguien saca el `sorted` o le mete un separador, en producción el
    efecto es que NINGÚN webhook legítimo pasa y las llamadas se cortan solas.
    """
    import base64
    import hashlib
    import hmac

    url = "https://kobra.example.com/voz/turno?call=CA9"
    params = {"To": "+18005551212", "CallSid": "CA9", "Digits": "1234",
              "From": "+59899000000"}
    secreto = "12345678901234567890123456789012"

    base = url + "".join(k + params[k] for k in sorted(params))
    a_mano = base64.b64encode(
        hmac.new(secreto.encode(), base.encode(), hashlib.sha1).digest()).decode()
    assert acceso.firma_esperada(url, params, secreto) == a_mano


def test_el_orden_en_que_llegan_los_campos_no_cambia_la_firma():
    """El error clásico: concatenar en el orden del diccionario en vez de
    ordenado por clave. Anda en la máquina del que lo escribió y falla contra
    Twilio, que ordena siempre."""
    url = "https://kobra.example.com/voz/entrante"
    uno = {"A": "1", "B": "2", "C": "3"}
    otro = {"C": "3", "A": "1", "B": "2"}
    secreto = "12345678901234567890123456789012"
    assert (acceso.firma_esperada(url, uno, secreto)
            == acceso.firma_esperada(url, otro, secreto))


def test_cambiar_un_valor_o_la_url_cambia_la_firma():
    """Si no, la firma no está firmando nada."""
    s = "12345678901234567890123456789012"
    base = acceso.firma_esperada("https://k/x", {"monto": "100"}, s)
    assert acceso.firma_esperada("https://k/x", {"monto": "999"}, s) != base
    assert acceso.firma_esperada("https://k/y", {"monto": "100"}, s) != base
    assert acceso.firma_esperada("https://k/x", {"monto": "100"}, s + "9") != base


# ---------------------------------------------------------------------------
# 5) El token existe sin que nadie lo configure
# ---------------------------------------------------------------------------
def test_se_genera_solo_la_primera_vez(tmp_path, monkeypatch):
    """"Acordate de configurar el token" es una instrucción que no se cumple.
    Si no está, se crea y se guarda; la segunda vez es el mismo, así que el
    link que anotó el usuario sigue sirviendo mañana."""
    monkeypatch.delenv("KOBRA_REALTIME_TOKEN", raising=False)
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    import importlib

    from kobra import config as kconfig
    importlib.reload(kconfig)
    monkeypatch.setattr(acceso, "CLAVE_CONFIG", "realtime_token_de_prueba")

    primero = acceso.token()
    assert len(primero) >= 32, "un token corto se adivina"
    assert acceso.token() == primero, "cambia en cada arranque: el link deja de servir"


def test_la_variable_de_entorno_manda(monkeypatch):
    """Para fijarlo desde Docker/systemd sin depender del archivo."""
    monkeypatch.setenv("KOBRA_REALTIME_TOKEN", "el-que-yo-quiero-usar-1234567890")
    assert acceso.token() == "el-que-yo-quiero-usar-1234567890"
