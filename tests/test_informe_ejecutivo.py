# © 2026 Martín Viera. Todos los derechos reservados.
"""Tests del informe ejecutivo en PDF (kobra/informe_ejecutivo.py + endpoint)."""
import importlib
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import informe_ejecutivo as kinforme  # noqa: E402


def _scored_demo(n=60):
    import numpy as np
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "id_deudor": [f"KB-{i:05d}" for i in range(n)],
        "monto_deuda": rng.uniform(5_000, 900_000, n),
        "valor_esperado_recupero": rng.uniform(1_000, 400_000, n),
        "probpago": rng.uniform(0, 1, n),
        "dias_mora": rng.integers(1, 300, n),
        "segmento_propension": rng.choice(["Alta", "Media", "Baja"], n),
        "tramo_mora": rng.choice(["1-30", "31-60", "61-90", "91-180", "180+"], n),
        "segmento": rng.choice(["Corporativo", "Pyme", "Retail"], n),
    })


def test_informe_pdf_es():
    pdf = kinforme.generar_pdf(_scored_demo(), None, empresa="principal",
                               codigo_pais="UY", datos_demo=True)
    assert pdf.startswith(b"%PDF") and len(pdf) > 2_000


def test_informe_pdf_pt_brasil():
    # país BR → textos en portugués y moneda R$; no debe explotar por acentos
    pdf = kinforme.generar_pdf(_scored_demo(), None, empresa="acme-br",
                               codigo_pais="BR", datos_demo=False)
    assert pdf.startswith(b"%PDF") and len(pdf) > 2_000


def test_informe_pdf_con_gestiones():
    # Mismo esquema que data/kobra_gestiones.csv (lo que agrega ranking_gestores)
    gestiones = pd.DataFrame({
        "id_gestion": [f"GST-{i:04d}" for i in range(20)],
        "gestor_id": ["G1", "G2", "G1", "G3"] * 5,
        "gestor": ["Ana", "Luis", "Ana", "Mara"] * 5,
        "resultado": ["Promesa de pago", "Sin acuerdo", "Pago total", "Promesa de pago"] * 5,
        "canal": ["Llamada", "WhatsApp", "Llamada", "Email"] * 5,
        "usa_kobra": [True, False, True, True] * 5,
        "calidad_gestion": [80.0, 60.0, 90.0, 70.0] * 5,
        "monto_gestionado": [10000, 20000, 15000, 12000] * 5,
        "recupero": [5000, 0, 15000, 4000] * 5,
    })
    pdf = kinforme.generar_pdf(_scored_demo(), gestiones, empresa="principal",
                               codigo_pais="UY", datos_demo=True)
    assert pdf.startswith(b"%PDF") and len(pdf) > 2_000


# --- endpoint ----------------------------------------------------------------
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    from fastapi.testclient import TestClient

    from webapp.backend import api
    return TestClient(api.app)


def test_api_informe_ejecutivo_pdf(cliente):
    r = cliente.post("/api/auth/login", json={"password": "AdminTest123!"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    resp = cliente.get("/api/informe/ejecutivo.pdf", headers=h)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "informe_ejecutivo.pdf" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")
    # sin token → 401
    assert cliente.get("/api/informe/ejecutivo.pdf").status_code == 401


def test_informe_email_sin_smtp_falla_claro(monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    r = kinforme.enviar_por_email("a@b.com", _scored_demo(), None,
                                  empresa="principal")
    assert not r["ok"] and "SMTP" in r["detalle"]


def test_informe_email_envia_con_smtp_mockeado(monkeypatch):
    import smtplib

    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USER", "user@test")
    monkeypatch.setenv("SMTP_PASSWORD", "secreto")
    monkeypatch.setenv("SMTP_FROM", "cobranzas@test")

    enviados = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            enviados["host"] = host
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            pass
        def login(self, u, p):
            enviados["login"] = u
        def sendmail(self, de, para, cuerpo):
            enviados["para"] = para
            enviados["tiene_pdf"] = "application/pdf" in cuerpo
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    r = kinforme.enviar_por_email("gerente@empresa.com", _scored_demo(), None,
                                  empresa="principal", codigo_pais="UY")
    assert r["ok"], r["detalle"]
    assert enviados["para"] == ["gerente@empresa.com"]
    assert enviados["tiene_pdf"]


def _h_admin(cliente):
    r = cliente.post("/api/auth/login", json={"password": "AdminTest123!"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_informe_programacion(cliente):
    h = _h_admin(cliente)
    d = cliente.get("/api/informe/programacion", headers=h).json()
    assert d["activo"] is False and d["destino"] == ""
    # activar sin email válido → 400
    r = cliente.post("/api/informe/programacion",
                     json={"activo": True, "destino": "no-es-email"}, headers=h)
    assert r.status_code == 400
    # activar bien → persiste
    r = cliente.post("/api/informe/programacion",
                     json={"activo": True, "destino": "gerente@empresa.com"}, headers=h)
    assert r.status_code == 200
    d2 = cliente.get("/api/informe/programacion", headers=h).json()
    assert d2["activo"] is True and d2["destino"] == "gerente@empresa.com"


def test_api_tenant_alta_y_aislamiento(cliente):
    import shutil
    h = _h_admin(cliente)
    try:
        r = cliente.post("/api/tenant/alta", json={"empresa": "Demo Prospecto!"}, headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["empresa"] == "demo-prospecto" and d["deudores"] == 2000
        # la empresa nueva ya tiene cartera propia consultable
        r2 = cliente.post("/api/auth/login",
                          json={"password": "AdminTest123!", "empresa": "demo-prospecto"})
        h2 = {"Authorization": f"Bearer {r2.json()['token']}"}
        k = cliente.get("/api/kpis", headers=h2).json()
        assert k["deudores"] == 2000
        # nombre repetido → 409 · nombre reservado → 400 · corto → 400
        assert cliente.post("/api/tenant/alta", json={"empresa": "demo-prospecto"},
                            headers=h).status_code == 409
        assert cliente.post("/api/tenant/alta", json={"empresa": "principal"},
                            headers=h).status_code == 400
        assert cliente.post("/api/tenant/alta", json={"empresa": "ab"},
                            headers=h).status_code == 400
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "demo-prospecto"),
                      ignore_errors=True)
