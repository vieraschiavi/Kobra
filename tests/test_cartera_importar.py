"""Tests de /api/cartera/importar: subir la cartera real (CSV/Excel) debe
reemplazar los datos de demo en TODO el dashboard, no solo simular una
negociación aparte. Bug real reportado: el cliente subía un CSV/Excel y
seguía viendo datos de demo — nunca existía este camino completo.

Usa un tenant aislado (como test_api_tenant_alta_y_aislamiento) para la
subida destructiva, así nunca toca outputs/kobra_scored.csv del repo."""
import importlib
import io
import os
import shutil
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import cartera_manual as kcartera
    importlib.reload(kcartera)  # limpia _MODELO_PRIOR cacheado de otro test
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    from fastapi.testclient import TestClient
    from webapp.backend import api
    importlib.reload(api)
    return api, TestClient(api.app)


def _h_admin(cliente, empresa=None):
    cuerpo = {"password": "AdminTest123!"}
    if empresa:
        cuerpo["empresa"] = empresa
    r = cliente.post("/api/auth/login", json=cuerpo)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _csv_cartera_real():
    df = pd.DataFrame({
        "nombre": ["Juan Pérez", "María Silva", "Carlos Notario"],
        "telefono": ["099111222", "098333444", "097555666"],
        "deuda": [50000, 120000, 8000],
        "dias_mora": [45, 10, 200],
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def test_origen_default_es_demo(cliente):
    api, c = cliente
    h = _h_admin(c)
    assert c.get("/api/cartera/origen", headers=h).json() == {"tipo": "demo"}


def test_importar_csv_reemplaza_dashboard_completo(cliente):
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        r = c.post("/api/tenant/alta", json={"empresa": "test-importar-cartera"},
                  headers=h_principal)
        assert r.status_code == 200, r.text
        h = _h_admin(c, empresa="test-importar-cartera")

        kpis_antes = c.get("/api/kpis", headers=h).json()
        assert kpis_antes["deudores"] == 2000  # la demo del tenant (muestra)

        r = c.post("/api/cartera/importar", headers=h,
                  files={"archivo": ("mi_cartera.csv", _csv_cartera_real(), "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deudores"] == 3

        # El dashboard entero (KPIs) ahora refleja la cartera real, no la demo.
        kpis_despues = c.get("/api/kpis", headers=h).json()
        assert kpis_despues["deudores"] == 3
        assert abs(kpis_despues["cartera_uyu"] - 178_000) < 1

        # Y la cartera priorizada trae los 3 deudores reales, con estrategia.
        cartera = c.get("/api/cartera", headers=h).json()
        assert len(cartera["filas"]) == 3
        fila = cartera["filas"][0]
        assert "estrategia" in fila and "probpago" in fila

        # Origen ahora marca "real", con fecha y nombre de archivo — nunca se
        # disfraza de demo. Y el tenant "principal" no se tocó.
        origen = c.get("/api/cartera/origen", headers=h).json()
        assert origen["tipo"] == "real"
        assert origen["archivo"] == "mi_cartera.csv"
        assert origen["deudores"] == 3
        assert "cargado_en" in origen
        assert c.get("/api/cartera/origen", headers=h_principal).json() == {"tipo": "demo"}
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-importar-cartera"),
                      ignore_errors=True)


def test_importar_csv_vacio_de_deuda_da_422(cliente):
    api, c = cliente
    h = _h_admin(c)
    buf = io.StringIO()
    pd.DataFrame({"nombre": ["Sin Deuda"]}).to_csv(buf, index=False)
    r = c.post("/api/cartera/importar", headers=h,
              files={"archivo": ("vacio.csv", buf.getvalue().encode(), "text/csv")})
    assert r.status_code == 422


def test_importar_extension_no_soportada_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/cartera/importar", headers=h,
              files={"archivo": ("cartera.txt", b"algo", "text/plain")})
    assert r.status_code == 400


def test_importar_requiere_admin(cliente):
    api, c = cliente
    from kobra import autenticacion as kauth
    kauth.establecer_password("gestor", "GestorTest123!")
    r = c.post("/api/auth/login", json={"password": "GestorTest123!"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = c.post("/api/cartera/importar", headers=h,
               files={"archivo": ("x.csv", _csv_cartera_real(), "text/csv")})
    assert r2.status_code == 403
