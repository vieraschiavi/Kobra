# © 2026 Martín Viera. Todos los derechos reservados.

"""Lo guardado en Configuración rige en los procesos que ya están corriendo.

Dos bugs de producción:

  * `kconfig.aplicar()` exportaba al entorno TODO lo guardado, incluidos
    valores que no son texto. Activar el informe semanal guarda
    `INFORME_EMAIL_ACTIVO=True`, y el siguiente arranque de la API, del
    servidor de llamadas y del dashboard moría con
    `TypeError: str expected, not bool` antes de servir nada.
  * El servidor de llamadas leía las API keys una vez, al arrancar. Rotar el
    token de Twilio desde la pantalla (otro proceso) dejaba el viejo en
    memoria: la firma de cada webhook daba inválida y todas las llamadas se
    cortaban con 403 hasta reiniciar a mano.
"""
import importlib
import os
import sys

import pytest
from conftest import firma_twilio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture
def kconfig(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    for k in ("TWILIO_AUTH_TOKEN", "OPENAI_API_KEY", "INFORME_EMAIL_ACTIVO",
              "TTS_PROVIDER", "ELEVENLABS_VOICE_ID"):
        monkeypatch.delenv(k, raising=False)
    from kobra import config
    importlib.reload(config)
    yield config
    monkeypatch.undo()
    importlib.reload(config)


def test_un_extra_que_no_es_texto_no_tumba_el_arranque(kconfig):
    kconfig.guardar_extra("INFORME_EMAIL_ACTIVO", True)
    kconfig.guardar_extra("CAMPANA_MAX_POR_CORRIDA", 50)
    kconfig.guardar({"OPENAI_API_KEY": "sk-guardada-123456"})
    os.environ.pop("OPENAI_API_KEY", None)
    kconfig.aplicar()                                  # antes: TypeError
    assert os.environ["OPENAI_API_KEY"] == "sk-guardada-123456"


def test_los_extras_no_se_congelan_en_el_entorno(kconfig):
    """La voz guardada al arrancar le ganaba para siempre a la elegida después."""
    kconfig.guardar_extra("TTS_PROVIDER", "elevenlabs")
    kconfig.guardar_extra("ELEVENLABS_VOICE_ID", "vozVieja123")
    kconfig.aplicar()
    assert "TTS_PROVIDER" not in os.environ
    assert "ELEVENLABS_VOICE_ID" not in os.environ


def test_refrescar_toma_una_key_rotada_desde_otro_proceso(kconfig):
    kconfig.guardar({"TWILIO_AUTH_TOKEN": "token-viejo-1"})
    kconfig.refrescar(ttl_seg=0)
    # Otro proceso (la pantalla) rota la key: escribe el almacén, no este
    # entorno — `guardar_extra` hace exactamente eso.
    kconfig.guardar_extra("TWILIO_AUTH_TOKEN", "token-nuevo-2")
    assert os.environ["TWILIO_AUTH_TOKEN"] == "token-viejo-1"
    kconfig.refrescar(ttl_seg=0)
    assert os.environ["TWILIO_AUTH_TOKEN"] == "token-nuevo-2"


def test_refrescar_no_pisa_lo_que_puso_quien_lanzo_el_proceso(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token-del-docker")
    from kobra import config
    importlib.reload(config)
    try:
        config.guardar_extra("TWILIO_AUTH_TOKEN", "token-de-la-pantalla")
        config.refrescar(ttl_seg=0)
        assert os.environ["TWILIO_AUTH_TOKEN"] == "token-del-docker"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_refrescar_respeta_el_ttl(kconfig, monkeypatch):
    lecturas = []
    monkeypatch.setattr(kconfig, "cargar", lambda: lecturas.append(1) or {})
    kconfig.refrescar(ttl_seg=0)
    for _ in range(50):
        kconfig.refrescar(ttl_seg=60)
    assert len(lecturas) == 1


def test_las_llamadas_siguen_andando_tras_rotar_el_token_de_twilio(tmp_path, monkeypatch):
    """End to end contra el servidor real: ya arrancado con el token viejo,
    el admin carga el nuevo y Twilio empieza a firmar con ese."""
    pytest.importorskip("fastapi")
    base = "https://kobra.example.com"
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", base)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    previos = dict(sys.modules)
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    try:
        from kobra import config
        config.guardar({"TWILIO_AUTH_TOKEN": "token-viejo-1"})
        from fastapi.testclient import TestClient

        from realtime import server
        cli = TestClient(server.app)
        form = {"CallSid": "CA-rot", "From": "+59899000000"}
        url = f"{base}/voz/entrante"
        assert cli.post(url[len(base):], data=form,
                        headers=firma_twilio(url, form, "token-viejo-1")).status_code == 200

        config.guardar_extra("TWILIO_AUTH_TOKEN", "token-nuevo-2")   # la pantalla lo rota
        config._ultimo_refresco = 0.0            # sin esperar los 10 s del TTL

        r = cli.post(url[len(base):], data=form,
                     headers=firma_twilio(url, form, "token-nuevo-2"))
        assert r.status_code == 200, "el servidor sigue validando con el token viejo"
    finally:
        for k in list(sys.modules):
            if k.startswith(("realtime", "kobra")):
                del sys.modules[k]
        sys.modules.update(previos)
