# © 2026 Martín Viera. Todos los derechos reservados.
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


# --- 100% de los datos alcanzable, y totales -------------------------------
def test_la_agenda_pagina_en_vez_de_recortar():
    """Antes devolvía solo las 200 promesas más urgentes y el resto quedaba
    inalcanzable: con 2.258 vencidas, el 91% de la cartera en riesgo no se
    podía ver ni exportar desde la pantalla."""
    import inspect

    from webapp.backend import api
    fuente = inspect.getsource(api.agenda)
    assert "pagina" in fuente and "paginas" in fuente
    assert "limite" in fuente, "se rompió la compatibilidad con el frontend viejo"


def test_los_totales_de_gestores_ponderan_por_volumen():
    """Regresión conceptual: promediar los porcentajes de cada gestor le da el
    mismo peso al que hizo 840 gestiones que al que hizo 449, y el número sale
    mal. Las tasas se calculan sobre el total, no promediando promedios."""
    pd = pytest.importorskip("pandas")
    from webapp.backend.api import _totales_gestores
    r = pd.DataFrame({"gestor": ["A", "B"], "gestiones": [840, 449],
                      "calidad_prom": [84.0, 64.5], "tasa_conversion": [0.77, 0.62],
                      "recupero": [69.2e6, 31.6e6], "monto": [129.5e6, 87.5e6],
                      "usa_kobra": [1, 1]})
    t = _totales_gestores(r)
    assert t["gestiones"] == 1289
    assert t["recupero"] == pytest.approx(100.8e6)
    # Sobre el total: 100,8 / 217,0 — no el promedio de 0,534 y 0,361.
    assert t["tasa_recupero"] == pytest.approx(100.8 / 217.0, rel=1e-6)
    simple = (84.0 + 64.5) / 2
    assert t["calidad_prom"] != pytest.approx(simple), "quedó el promedio simple"
    assert t["calidad_prom"] == pytest.approx(77.2075, rel=1e-4)


def test_los_totales_no_rompen_con_ranking_vacio():
    pd = pytest.importorskip("pandas")
    from webapp.backend.api import _totales_gestores
    assert _totales_gestores(pd.DataFrame()) == {}
    assert _totales_gestores(None) == {}


# --- Excel formateado ------------------------------------------------------
def test_el_excel_sale_formateado_y_con_totales():
    """Un export que hay que reformatear a mano cada vez no sirve para mandar
    a gerencia."""
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    openpyxl = pytest.importorskip("openpyxl")
    import io

    from webapp.backend.api import _excel_formateado
    df = pd.DataFrame({
        "id_deudor": ["KB-1", "KB-2"],
        "monto_acordado": [12500.5, np.nan],
        "tasa_recupero": [0.54, 0.31],
        "fecha_promesa": pd.to_datetime(["2026-01-05", "2026-02-11"]),
    })
    datos = _excel_formateado({"Promesas": df}, titulo="Prueba")
    ws = openpyxl.load_workbook(io.BytesIO(datos))["Promesas"]
    filas = [list(fila) for fila in ws.iter_rows(values_only=True)]
    assert filas[0][0] == "Prueba"
    assert "TOTAL" in [f[0] for f in filas]
    total = next(f for f in filas if f[0] == "TOTAL")
    assert str(total[1]).startswith("=SUM("), "no sumó la columna de dinero"
    # Y NO suma la tasa: "tasa_recupero" contiene "recupero" y entraba por la
    # ventana, dando un total sin sentido.
    assert total[2] is None, "sumó una columna de porcentaje"


def test_el_nombre_de_hoja_no_rompe_excel():
    """Excel corta a 31 caracteres y rechaza []:*?/\\ — un nombre inválido hace
    fallar la escritura entera."""
    pd = pytest.importorskip("pandas")
    openpyxl = pytest.importorskip("openpyxl")
    import io

    from webapp.backend.api import _excel_formateado
    datos = _excel_formateado(
        {"Cartera [2026]: priorizada/final*": pd.DataFrame({"a": [1]})})
    wb = openpyxl.load_workbook(io.BytesIO(datos))
    hoja = wb.sheetnames[0]
    assert len(hoja) <= 31
    assert not set(hoja) & set("[]:*?/\\")
