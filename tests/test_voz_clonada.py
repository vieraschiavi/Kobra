# © 2026 Martín Viera. Todos los derechos reservados.

"""Voz clonada: que llegue a las llamadas y que clonarla sea grabar y listo.

El defecto de origen: la voz elegida en Configuración se guardaba y el
servidor de llamadas nunca la leía (leía solo el entorno, una vez, al
importar, y además exigía un `TTS_PROVIDER` que `env.example` no documenta).
Estos tests fijan:

  * que lo guardado desde la pantalla suena en la PRÓXIMA frase, sin reinicio,
  * que la configuración documentada en `env.example` también funciona,
  * que una muestra que no sirve se rechaza con un motivo accionable,
  * que el clonado manda lo que ElevenLabs espera y traduce sus errores,
  * y que la API exige admin de la instalación, consentimiento y plan.
"""
import importlib
import io
import os
import sys

import numpy as np
import pytest
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-voz-clonada"
_RECARGABLES = ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
                "kobra.voz_clonada", "webapp.backend.api")


def _wav(segundos: float, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    t = np.arange(int(segundos * sr)) / sr
    sf.write(buf, (0.2 * np.sin(2 * np.pi * 180 * t)).astype(np.float32), sr, format="WAV")
    return buf.getvalue()


@pytest.fixture
def vc(tmp_path, monkeypatch):
    """`voz_clonada` con la config en una carpeta temporal y sin voz en el entorno."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    for v in ("TTS_PROVIDER", "ELEVENLABS_VOICE_ID", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import voz_clonada
    importlib.reload(voz_clonada)
    yield voz_clonada
    monkeypatch.undo()
    importlib.reload(kconfig)
    importlib.reload(voz_clonada)


# ---------------------------------------------------------------------------
# Qué voz suena en la llamada
# ---------------------------------------------------------------------------
def test_sin_nada_configurado_habla_twilio(vc):
    assert vc.voz_activa() == ""
    assert vc.estado()["motor_llamadas"] == "twilio"


def test_la_voz_elegida_en_pantalla_es_la_que_suena(vc):
    vc.activar("vozClonada123", "Martín")
    assert vc.voz_activa() == "vozClonada123"
    assert vc.estado()["nombre"] == "Martín"


def test_la_configuracion_de_env_example_alcanza(vc, monkeypatch):
    """`env.example` documenta ELEVENLABS_VOICE_ID y no TTS_PROVIDER. Antes,
    sin TTS_PROVIDER=elevenlabs, la voz no se usaba nunca."""
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "vozDelEntorno1")
    assert vc.voz_activa() == "vozDelEntorno1"
    assert vc.estado()["forzada_por_entorno"] is True


def test_desactivar_vuelve_a_twilio_y_tts_provider_twilio_la_apaga(vc, monkeypatch):
    vc.activar("vozClonada123")
    vc.desactivar()
    assert vc.voz_activa() == ""
    vc.activar("vozClonada123")
    monkeypatch.setenv("TTS_PROVIDER", "twilio")
    assert vc.voz_activa() == ""


def test_la_llamada_usa_la_voz_guardada_sin_reiniciar_el_servidor(vc, monkeypatch):
    """El servidor de llamadas ya está importado (arrancado) cuando alguien
    clona la voz. La próxima frase tiene que salir con ella."""
    from realtime import server
    monkeypatch.setattr(server, "kvoz_clonada", vc)
    pedidas = []

    def falso_sintetizar(texto, voice_id, api_key=None, modelo=None):
        pedidas.append((voice_id, modelo))
        return {"ok": True, "audio": b"ID3mp3", "caracteres": len(texto),
                "costo_est_usd": 0.0, "error": None}

    monkeypatch.setattr(server.voz_tts, "sintetizar", falso_sintetizar)
    monkeypatch.setattr(server, "_public_base", lambda request: "https://kobra.test")
    pedido = object()

    assert server._say("Hola", pedido).startswith("<Say")      # todavía sin voz

    vc.activar("vozClonada123", "Martín")
    xml = server._say("Hola de nuevo", pedido)
    assert xml.startswith("<Play>https://kobra.test/voz/audio/"), xml
    assert pedidas == [("vozClonada123", server.voz_tts.MODELO_LLAMADAS)]


def test_si_elevenlabs_falla_la_llamada_sigue_con_polly(vc, monkeypatch):
    from realtime import server
    monkeypatch.setattr(server, "kvoz_clonada", vc)
    monkeypatch.setattr(server.voz_tts, "sintetizar", lambda *a, **k: {
        "ok": False, "audio": None, "caracteres": 0, "costo_est_usd": 0.0, "error": "sin crédito"})
    vc.activar("vozClonada123")
    assert server._say("Hola", object()).startswith("<Say")


# ---------------------------------------------------------------------------
# Validación de la muestra
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nombre, contenido, motivo", [
    ("voz.ogg", b"x", ".wav, .mp3 o .m4a"),
    ("voz.wav", b"", "vacía"),
    ("voz.wav", b"esto no es un wav", "dañado"),
])
def test_muestra_invalida_dice_por_que(vc, nombre, contenido, motivo):
    with pytest.raises(vc.MuestraInvalida, match=motivo):
        vc.validar_muestra(nombre, contenido)


def test_muestra_demasiado_corta_se_rechaza(vc):
    with pytest.raises(vc.MuestraInvalida, match="al menos 10 s"):
        vc.validar_muestra("voz.wav", _wav(4))


def test_muestra_corta_pero_valida_avisa_y_una_larga_no(vc):
    corta = vc.validar_muestra("voz.wav", _wav(15))
    assert round(corta["duracion_s"]) == 15 and "un minuto" in corta["aviso"]
    assert vc.validar_muestra("voz.wav", _wav(65))["aviso"] is None
    # Un MP3 no se decodifica en el servidor: pasa sin duración ni aviso.
    assert vc.validar_muestra("voz.mp3", b"ID3algo") == {"duracion_s": None, "aviso": None}


# ---------------------------------------------------------------------------
# Clonado contra ElevenLabs (red simulada)
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, status, datos=None, texto=""):
        self.status_code, self._datos, self.text = status, datos, texto
        self.ok = status < 400
        self.content = b"x" if datos is not None else b""

    def json(self):
        return self._datos


def test_clonar_manda_nombre_y_muestras_y_devuelve_el_id(vc, monkeypatch):
    import requests
    enviado = {}

    def falso_post(url, headers, data, files, timeout):
        enviado.update(url=url, headers=headers, data=data, files=files)
        return _Resp(200, {"voice_id": "nuevaVoz123", "requires_verification": False})

    monkeypatch.setattr(requests, "post", falso_post)
    r = vc.clonar("Martín", [("m.wav", b"RIFF")], api_key="sk-una-key-bien-larga")
    assert r == {"ok": True, "voice_id": "nuevaVoz123",
                 "requiere_verificacion": False, "error": None}
    assert enviado["url"].endswith("/v1/voices/add")
    assert enviado["headers"] == {"xi-api-key": "sk-una-key-bien-larga"}
    assert enviado["data"]["name"] == "Martín"
    assert enviado["files"] == [("files", ("m.wav", b"RIFF"))]


@pytest.mark.parametrize("respuesta, motivo", [
    (_Resp(401, {"detail": {"message": "invalid key"}}), "rechazó la key"),
    (_Resp(422, {"detail": [{"msg": "file too short"}]}), "422: file too short"),
    (_Resp(200, {}), "no devolvió el id"),
])
def test_clonar_traduce_los_errores_de_elevenlabs(vc, monkeypatch, respuesta, motivo):
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: respuesta)
    r = vc.clonar("Martín", [("m.wav", b"RIFF")], api_key="sk-una-key-bien-larga")
    assert r["ok"] is False and motivo in r["error"]


def test_clonar_sin_red_no_levanta_excepcion(vc, monkeypatch):
    import requests

    def sin_red(*a, **k):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(requests, "post", sin_red)
    r = vc.clonar("Martín", [("m.wav", b"RIFF")], api_key="sk-una-key-bien-larga")
    assert r["ok"] is False and "No pude conectar" in r["error"]


def test_clonar_sin_key_lo_dice_sin_llamar_a_la_red(vc, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("no debía llamar"))
    assert "ELEVENLABS_API_KEY" in vc.clonar("Martín", [("m.wav", b"RIFF")])["error"]


def test_la_key_guardada_en_pantalla_sirve_aunque_el_entorno_no_la_tenga(vc):
    """El servidor de llamadas arrancó antes de que se cargara la key."""
    vc.kconfig.guardar({"ELEVENLABS_API_KEY": "sk-guardada-en-pantalla"})
    os.environ.pop("ELEVENLABS_API_KEY", None)
    vc._olvidar_cache()
    assert vc.api_key_elevenlabs() == "sk-guardada-en-pantalla"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.fixture
def api_voz(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-una-key-bien-larga")
    for v in ("KOBRA_OWNER", "TTS_PROVIDER", "ELEVENLABS_VOICE_ID"):
        monkeypatch.delenv(v, raising=False)

    def montar(features):
        for nombre in _RECARGABLES[:-1]:
            importlib.reload(importlib.import_module(nombre))
        from backend_venta import licencias as klic
        from kobra import config as kconfig
        kconfig.guardar_extra("LICENCIA_TOKEN", klic.emitir_licencia(
            "cliente-voz", "basico", features=features))
        from webapp.backend import api
        importlib.reload(api)
        return api

    yield montar
    monkeypatch.undo()
    for nombre in _RECARGABLES:
        if nombre in sys.modules:
            importlib.reload(sys.modules[nombre])


def _cliente(api, rol="admin", empresa=None):
    from fastapi.testclient import TestClient
    cli = TestClient(api.app)
    cli.headers.update({"Authorization":
                        f"Bearer {api._emitir_token(rol, empresa or api.EMPRESA_DEFAULT)}"})
    return cli


def _clonar(cli, consentimiento="true", contenido=None):
    return cli.post("/api/voz/clonada",
                    data={"nombre": "Martín", "consentimiento": consentimiento},
                    files={"archivo": ("muestra.wav", contenido or _wav(20), "audio/wav")})


def _red_ok(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(
        200, {"voice_id": "nuevaVoz123", "requires_verification": False}))


def test_api_clona_activa_y_deja_constancia(api_voz, monkeypatch):
    api = api_voz(["voz"])
    _red_ok(monkeypatch)
    registros = []
    monkeypatch.setattr(api.kauditoria, "registrar",
                        lambda accion, detalle=None, **k: registros.append((accion, detalle)))
    cli = _cliente(api)
    r = _clonar(cli)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["motor_llamadas"] == "elevenlabs" and d["voice_id"] == "nuevaVoz123"
    assert "un minuto" in d["aviso"]                  # 20 s: anda, pero conviene más
    assert cli.get("/api/voz/clonada").json()["nombre"] == "Martín"
    assert registros[-1][0] == "voz_clonada"
    assert registros[-1][1]["consentimiento_declarado"] is True


def test_api_sin_consentimiento_no_clona(api_voz, monkeypatch):
    api = api_voz(["voz"])
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("no debía clonar"))
    r = _clonar(_cliente(api), consentimiento="false")
    assert r.status_code == 400 and "consentimiento" in r.json()["detail"]


def test_api_muestra_corta_400_con_motivo(api_voz, monkeypatch):
    api = api_voz(["voz"])
    _red_ok(monkeypatch)
    r = _clonar(_cliente(api), contenido=_wav(3))
    assert r.status_code == 400 and "al menos" in r.json()["detail"]


def test_api_licencia_sin_modulo_voz_no_clona(api_voz, monkeypatch):
    """Owner vs licencia: el cliente necesita `voz` en su licencia."""
    api = api_voz(["whatsapp"])
    _red_ok(monkeypatch)
    r = _clonar(_cliente(api))
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"


def test_api_gestor_y_admin_de_otra_empresa_no_tocan_la_voz(api_voz):
    api = api_voz(["voz"])
    assert _cliente(api, rol="gestor").get("/api/voz/clonada").status_code == 403
    r = _cliente(api, empresa="otra-empresa").post("/api/voz/clonada/desactivar")
    assert r.status_code == 403 and "instalación" in r.json()["detail"]


def test_api_probar_devuelve_mp3_de_la_voz_activa(api_voz, monkeypatch):
    api = api_voz(["voz"])
    cli = _cliente(api)
    r = cli.post("/api/voz/clonada/probar", json={})
    assert r.status_code == 400 and "No hay voz" in r.json()["detail"]

    from kobra import voz_tts
    pedidas = []
    monkeypatch.setattr(voz_tts, "sintetizar", lambda texto, voice_id, **k: (
        pedidas.append((texto, voice_id)) or {"ok": True, "audio": b"ID3mp3",
                                               "caracteres": len(texto),
                                               "costo_est_usd": 0.0, "error": None}))
    assert cli.post("/api/voz/clonada/elegir",
                    json={"voice_id": "vozDeLaCuenta1", "nombre": "Ana"}).status_code == 200
    r = cli.post("/api/voz/clonada/probar", json={"texto": "x" * 999})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"ID3mp3"
    assert pedidas == [("x" * 300, "vozDeLaCuenta1")]   # la prueba no cobra un guion entero


def test_api_elegir_rechaza_un_id_raro_y_desactivar_vuelve_a_twilio(api_voz):
    api = api_voz(["voz"])
    cli = _cliente(api)
    assert cli.post("/api/voz/clonada/elegir",
                    json={"voice_id": "../../etc"}).status_code == 400
    cli.post("/api/voz/clonada/elegir", json={"voice_id": "vozDeLaCuenta1"})
    assert cli.post("/api/voz/clonada/desactivar").json()["motor_llamadas"] == "twilio"
