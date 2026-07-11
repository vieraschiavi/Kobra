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
