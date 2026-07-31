"""Tests de kobra/llm.py: el cliente puede elegir Claude/Gemini/OpenAI como
proveedor de IA (con su propia cuenta corporativa) para el Asistente, el
Copiloto y el Gestor IA — antes esto estaba hardcodeado a Anthropic en 4
archivos distintos."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def kllm(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import llm
    importlib.reload(llm)
    return llm


def test_proveedor_default_es_anthropic(kllm):
    assert kllm.proveedor_activo() == "anthropic"


def test_establecer_proveedor_persiste(kllm):
    kllm.establecer_proveedor("gemini")
    assert kllm.proveedor_activo() == "gemini"
    with pytest.raises(ValueError):
        kllm.establecer_proveedor("copilot")


def test_disponible_sin_key(kllm, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not kllm.disponible()
    assert kllm.disponible(api_key="sk-ant-test-1234")


def test_generar_sin_key_devuelve_none_o_lanza(kllm, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert kllm.generar("hola") is None
    with pytest.raises(RuntimeError):
        kllm.generar("hola", lanzar=True)


def test_generar_anthropic_mockeado(kllm, monkeypatch):
    import requests

    capturado = {}

    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"content": [{"text": "respuesta de claude"}]}

    def _post(url, headers=None, json=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
        return _Resp()

    monkeypatch.setattr(requests, "post", _post)
    out = kllm.generar("pregunta", system="sos un asistente", max_tokens=99,
                       api_key="sk-ant-test-1234")
    assert out == "respuesta de claude"
    assert capturado["url"] == "https://api.anthropic.com/v1/messages"
    assert capturado["json"]["system"] == "sos un asistente"
    assert capturado["json"]["max_tokens"] == 99
    assert capturado["json"]["messages"][0]["content"] == "pregunta"


def test_generar_gemini_mockeado(kllm, monkeypatch):
    import requests
    kllm.establecer_proveedor("gemini")

    capturado = {}

    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "respuesta de gemini"}]}}]}

    def _post(url, headers=None, json=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
        capturado["headers"] = headers
        return _Resp()

    monkeypatch.setattr(requests, "post", _post)
    out = kllm.generar("pregunta", system="sos un asistente", api_key="AIzaTest1234")
    assert out == "respuesta de gemini"
    assert "generativelanguage.googleapis.com" in capturado["url"]
    assert capturado["headers"]["x-goog-api-key"] == "AIzaTest1234"
    assert capturado["json"]["systemInstruction"]["parts"][0]["text"] == "sos un asistente"
    assert capturado["json"]["contents"][0]["parts"][0]["text"] == "pregunta"


def test_generar_openai_mockeado(kllm, monkeypatch):
    import requests
    kllm.establecer_proveedor("openai")

    capturado = {}

    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": "respuesta de chatgpt"}}]}

    def _post(url, headers=None, json=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
        return _Resp()

    monkeypatch.setattr(requests, "post", _post)
    out = kllm.generar("pregunta", system="sos un asistente", api_key="sk-openai-test-1234")
    assert out == "respuesta de chatgpt"
    assert capturado["url"] == "https://api.openai.com/v1/chat/completions"
    assert capturado["json"]["messages"] == [
        {"role": "system", "content": "sos un asistente"},
        {"role": "user", "content": "pregunta"},
    ]


def test_generar_error_de_red_devuelve_none_sin_lanzar(kllm, monkeypatch):
    import requests

    def _post(*a, **kw):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "post", _post)
    assert kllm.generar("pregunta", api_key="sk-ant-test-1234") is None


def test_establecer_modelo_override(kllm):
    assert kllm.modelo_de("gemini") == "gemini-2.5-flash"
    kllm.establecer_modelo("gemini", "gemini-3.5-flash")
    assert kllm.modelo_de("gemini") == "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# Endpoint /api/config/proveedor_ia
# ---------------------------------------------------------------------------
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    return api, TestClient(api.app)


def _h_admin(cliente):
    r = cliente.post("/api/auth/login", json={"password": "AdminTest123!"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_proveedor_ia_get_y_post(cliente):
    api, c = cliente
    h = _h_admin(c)
    d = c.get("/api/config/proveedor_ia", headers=h).json()
    assert d["proveedor"] == "anthropic"
    assert set(d["proveedores"]) == {"anthropic", "gemini", "openai"}

    r = c.post("/api/config/proveedor_ia", json={"proveedor": "openai"}, headers=h)
    assert r.status_code == 200 and r.json()["proveedor"] == "openai"

    d2 = c.get("/api/config/proveedor_ia", headers=h).json()
    assert d2["proveedor"] == "openai"

    # proveedor inválido -> 400
    assert c.post("/api/config/proveedor_ia", json={"proveedor": "copilot"},
                  headers=h).status_code == 400

    # sin token -> 401
    assert c.get("/api/config/proveedor_ia").status_code == 401
