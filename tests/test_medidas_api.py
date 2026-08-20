# © 2026 Martín Viera. Todos los derechos reservados.

"""Medidas calculadas contra la API: gateo, permisos y persistencia.

`tests/test_medidas.py` prueba el motor y su lista blanca. Acá se prueba lo que
lo rodea, que es donde un motor seguro se vuelve inseguro igual:

  * que el módulo esté detrás del plan,
  * que una fórmula no se pueda guardar sin validar (si no, el error explota
    en la cara de otra persona cuando abre el tablero),
  * que solo un admin pueda cambiar la definición de un KPI que después mira
    todo el equipo,
  * y que las medidas se calculen sobre los datos YA enmascarados cuando hay
    gobernanza — una medida es una vía de lectura como cualquier otra.
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-medidas-api"

_RECARGABLES = ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
                "webapp.backend.api")


def _recargar_todo():
    for nombre in _RECARGABLES:
        modulo = sys.modules.get(nombre)
        if modulo is not None:
            importlib.reload(modulo)


@pytest.fixture(autouse=True)
def _dejar_los_modulos_como_estaban(monkeypatch):
    """Recargar módulos con el entorno del test los deja apuntando a la carpeta
    temporal, y `monkeypatch` no deshace un `reload`. Sin esto, el test
    siguiente hereda esta licencia y falla por algo ajeno a él."""
    yield
    monkeypatch.undo()
    _recargar_todo()


def _montar(tmp_path, monkeypatch, plan):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)
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
    kconfig.guardar_extra("LICENCIA_TOKEN",
                          klic.emitir_licencia("cliente-dax", plan, secreto=SECRETO))

    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api, rol="admin"):
    import pandas as pd
    from fastapi.testclient import TestClient

    cartera = pd.DataFrame({
        "id_deudor": [f"KB-{100000 + i}" for i in range(4)],
        "monto_deuda": [100.0, 200.0, 300.0, 400.0],
        "dias_mora": [10, 95, 120, 5],
        "cuotas_atrasadas": [1, 3, 4, 0],
        "segmento": ["Pyme", "Individuo", "Pyme", "Corp"],
        "score_buro": [576, 620, 780, 410],
        "prob_pago": [0.8, 0.4, 0.9, 0.1],
    })
    ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    cartera.to_csv(ruta, index=False)

    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token(rol, api.EMPRESA_DEFAULT)}"})
    return cli, cartera


# ---------------------------------------------------------------------------
# Gateo por plan
# ---------------------------------------------------------------------------
def test_sin_el_modulo_invita_a_mejorar_el_plan(tmp_path, monkeypatch):
    """Pro incluye gobernanza pero NO medidas: es el escalón siguiente."""
    api = _montar(tmp_path, monkeypatch, "pro")
    cli, _ = _cliente(api)
    r = cli.get("/api/medidas")
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"
    assert "medidas calculadas" in r.json()["detail"]


def test_con_el_modulo_trae_las_medidas_de_ejemplo(tmp_path, monkeypatch):
    """Un tablero vacío no lo llena nadie: sin ejemplos, el usuario no sabe qué
    se puede escribir."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api)
    d = cli.get("/api/medidas").json()
    assert d["medidas"], "no vinieron medidas de arranque"
    assert all(v["error"] is None for v in d["valores"]), d["valores"]


