"""Tests del motor de originación (kobra/originacion.py) y sus endpoints."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import originacion as korig  # noqa: E402


@pytest.fixture(scope="module")
def modelo():
    df = korig.generar_solicitudes_sinteticas()
    return korig.OriginacionModel().fit(df)


def test_originacion_dataset_sintetico_deterministico():
    a = korig.generar_solicitudes_sinteticas(n=500, semilla=7)
    b = korig.generar_solicitudes_sinteticas(n=500, semilla=7)
    assert a.equals(b)
    assert set(korig.NUM_FEATURES + korig.CAT_FEATURES +
               ["id_solicitud", "fecha_solicitud", korig.TARGET]) <= set(a.columns)
    assert 0.05 < a[korig.TARGET].mean() < 0.35   # desbalance realista, no degenerado


def test_originacion_walk_forward_y_benchmark_honesto(modelo):
    m = modelo.metrics
    assert "walk-forward" in m["validacion"]
    assert m["auc_walk_forward"] > 0.75           # discrimina de verdad
    assert m["ks_walk_forward"] > 0.3
    # el benchmark es la regla del oficial, y el modelo debe ganarle
    assert m["auc_walk_forward"] > m["auc_regla_oficial"]
    assert m["mejora_vs_regla"] > 0


def test_originacion_decisiones_por_umbral(modelo):
    bueno = dict(edad=45, ingreso_declarado=90000, antiguedad_laboral_meses=180,
                 monto_solicitado=60000, plazo_meses=24, antiguedad_socio_meses=120,
                 creditos_previos=3, atrasos_previos=0, tipo_credito="Consumo",
                 situacion_laboral="Dependiente", departamento="Montevideo")
    r = modelo.evaluar(bueno)
    assert r["decision"] == "Aprobar" and r["score"] > 800
    assert r["confianza"] == "Alta"
    assert r["monto_sugerido"] == 60000           # aprobado: monto pedido completo

    malo = dict(edad=23, ingreso_declarado=18000, antiguedad_laboral_meses=3,
                monto_solicitado=400000, plazo_meses=6, antiguedad_socio_meses=1,
                creditos_previos=2, atrasos_previos=2, tipo_credito="Consumo",
                situacion_laboral="Independiente", departamento="Montevideo")
    r2 = modelo.evaluar(malo)
    assert r2["decision"] == "Rechazar" and r2["prob_mora"] > korig.UMBRAL_RECHAZAR
    assert r2["monto_sugerido"] == 0


def test_originacion_razones_en_lenguaje_simple(modelo):
    malo = dict(edad=23, ingreso_declarado=18000, antiguedad_laboral_meses=3,
                monto_solicitado=400000, plazo_meses=6, antiguedad_socio_meses=1,
                creditos_previos=2, atrasos_previos=2, tipo_credito="Consumo",
                situacion_laboral="Independiente", departamento="Montevideo")
    razones = modelo.evaluar(malo)["razones"]
    assert 1 <= len(razones) <= 3
    for rz in razones:
        assert rz["factor"] in korig.ETIQUETAS.values()     # sin jerga ML
        assert rz["direccion"] in ("sube el riesgo", "baja el riesgo")


def test_originacion_datos_insuficientes_deriva_siempre(modelo):
    r = modelo.evaluar(dict(monto_solicitado=50000, plazo_meses=12))
    assert r["confianza"] == "Baja"
    assert r["decision"] == "Derivar a análisis"   # nunca auto-decide con 2/11 datos
    assert r["datos_presentes"] == "2/11"


def test_originacion_evaluar_lote(modelo):
    df = korig.generar_solicitudes_sinteticas(n=30, semilla=99)
    out = modelo.evaluar_lote(df)
    assert len(out) == 30
    assert {"prob_mora", "score", "decision", "confianza"} <= set(out.columns)
    assert out["decision"].isin(["Aprobar", "Derivar a análisis", "Rechazar"]).all()


# --- endpoints -------------------------------------------------------------
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


def _h(cliente):
    r = cliente.post("/api/auth/login", json={"password": "AdminTest123!"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_originacion_score_y_metricas(cliente):
    h = _h(cliente)
    r = cliente.post("/api/originacion/score", json={"solicitud": {
        "edad": 40, "ingreso_declarado": 80000, "antiguedad_laboral_meses": 120,
        "monto_solicitado": 50000, "plazo_meses": 24, "antiguedad_socio_meses": 60,
        "creditos_previos": 2, "atrasos_previos": 0, "tipo_credito": "Consumo",
        "situacion_laboral": "Dependiente", "departamento": "Montevideo"}}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["decision"] in ("Aprobar", "Derivar a análisis", "Rechazar")
    assert d["modelo_demo"] is True                # honestidad: entrenado con demo
    assert d["metricas_modelo"]["auc_walk_forward"] > 0.7

    m = cliente.get("/api/originacion/metricas", headers=h).json()
    assert "walk-forward" in m["validacion"]


def test_api_nba_por_deudor(cliente):
    h = _h(cliente)
    primero = cliente.get("/api/cartera?tamano=1", headers=h).json()["filas"][0]["id_deudor"]
    r = cliente.get(f"/api/nba/{primero}", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert {"canal", "estrategia", "guion_sugerido", "prioridad", "motivo"} <= set(d)
    assert cliente.get("/api/nba/NO-EXISTE", headers=h).status_code == 404
