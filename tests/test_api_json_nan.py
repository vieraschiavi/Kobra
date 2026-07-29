"""Regresión del Error 500 de la Cartera priorizada.

Reportado con una cartera real del cliente: la pantalla mostraba «Error 500» y
el log del servidor decía

    ValueError: Out of range float values are not JSON compliant

La causa no estaba en la consulta ni en los filtros sino en la serialización.
JSON no puede representar NaN ni infinito, y Starlette serializa con
`allow_nan=False`, así que **una sola celda vacía** en cualquier columna
numérica tumbaba la respuesta entera — no esa fila: la pantalla completa.

Con datos sintéticos nunca aparecía, porque el generador no deja huecos. Con
una cartera real salta en cuanto falta un monto, una fecha o un score.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_sanear_reemplaza_nan_e_infinitos_en_cualquier_profundidad():
    from webapp.backend.api import _sanear
    caso = {"a": float("nan"),
            "b": [1.0, float("inf"), {"c": float("-inf")}],
            "d": "texto", "e": 3.5, "f": None, "g": 7}
    assert _sanear(caso) == {"a": None, "b": [1.0, None, {"c": None}],
                             "d": "texto", "e": 3.5, "f": None, "g": 7}


def test_los_valores_validos_no_se_tocan():
    """Un saneador demasiado entusiasta que redondee o convierta números sería
    peor que el bug: los montos tienen que llegar exactos."""
    from webapp.backend.api import _sanear
    for valor in (0.0, -0.0, 1e300, -1e300, 1234567.89, 0.1 + 0.2, True, False):
        assert _sanear(valor) == valor
    assert _sanear("NaN") == "NaN"          # el string no es un float


def test_una_celda_vacia_ya_no_tumba_la_respuesta():
    """El caso real, de punta a punta: una fila de cartera con un dato faltante
    devolvía 500 y ahora devuelve 200 con ese campo en null."""
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from webapp.backend.api import JSONLimpia

    fila = pd.DataFrame([{"id": "KB-1", "monto": 1000.0,
                          "dias_mora": np.nan, "prob": 0.7}])

    sin_arreglo = FastAPI()
    con_arreglo = FastAPI(default_response_class=JSONLimpia)
    for app in (sin_arreglo, con_arreglo):
        app.get("/cartera")(lambda: {"filas": fila.to_dict("records")})

    # Se verifica también el ANTES: si algún día Starlette empezara a aceptar
    # NaN, este test dejaría de estar probando lo que cree probar.
    r = TestClient(sin_arreglo, raise_server_exceptions=False).get("/cartera")
    assert r.status_code == 500, "el bug ya no se reproduce: revisar este test"

    r = TestClient(con_arreglo).get("/cartera")
    assert r.status_code == 200
    assert r.json()["filas"][0]["dias_mora"] is None
    assert r.json()["filas"][0]["monto"] == 1000.0


def test_la_api_real_usa_la_respuesta_saneada():
    """El arreglo va en la app, no en un endpoint: el mismo defecto acecha en
    cualquier respuesta armada con `to_dict("records")` — KPIs, agenda,
    gestores— y taparlos de a uno deja afuera los que vengan."""
    from webapp.backend import api
    assert api.app.router.default_response_class is api.JSONLimpia
