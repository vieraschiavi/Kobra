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


def _xlsx_columnas_raras():
    """Excel estilo export de ProbPago/ERP: nombres de columna que NO son los
    nuestros (camelCase, otro idioma, moneda formateada). Debe adaptarse solo."""
    df = pd.DataFrame({
        "IdCliente": ["C1", "C2", "C3"],
        "Nombre Cliente": ["Ana", "Beto", "Caro"],
        "Celular": ["099111", "098222", "097333"],
        "MontoDeuda": ["$ 1.234.567", "50.000", "8.900,50"],
        "DiasAtraso": [45, 10, 200],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_origen_default_es_demo(cliente):
    api, c = cliente
    h = _h_admin(c)
    origen = c.get("/api/cartera/origen", headers=h).json()
    assert origen["tipo"] == "demo" and origen["modo"] == "demo"
    assert origen["hay_real"] is False  # sin cartera real subida, el botón está deshabilitado


def test_mapea_columnas_parecidas():
    """El corazón del pedido: adaptarse a nombres de columna similares."""
    from kobra import cartera_manual as kc
    m = kc.mapear_columnas(["IdCliente", "Nombre Cliente", "Celular",
                            "MontoDeuda", "DiasAtraso"])
    assert m["MontoDeuda"] == "monto_deuda"
    assert m["Nombre Cliente"] == "nombre"
    assert m["Celular"] == "telefono"
    assert m["DiasAtraso"] == "dias_mora"
    # Otros idiomas + sinónimos de deuda
    for col in ["Saldo Vencido", "Dívida Total", "Total Debt", "Importe", "saldo"]:
        assert kc.mapear_columnas([col]).get(col) == "monto_deuda", col


def test_parseo_moneda_formateada():
    from kobra import cartera_manual as kc
    assert kc._a_numero("$ 1.234.567,89") == 1234567.89   # es: miles '.', dec ','
    assert kc._a_numero("1,234,567.89") == 1234567.89     # en: miles ',', dec '.'
    assert kc._a_numero("R$ 5.000") == 5000.0
    assert kc._a_numero("45%") == 0.45
    assert pd.isna(kc._a_numero(""))


def test_importar_xlsx_con_columnas_raras(cliente):
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        r = c.post("/api/tenant/alta", json={"empresa": "test-cols-raras"}, headers=h_principal)
        assert r.status_code == 200, r.text
        h = _h_admin(c, empresa="test-cols-raras")
        r = c.post("/api/cartera/importar", headers=h, files={"archivo": (
            "ProbPago_export.xlsx", _xlsx_columnas_raras(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deudores"] == 3
        # El monto formateado '$ 1.234.567' se parseó bien.
        assert abs(d["cartera_total_uyu"] - (1234567 + 50000 + 8900.5)) < 1
        assert d["columnas_detectadas"]["MontoDeuda"] == "monto_deuda"
        kpis = c.get("/api/kpis", headers=h).json()
        assert kpis["deudores"] == 3
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-cols-raras"),
                      ignore_errors=True)


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
        assert origen["tipo"] == "real" and origen["modo"] == "real"
        assert origen["hay_real"] is True
        assert origen["archivo"] == "mi_cartera.csv"
        assert origen["deudores"] == 3
        assert "cargado_en" in origen
        assert c.get("/api/cartera/origen", headers=h_principal).json()["tipo"] == "demo"

        # Botón demo ON: volver a la demo NO pierde la cartera real (se puede
        # re-activar), y el dashboard entero vuelve a los datos sintéticos.
        c.post("/api/cartera/modo", json={"modo": "demo"}, headers=h)
        assert c.get("/api/kpis", headers=h).json()["deudores"] == 2000
        origen_demo = c.get("/api/cartera/origen", headers=h).json()
        assert origen_demo["modo"] == "demo" and origen_demo["hay_real"] is True

        # Botón demo OFF: re-activar la cartera real que ya estaba subida.
        c.post("/api/cartera/modo", json={"modo": "real"}, headers=h)
        assert c.get("/api/kpis", headers=h).json()["deudores"] == 3
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-importar-cartera"),
                      ignore_errors=True)


def test_activar_modo_real_sin_cartera_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    # No se puede activar 'real' si nunca se subió una cartera real.
    r = c.post("/api/cartera/modo", json={"modo": "real"}, headers=h)
    assert r.status_code == 400


def test_modo_invalido_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/cartera/modo", json={"modo": "otro"}, headers=h)
    assert r.status_code == 400


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


def test_importar_sql_desde_base_reemplaza_dashboard(cliente, tmp_path):
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        r = c.post("/api/tenant/alta", json={"empresa": "test-importar-sql"},
                  headers=h_principal)
        assert r.status_code == 200, r.text
        h = _h_admin(c, empresa="test-importar-sql")

        # Base SQLite del "cliente" con su cartera real.
        import sqlalchemy as sa
        db = tmp_path / "cartera_cliente.db"
        eng = sa.create_engine(f"sqlite:///{db}")
        pd.DataFrame({
            "nombre": ["Ana", "Beto", "Caro", "Dani"],
            "telefono": ["0991", "0992", "0993", "0994"],
            "monto_deuda": [10000, 25000, 5000, 40000],
            "dias_mora": [30, 90, 15, 200],
        }).to_sql("cartera", eng, index=False)
        eng.dispose()

        r = c.post("/api/cartera/importar-sql", headers=h, json={
            "conn_url": f"sqlite:///{db}",
            "consulta": "SELECT nombre, telefono, monto_deuda, dias_mora FROM cartera"})
        assert r.status_code == 200, r.text
        assert r.json()["deudores"] == 4

        kpis = c.get("/api/kpis", headers=h).json()
        assert kpis["deudores"] == 4
        origen = c.get("/api/cartera/origen", headers=h).json()
        assert origen["modo"] == "real" and origen["archivo"] == "Base de datos (SQL)"
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-importar-sql"),
                      ignore_errors=True)


def test_importar_sql_rechaza_consulta_de_escritura(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/cartera/importar-sql", headers=h, json={
        "conn_url": "sqlite:///x.db",
        "consulta": "DELETE FROM cartera"})
    assert r.status_code == 422  # solo lectura (SELECT/WITH)


def test_importar_sql_requiere_admin(cliente):
    api, c = cliente
    from kobra import autenticacion as kauth
    kauth.establecer_password("gestor", "GestorTest123!")
    r = c.post("/api/auth/login", json={"password": "GestorTest123!"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = c.post("/api/cartera/importar-sql", headers=h,
               json={"conn_url": "sqlite:///x.db", "consulta": "SELECT 1"})
    assert r2.status_code == 403
