"""Tests del gateo por licencia en modo standalone (webapp/backend/api.py).

En modo hosted (Vercel, multi-tenant) el login sigue siendo por contraseña,
sin cambios. En modo standalone (instalador de Windows, KOBRA_MODO_STANDALONE=1,
lo activa kobra_launcher.py) la puerta de entrada es la licencia emitida al
comprar (o el trial de 3 días) — no una contraseña de administrador.
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _cliente(tmp_path, monkeypatch, standalone):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    if standalone:
        monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    else:
        monkeypatch.delenv("KOBRA_MODO_STANDALONE", raising=False)
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from fastapi.testclient import TestClient
    from webapp.backend import api
    importlib.reload(api)  # MODO_STANDALONE se lee al importar el módulo
    return api, TestClient(api.app)


@pytest.fixture()
def standalone(tmp_path, monkeypatch):
    return _cliente(tmp_path, monkeypatch, standalone=True)


@pytest.fixture()
def hosted(tmp_path, monkeypatch):
    return _cliente(tmp_path, monkeypatch, standalone=False)


def test_modo_hosted_no_pide_licencia(hosted):
    _, cliente = hosted
    assert cliente.get("/api/licencia/estado").json() == {"standalone": False}
    assert cliente.post("/api/licencia/activar", json={"token": "x"}).status_code == 404


def test_modo_standalone_sin_licencia_todavia(standalone):
    _, cliente = standalone
    assert cliente.get("/api/licencia/estado").json() == {"standalone": True, "activa": False}


def test_modo_standalone_activa_con_trial_y_persiste(standalone):
    api, cliente = standalone
    from backend_venta import licencias as klicencias
    token = klicencias.emitir_licencia("cliente-test", "trial")

    r = cliente.post("/api/licencia/activar", json={"token": token})
    assert r.status_code == 200
    d = r.json()
    assert d["trial"] is True
    assert d["plan"] == "trial"
    assert d["dias_restantes"] == 2  # emitido ahora mismo, vence en 3 días
    assert d["token"]

    # El bearer emitido ya sirve para pegarle a la API sin pedir password.
    h = {"Authorization": f"Bearer {d['token']}"}
    assert cliente.get("/api/kpis", headers=h).status_code != 401

    # Y queda persistido: una nueva consulta de estado la sigue viendo activa.
    r2 = cliente.get("/api/licencia/estado").json()
    assert r2 == {"standalone": True, "activa": True, "plan": "trial",
                 "trial": True, "dias_restantes": 2}


def test_modo_standalone_licencia_invalida(standalone):
    _, cliente = standalone
    r = cliente.post("/api/licencia/activar", json={"token": "no-es-un-jwt"})
    assert r.status_code == 400
    assert "inválida" in r.json()["detail"]


def test_modo_standalone_licencia_vencida(standalone):
    _, cliente = standalone
    from backend_venta import licencias as klicencias
    token = klicencias.emitir_licencia("cliente-test", "trial", dias=-1)
    r = cliente.post("/api/licencia/activar", json={"token": token})
    assert r.status_code == 400
    assert "venció" in r.json()["detail"]