def test_la_respuesta_trae_columnas_y_funciones_para_el_editor(tmp_path, monkeypatch):
    """El editor tiene que poder ofrecer qué escribir sin que el usuario
    adivine nombres de columna."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente(api)
    d = cli.get("/api/medidas").json()
    assert "monto_deuda" in d["columnas"]
    assert "suma" in d["funciones"] and "contar_si" in d["funciones"]


# ---------------------------------------------------------------------------
# Probar antes de guardar
# ---------------------------------------------------------------------------
def test_probar_una_formula_devuelve_la_vista_previa(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api)
    r = cli.post("/api/medidas/validar",
                 json={"nombre": "Deuda total", "formula": "suma(monto_deuda)"})
    d = r.json()
    assert d["ok"] is True
    assert d["vista_previa"]["valor"] == 1000.0


def test_probar_una_formula_rota_explica_el_error(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api)
    d = cli.post("/api/medidas/validar",
                 json={"nombre": "x", "formula": "suma(no_existe)"}).json()
    assert d["ok"] is False
    assert "no_existe" in d["error"]


def test_una_formula_peligrosa_se_rechaza_por_la_api(tmp_path, monkeypatch):
    """La lista blanca del motor tiene que seguir puesta cuando la fórmula
    llega por HTTP — que es como llega en producción."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api)
    d = cli.post("/api/medidas/validar",
                 json={"nombre": "x",
                       "formula": "__import__('os').system('id')"}).json()
    assert d["ok"] is False


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------
def test_guardar_y_recuperar(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api)
    r = cli.post("/api/medidas", json=[
        {"nombre": "Deuda total", "formula": "suma(monto_deuda)",
         "descripcion": "", "formato": "moneda"},
        {"nombre": "Mora alta %",
         "formula": "contar_si(dias_mora > 90) / contar() * 100",
         "descripcion": "", "formato": "porcentaje"},
    ])
    assert r.status_code == 200, r.text

    d = cli.get("/api/medidas").json()
    nombres = [m["nombre"] for m in d["medidas"]]
    assert nombres == ["Deuda total", "Mora alta %"]
    valores = {v["nombre"]: v["valor"] for v in d["valores"]}
    assert valores["Deuda total"] == 1000.0
    assert valores["Mora alta %"] == 50.0


def test_un_lote_con_una_formula_mala_no_se_guarda_a_medias(tmp_path, monkeypatch):
    """Guardar la mitad deja al cliente sin saber cuáles quedaron."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api)
    cli.post("/api/medidas", json=[
        {"nombre": "Buena", "formula": "suma(monto_deuda)"}])

    r = cli.post("/api/medidas", json=[
        {"nombre": "Buena 2", "formula": "contar()"},
        {"nombre": "Rota", "formula": "suma(fantasma)"},
    ])
    assert r.status_code == 400
    # Y la anterior sigue intacta.
    assert [m["nombre"] for m in cli.get("/api/medidas").json()["medidas"]] == ["Buena"]


def test_un_gestor_no_puede_cambiar_las_definiciones(tmp_path, monkeypatch):
    """Una medida es una definición de negocio que después ve todo el equipo.
    Si cualquiera la cambia, nadie sabe qué está mirando."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api, rol="gestor")
    r = cli.post("/api/medidas",
                 json=[{"nombre": "x", "formula": "contar()"}])
    assert r.status_code == 403


def test_un_gestor_si_puede_ver_las_medidas(tmp_path, monkeypatch):
    """Leer sí: el tablero es para todo el equipo."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api, rol="gestor")
    assert cli.get("/api/medidas").status_code == 200


# ---------------------------------------------------------------------------
# Medidas + gobernanza
# ---------------------------------------------------------------------------
def test_las_medidas_se_calculan_sobre_los_datos_enmascarados(tmp_path, monkeypatch):
    """Una medida es una vía de lectura como cualquier otra: si se calculara
    sobre los datos crudos, un gestor podría averiguar el ingreso exacto de un
    deudor pidiendo `maximo(...)` con el filtro bien puesto."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente(api, rol="gestor")

    d = cli.post("/api/medidas/validar",
                 json={"nombre": "ids", "formula": "distintos(id_deudor)"}).json()
    assert d["ok"] is True
    # El seudónimo es estable, así que la cuenta de distintos se conserva —
    # el dato analítico sigue, el identificatorio no.
    assert d["vista_previa"]["valor"] == float(cartera["id_deudor"].nunique())

    # Y una columna sensible ya no es numérica: quedó en tramos.
    roto = cli.post("/api/medidas/validar",
                    json={"nombre": "score", "formula": "promedio(score_buro)"}).json()
    assert roto["ok"] is True
    assert roto["vista_previa"]["valor"] is None, \
        "el gestor pudo promediar el score en claro pese al enmascarado"


@pytest.mark.parametrize("ruta,metodo", [
    ("/api/medidas", "get"),
    ("/api/medidas/validar", "post"),
    ("/api/medidas", "post"),
])
def test_los_endpoints_piden_sesion(tmp_path, monkeypatch, ruta, metodo):
    from fastapi.testclient import TestClient
    api = _montar(tmp_path, monkeypatch, "enterprise")
    _cliente(api)
    cli = TestClient(api.app)
    r = cli.post(ruta, json=[]) if metodo == "post" else cli.get(ruta)
    assert r.status_code == 401
