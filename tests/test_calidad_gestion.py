"""Tests del motor de calidad de gestión (rúbrica 14 criterios) y la
comparativa Gestor IA vs Humano, más los endpoints /api/calidad/*."""
import importlib
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_BUENA = """Gestor: Hola, buenos días, le hablo de cobranzas. ¿Hablo con el señor Martín, el titular?
Cliente: Sí, soy yo.
Gestor: Gracias. Veo que registra un saldo de 120.000 pesos con vencimiento el mes pasado. ¿Qué pasó, cómo está?
Cliente: Estoy complicado, no me alcanza.
Gestor: Entiendo su situación, comprendo que es difícil. Busquemos algo: podemos hacer un plan en cuotas o un descuento si paga el total. ¿Qué le parece?
Cliente: ¿En cuotas cuánto sería?
Gestor: Le propongo 3 cuotas, la primera para el día 25. Le envío el link de pago y lo dejo registrado en el sistema. Muchas gracias, quedo a disposición.
Cliente: Dale."""

_MALA = """Gestor: Pagá la deuda o te mando a legales. Chau."""


def test_evaluar_buena_vs_mala():
    from kobra import calidad_gestion as cg
    b = cg.evaluar(_BUENA, canal="Llamada", usar_ia=False)
    m = cg.evaluar(_MALA, canal="Llamada", usar_ia=False)
    assert 0 <= m["puntaje_total"] < b["puntaje_total"] <= 100
    assert b["puntaje_total"] >= 80 and b["categoria"] in ("Muy buena", "Excelente")
    assert len(b["criterios"]) == 14
    assert sum(c["max"] for c in b["criterios"]) == 100
    # La mala tiene oportunidades de mejora concretas.
    assert m["oportunidades"]


def test_no_penaliza_criterios_que_no_aplican():
    """Cumplimiento normativo / tono / registro tienen piso alto (no se
    penaliza fuerte si no hay señales explícitas)."""
    from kobra import calidad_gestion as cg
    r = cg.evaluar(_BUENA, canal="Llamada", usar_ia=False)
    normativo = next(c for c in r["criterios"] if c["nombre"] == "Cumplimiento normativo")
    assert normativo["puntaje"] >= normativo["max"] * 0.7


def test_comparativa_ia_vs_humano():
    from kobra import calidad_gestion as cg
    g = pd.DataFrame({
        "tipo_gestor": ["IA", "IA", "Humano", "Humano"],
        "gestor_id": ["IA01", "IA01", "G01", "G01"],
        "gestor": ["Gestor IA01", "Gestor IA01", "Gestor 01", "Gestor 01"],
        "canal": ["Llamada", "WhatsApp", "Llamada", "Llamada"],
        "calidad_gestion": [85.0, 80.0, 60.0, 64.0],
        "resultado": ["Pago", "Promesa", "Sin acuerdo", "Pago"],
        "recupero": [10000, 5000, 0, 3000],
    })
    comp = cg.comparativa(g)
    tipos = {t["tipo"]: t for t in comp["por_tipo"]}
    assert tipos["IA"]["calidad_prom"] > tipos["Humano"]["calidad_prom"]
    assert tipos["IA"]["tasa_conversion"] == 100.0  # Pago + Promesa
    assert comp["ranking"][0]["tipo"] == "IA"       # ordenado por calidad
    # Filtro por canal.
    solo_wpp = cg.comparativa(g, canal="WhatsApp")
    assert solo_wpp["total_gestiones"] == 1


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


def test_endpoint_evaluar_y_comparativa(cliente):
    api, c = cliente
    h = _h(c)
    r = c.post("/api/calidad/evaluar", headers=h,
               json={"transcripcion": _BUENA, "canal": "Llamada"})
    assert r.status_code == 200, r.text
    assert r.json()["puntaje_total"] > 0 and len(r.json()["criterios"]) == 14
    # transcripción muy corta → 422
    assert c.post("/api/calidad/evaluar", headers=h,
                  json={"transcripcion": "hola"}).status_code == 422
    comp = c.get("/api/calidad/comparativa", headers=h).json()
    assert "por_tipo" in comp and "ranking" in comp and "canales" in comp
