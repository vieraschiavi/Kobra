# © 2026 Martín Viera. Todos los derechos reservados.

"""Tests de /api/gestor-ia/demo: la demo del Gestor IA negociando (voz y
WhatsApp) — la parte que 'no se había probado'. Corre el motor real de
negociación y devuelve turnos + conclusiones."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


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


def _h(c):
    r = c.post("/api/auth/login", json={"password": "AdminTest123!"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.parametrize("canal", ["Llamada", "WhatsApp"])
def test_demo_negocia_y_cierra(cliente, canal):
    api, c = cliente
    r = c.post("/api/gestor-ia/demo", json={"canal": canal}, headers=_h(c))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["canal"] == canal
    # Diagnóstico ProbPago real del deudor de demostración. El nombre se
    # verifica contra el módulo y no se escribe acá: el deudor demo llevaba el
    # nombre y el CELULAR REAL del dueño, y este test los fijaba — o sea que
    # blindaba la PII en vez de impedirla (ver tests/test_sin_datos_personales.py).
    from webapp.backend.api import _DEUDOR_DEMO_GESTOR
    assert d["brief"]["nombre"] == _DEUDOR_DEMO_GESTOR["nombre"]
    assert d["brief"]["nombre"]      # y no viene vacío
    assert 0 < d["brief"]["probpago"] <= 1
    # La conversación tiene turnos alternados y arranca el gestor.
    assert d["turnos"][0]["quien"] == "gestor"
    assert len(d["turnos"]) >= 4
    # El guion demo termina aceptando → promesa de pago con monto acordado.
    assert d["conclusion"]["resultado"] == "Promesa"
    assert d["conclusion"]["monto_acordado"] > 0
    assert d["conclusion"]["calidad_gestion"] is not None


def test_demo_guion_propio_negativa(cliente):
    api, c = cliente
    # El admin puede pasar sus propios mensajes de cliente; una negativa dura
    # cierra sin acuerdo (el motor la detecta).
    r = c.post("/api/gestor-ia/demo", headers=_h(c), json={
        "canal": "Llamada",
        "mensajes": ["Sí soy yo", "No pienso pagar nada, no me llamen más"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["conclusion"]["resultado"] in ("Sin acuerdo", "No contactar")


def test_demo_deudor_propio(cliente):
    api, c = cliente
    r = c.post("/api/gestor-ia/demo", headers=_h(c), json={
        "canal": "WhatsApp",
        "deudor": {"id_deudor": "X1", "nombre": "Ana", "deuda": "80000", "dias_mora": "45"}})
    assert r.status_code == 200, r.text
    assert r.json()["brief"]["nombre"] == "Ana"
