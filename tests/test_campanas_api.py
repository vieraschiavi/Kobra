# © 2026 Martín Viera. Todos los derechos reservados.

"""El módulo de campañas visto desde la API.

Dos cosas que no se ven testeando el motor solo:

1. **El candado.** Campañas va con la misma licencia que logística, y sobre
   las mismas tablas. Un cliente que no compró ese módulo no tiene que poder
   entrar por esta puerta nueva.
2. **Que el JSON salga.** El motor puede devolver un `NaN` perfectamente
   razonable en pandas que después rompe el `fetch` del navegador sin ningún
   error visible.
"""
import importlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

_RECARGABLES = ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
                "webapp.backend.api")


@pytest.fixture(autouse=True)
def _dejar_los_modulos_como_estaban(monkeypatch):
    yield
    monkeypatch.undo()
    for nombre in _RECARGABLES:
        m = sys.modules.get(nombre)
        if m is not None:
            importlib.reload(m)


def _montar(tmp_path, monkeypatch, extras=("logistica",)):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.delenv("KOBRA_OWNER", raising=False)

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import rutas as krutas
    importlib.reload(krutas)
    from kobra import edicion as kedicion
    importlib.reload(kedicion)
    from kobra import plan as kplan
    importlib.reload(kplan)

    from backend_venta import licencias as klic
    feats = [*klic.PLANES["enterprise"]["features"], *extras]
    kconfig.guardar_extra(
        "LICENCIA_TOKEN",
        klic.emitir_licencia("cliente-camp", "enterprise",
                             cupo_mensual=None, features=feats))
    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api):
    from fastapi.testclient import TestClient
    cli = api and __import__("fastapi.testclient", fromlist=["TestClient"])
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token('admin', api.EMPRESA_DEFAULT)}"})
    return cli


def _cargar_tablas(api, con_sku_fantasma=False):
    """Deja productos y ventas como si el cliente ya los hubiera subido."""
    rng = np.random.default_rng(11)
    productos = pd.DataFrame({
        "sku": [f"S{i}" for i in range(5)], "nombre": [f"P{i}" for i in range(5)],
        "categoria": ["A"] * 5, "precio": [1000.0] * 5,
        "costo": [600.0] * 5, "stock": [400] * 5})
    filas = []
    for desde, hasta, lineas, desc, camp in (
            ("2026-01-01", "2026-03-31", 6, 0.0, None),
            ("2026-04-01", "2026-04-07", 18, 0.15, "Hot Sale")):
        for dia in pd.date_range(desde, hasta):
            for _ in range(lineas):
                filas.append({"fecha": dia, "sku": f"S{rng.integers(0, 5)}",
                              "cantidad": int(rng.integers(1, 4)),
                              "cliente_id": f"C{rng.integers(0, 30):02d}",
                              "precio_unit": 1000.0 * (1 - desc),
                              "campania": camp})
    if con_sku_fantasma:
        # Un SKU que se vendió y no está en el maestro: el que dejaba NaN.
        filas.append({"fecha": "2026-04-03", "sku": "S99", "cantidad": 9,
                      "cliente_id": "C01", "precio_unit": 850.0,
                      "campania": "Hot Sale"})

    for tabla, df in (("productos", productos), ("ventas", pd.DataFrame(filas))):
        ruta = api._archivo_modulo(api.EMPRESA_DEFAULT, "logistica", tabla)
        import os
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        df.to_csv(ruta, index=False)


def test_sin_el_modulo_de_logistica_campanias_no_abre(tmp_path, monkeypatch):
    """Es la misma licencia: no puede ser una puerta de atrás al mismo dato."""
    api = _montar(tmp_path, monkeypatch, extras=())
    _cargar_tablas(api)
    r = _cliente(api).get("/api/campanas/resumen")
    assert r.status_code == 403, r.text
    assert "plan" in r.text.lower()


def test_con_el_modulo_devuelve_el_panel_completo(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    _cargar_tablas(api)
    r = _cliente(api).get("/api/campanas/resumen")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) >= {"titulos", "rfm", "segmentos", "cohortes", "ediciones",
                      "detalle", "descuento_medible", "aviso_descuento"}
    assert d["ediciones"] and d["ediciones"][0]["campania"] == "Hot Sale"
    # Las fechas salen como texto, no como un timestamp que el front no parsea.
    assert d["ediciones"][0]["desde"] == "2026-04-01"
    assert d["descuento_medible"] is True
    assert d["detalle"]["contra_normal"]["campania"]["descuento_pct"] == pytest.approx(
        15.0, abs=0.1)


def test_un_sku_fuera_del_maestro_no_deja_la_pantalla_en_blanco(tmp_path, monkeypatch):
    """`NaN` no es JSON válido: el fetch falla entero y no se ve ningún error.

    Se valida con el parser estricto, porque el de Python acepta `NaN` por
    defecto y dejaría pasar exactamente el bug que esto cuida.
    """
    import json
    api = _montar(tmp_path, monkeypatch)
    _cargar_tablas(api, con_sku_fantasma=True)
    r = _cliente(api).get("/api/campanas/resumen")
    assert r.status_code == 200, r.text
    json.loads(r.content)                       # el body es JSON de verdad
    assert "NaN" not in r.text and "Infinity" not in r.text
    stock = r.json()["detalle"]["stock"]
    fantasma = [f for f in stock if f["sku"] == "S99"]
    assert fantasma and fantasma[0]["cobertura_dias"] is None


def test_se_puede_pedir_una_campania_puntual(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    _cargar_tablas(api)
    r = _cliente(api).get("/api/campanas/resumen", params={"campania": "Hot Sale"})
    assert r.status_code == 200, r.text
    assert r.json()["detalle"]["campania"] == "Hot Sale"


def test_el_idioma_llega_hasta_los_nombres_de_segmento(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    _cargar_tablas(api)
    cli = _cliente(api)
    es = cli.get("/api/campanas/resumen").json()["titulos"]
    en = cli.get("/api/campanas/resumen",
                 headers={"Accept-Language": "en"}).json()["titulos"]
    assert es["rfm"] != en["rfm"], "el título no se tradujo"


def test_sin_las_tablas_cargadas_dice_cual_falta(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    r = _cliente(api).get("/api/campanas/resumen")
    assert r.status_code == 404
    assert "productos" in r.text or "subila" in r.text.lower()
