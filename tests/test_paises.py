"""Tests del catálogo de países (Fase 1 LATAM) y sus endpoints."""
import importlib
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import paises as kpaises  # noqa: E402


def test_catalogo_fase1():
    cat = kpaises.listar()
    codigos = [p["codigo"] for p in cat]
    assert codigos == ["UY", "AR", "MX", "CL", "CO", "PE"]      # UY primero, orden de despliegue
    for p in cat:
        assert p["moneda"] and p["simbolo"] and p["locale"]
        assert p["nota_cumplimiento"]


def test_obtener_default_y_case_insensitive():
    assert kpaises.obtener(None).codigo == "UY"
    assert kpaises.obtener("").codigo == "UY"
    assert kpaises.obtener("br").codigo == "UY"      # fuera de catálogo → default
    assert kpaises.obtener("mx").codigo == "MX"


# --- endpoints ---------------------------------------------------------------
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    kauth.establecer_password("gestor", "GestorTest123!")

    from fastapi.testclient import TestClient
    from webapp.backend import api
    yield TestClient(api.app)

    # El endpoint escribe data/tenants/<empresa>/pais.json en el repo real
    # (no aislado por KOBRA_CONFIG_DIR) — limpiar para no ensuciar el repo.
    shutil.rmtree(os.path.join(ROOT, "data", "tenants", "kobra-test-pais"), ignore_errors=True)


def _tok(cliente, password="AdminTest123!", empresa="kobra-test-pais"):
    r = cliente.post("/api/auth/login", json={"password": password, "empresa": empresa})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_catalogo_paises(cliente):
    h = _tok(cliente)
    r = cliente.get("/api/paises", headers=h)
    assert r.status_code == 200
    assert len(r.json()["paises"]) == 6


def test_api_tenant_pais_default_es_uruguay(cliente):
    h = _tok(cliente)
    r = cliente.get("/api/tenant/pais", headers=h)
    assert r.status_code == 200 and r.json()["codigo"] == "UY"


def test_api_tenant_pais_set_y_leer(cliente):
    h_admin = _tok(cliente)
    r = cliente.post("/api/tenant/pais", json={"codigo": "co"}, headers=h_admin)
    assert r.status_code == 200
    assert r.json() == {"codigo": "CO", "nombre": "Colombia", "moneda": "COP",
                         "simbolo": "$", "locale": "es-CO",
                         "nota_cumplimiento": kpaises.NOTA_CUMPLIMIENTO_DEFAULT}
    # persiste para el mismo tenant en un pedido posterior
    r2 = cliente.get("/api/tenant/pais", headers=h_admin)
    assert r2.json()["codigo"] == "CO"


def test_api_tenant_pais_rechaza_codigo_invalido(cliente):
    h = _tok(cliente)
    r = cliente.post("/api/tenant/pais", json={"codigo": "BR"}, headers=h)
    assert r.status_code == 400


def test_api_tenant_pais_solo_admin_puede_cambiarlo(cliente):
    h_gestor = _tok(cliente, "GestorTest123!")
    r = cliente.post("/api/tenant/pais", json={"codigo": "AR"}, headers=h_gestor)
    assert r.status_code == 403
    # gestor sí puede leerlo
    assert cliente.get("/api/tenant/pais", headers=h_gestor).status_code == 200


def test_api_tenant_pais_aislado_por_tenant(cliente):
    h_a = _tok(cliente, empresa="kobra-test-pais")
    cliente.post("/api/tenant/pais", json={"codigo": "PE"}, headers=h_a)
    h_b = _tok(cliente, empresa="acme")
    assert cliente.get("/api/tenant/pais", headers=h_b).json()["codigo"] == "UY"
    shutil.rmtree(os.path.join(ROOT, "data", "tenants", "acme"), ignore_errors=True)
