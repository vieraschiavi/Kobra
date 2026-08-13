# © 2026 Martín Viera. Todos los derechos reservados.

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


def test_generar_xai_mockeado(kllm, monkeypatch):
    import requests
    kllm.establecer_proveedor("xai")

    capturado = {}

    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": "respuesta de grok"}}]}

    def _post(url, headers=None, json=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
        return _Resp()

    monkeypatch.setattr(requests, "post", _post)
    out = kllm.generar("pregunta", system="sos un asistente", api_key="xai-test-1234")
    assert out == "respuesta de grok"
    assert capturado["url"] == "https://api.x.ai/v1/chat/completions"
    assert capturado["json"]["model"] == "grok-4"


def test_establecer_modelo_override(kllm):
    assert kllm.modelo_de("gemini") == "gemini-2.5-flash"
    kllm.establecer_modelo("gemini", "gemini-3.5-flash")
    assert kllm.modelo_de("gemini") == "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# Catálogo de modelos: modelos_disponibles() + actualizar_modelos()
# ---------------------------------------------------------------------------
def test_modelos_disponibles_sin_cache_devuelve_default(kllm):
    assert kllm.modelos_disponibles("anthropic") == ["claude-sonnet-5"]
    with pytest.raises(ValueError):
        kllm.modelos_disponibles("copilot")


def test_modelos_disponibles_incluye_el_modelo_en_uso(kllm):
    # El modelo elegido se ofrece siempre, aunque no esté en el catálogo.
    kllm.establecer_modelo("openai", "gpt-4o-mini")
    assert kllm.modelos_disponibles("openai")[0] == "gpt-4o-mini"


def test_actualizar_modelos_sin_key_no_rompe(kllm, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = kllm.actualizar_modelos("anthropic")
    assert res["ok"] is False
    assert "ANTHROPIC_API_KEY" in res["detalle"]
    assert res["modelos"] == ["claude-sonnet-5"]


def _resp_get(payload):
    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return payload
    return _Resp()


def test_actualizar_modelos_anthropic_cachea_y_persiste(kllm, monkeypatch):
    import requests
    capturado = {}

    def _get(url, headers=None, timeout=None):
        capturado["url"] = url
        capturado["headers"] = headers
        return _resp_get({"data": [{"id": "claude-fable-5"}, {"id": "claude-sonnet-5"}]})

    monkeypatch.setattr(requests, "get", _get)
    res = kllm.actualizar_modelos("anthropic", api_key="sk-ant-test-1234")
    assert res["ok"] is True
    assert "api.anthropic.com/v1/models" in capturado["url"]
    assert capturado["headers"]["x-api-key"] == "sk-ant-test-1234"
    # Queda cacheado (sin red) y con fecha de actualización
    assert kllm.modelos_disponibles("anthropic") == ["claude-fable-5", "claude-sonnet-5"]
    assert kllm.fecha_actualizacion_modelos("anthropic")


def test_actualizar_modelos_openai_filtra_no_chat(kllm, monkeypatch):
    import requests

    def _get(url, headers=None, timeout=None):
        return _resp_get({"data": [
            {"id": "gpt-5", "created": 30},
            {"id": "gpt-4o-mini", "created": 20},
            {"id": "text-embedding-3-small", "created": 50},
            {"id": "whisper-1", "created": 40},
            {"id": "gpt-4o-audio-preview", "created": 25},
            {"id": "dall-e-3", "created": 10},
            {"id": "o3-mini", "created": 28},
        ]})

    monkeypatch.setattr(requests, "get", _get)
    res = kllm.actualizar_modelos("openai", api_key="sk-openai-test-1234")
    assert res["ok"] is True
    # Solo chat, ordenados por más nuevo primero
    assert kllm.modelos_disponibles("openai") == \
        ["gpt-4o", "gpt-5", "o3-mini", "gpt-4o-mini"]  # gpt-4o primero por estar en uso


def test_actualizar_modelos_gemini_filtra_por_capacidad(kllm, monkeypatch):
    import requests

    def _get(url, headers=None, timeout=None):
        return _resp_get({"models": [
            {"name": "models/gemini-3-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/imagen-4", "supportedGenerationMethods": ["predict"]},
        ]})

    monkeypatch.setattr(requests, "get", _get)
    res = kllm.actualizar_modelos("gemini", api_key="AIzaTest1234")
    assert res["ok"] is True
    assert kllm.modelos_disponibles("gemini") == ["gemini-3-pro", "gemini-2.5-flash"]


def test_actualizar_modelos_error_de_red_conserva_cache(kllm, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get",
                        lambda *a, **kw: _resp_get({"data": [{"id": "grok-5"}]}))
    assert kllm.actualizar_modelos("xai", api_key="xai-test-1234")["ok"] is True

    def _get_roto(*a, **kw):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "get", _get_roto)
    res = kllm.actualizar_modelos("xai", api_key="xai-test-1234")
    assert res["ok"] is False
    # El caché anterior sigue disponible (grok-4 primero por estar en uso)
    assert kllm.modelos_disponibles("xai") == ["grok-4", "grok-5"]


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
    assert set(d["proveedores"]) == {"anthropic", "gemini", "openai", "xai"}
    # Catálogo de modelos por proveedor (default sin actualizar)
    assert d["modelos"]["anthropic"]["activo"] == "claude-sonnet-5"
    assert d["modelos"]["xai"]["disponibles"] == ["grok-4"]
    assert d["modelos"]["gemini"]["actualizado"] is None

    r = c.post("/api/config/proveedor_ia", json={"proveedor": "openai"}, headers=h)
    assert r.status_code == 200 and r.json()["proveedor"] == "openai"

    d2 = c.get("/api/config/proveedor_ia", headers=h).json()
    assert d2["proveedor"] == "openai"

    # Elegir también el modelo (regula el consumo de tokens)
    r = c.post("/api/config/proveedor_ia",
               json={"proveedor": "openai", "modelo": "gpt-4o-mini"}, headers=h)
    assert r.status_code == 200 and r.json()["modelo"] == "gpt-4o-mini"
    d3 = c.get("/api/config/proveedor_ia", headers=h).json()
    assert d3["modelos"]["openai"]["activo"] == "gpt-4o-mini"

    # proveedor inválido -> 400
    assert c.post("/api/config/proveedor_ia", json={"proveedor": "copilot"},
                  headers=h).status_code == 400

    # sin token -> 401
    assert c.get("/api/config/proveedor_ia").status_code == 401


def test_api_actualizar_modelos(cliente, monkeypatch):
    import requests
    api, c = cliente
    h = _h_admin(c)

    # Sin key del proveedor -> 502 con el motivo
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    r = c.post("/api/config/proveedor_ia/actualizar_modelos",
               json={"proveedor": "xai"}, headers=h)
    assert r.status_code == 502 and "XAI_API_KEY" in r.json()["detail"]

    # Con key y API respondiendo, el catálogo queda cacheado con fecha
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234")

    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": [{"id": "claude-fable-5"}, {"id": "claude-sonnet-5"}]}

    monkeypatch.setattr(requests, "get", lambda *a, **kw: _Resp())
    r = c.post("/api/config/proveedor_ia/actualizar_modelos",
               json={"proveedor": "anthropic"}, headers=h)
    assert r.status_code == 200
    assert r.json()["modelos"] == ["claude-fable-5", "claude-sonnet-5"]
    assert r.json()["actualizado"]

    d = c.get("/api/config/proveedor_ia", headers=h).json()
    assert d["modelos"]["anthropic"]["disponibles"] == ["claude-fable-5", "claude-sonnet-5"]

    # rol no admin no puede
    assert c.post("/api/config/proveedor_ia/actualizar_modelos",
                  json={"proveedor": "xai"}).status_code == 401
