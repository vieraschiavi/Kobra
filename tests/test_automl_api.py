# © 2026 Martín Viera. Todos los derechos reservados.

"""AutoML contra la API: gateo, permisos y qué pasa con el archivo subido.

`tests/test_automl.py` prueba el motor y la honestidad de la métrica. Acá se
prueba lo que lo rodea: quién puede entrenar, qué se hace con los datos que
sube el cliente, y que un archivo malo dé un mensaje y no un 500.
"""
import importlib
import io
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-automl-api"

_RECARGABLES = ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
                "webapp.backend.api")


def _recargar_todo():
    for nombre in _RECARGABLES:
        modulo = sys.modules.get(nombre)
        if modulo is not None:
            importlib.reload(modulo)


@pytest.fixture(autouse=True)
def _dejar_los_modulos_como_estaban(monkeypatch):
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
                          klic.emitir_licencia("cliente-ml", plan, secreto=SECRETO))

    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api, rol="admin"):
    from fastapi.testclient import TestClient
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token(rol, api.EMPRESA_DEFAULT)}"})
    return cli


def _csv(n=400, semilla=0) -> bytes:
    """Dataset sintético del cliente, en memoria."""
    r = np.random.default_rng(semilla)
    dias = r.integers(0, 300, n)
    score = r.integers(300, 950, n)
    z = 2.2 - 0.011 * dias + 0.004 * (score - 600)
    df = pd.DataFrame({
        "dias_mora": dias,
        "score_buro": score,
        "monto_deuda": r.gamma(2.0, 60000, n).round(2),
        "segmento": r.choice(["Pyme", "Individuo", "Corp"], n),
        "pago": r.binomial(1, 1 / (1 + np.exp(-z))),
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _subir(cli, ruta, contenido, **params):
    return cli.post(ruta, params=params,
                    files={"archivo": ("cartera.csv", contenido, "text/csv")})


# ---------------------------------------------------------------------------
# Gateo por plan
# ---------------------------------------------------------------------------
def test_sin_el_modulo_invita_a_mejorar_el_plan(tmp_path, monkeypatch):
    """Starter trae gobernanza y medidas pero no AutoML: es el último escalón."""
    api = _montar(tmp_path, monkeypatch, "starter")
    cli = _cliente(api)
    r = _subir(cli, "/api/automl/columnas", _csv())
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"
    assert "tus propios datos" in r.json()["detail"]


def test_con_el_modulo_lee_las_columnas_del_archivo(tmp_path, monkeypatch):
    """Primer paso del flujo: el usuario tiene que ver qué subió antes de
    elegir qué predecir."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    d = _subir(cli, "/api/automl/columnas", _csv()).json()
    assert "pago" in d["columnas"]
    assert d["filas"] == 400
    assert len(d["vista"]) == 5


# ---------------------------------------------------------------------------
# Entrenar
# ---------------------------------------------------------------------------
def test_entrena_y_devuelve_el_informe_honesto(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    r = _subir(cli, "/api/automl/entrenar", _csv(n=600, semilla=1),
               objetivo="pago")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["modelo_elegido"]
    assert d["holdout"]["auc"] > 0.6
    # Lo que separa este informe de una propaganda:
    assert "brecha_seleccion_holdout" in d
    assert d["filas"]["holdout"] > 0
    assert d["importancias"], "no se puede explicar el modelo"


def test_el_informe_es_serializable(tmp_path, monkeypatch):
    """El objeto del modelo no puede viajar al frontend."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    d = _subir(cli, "/api/automl/entrenar", _csv(), objetivo="pago").json()
    assert "pipeline" not in d


def test_un_dataset_malo_da_400_y_no_500(tmp_path, monkeypatch):
    """El problema está en los datos que subió el cliente, no en el programa.
    Un 500 le diría que Kobra está roto."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    r = _subir(cli, "/api/automl/entrenar", _csv(n=20), objetivo="pago")
    assert r.status_code == 400
    assert "filas" in r.json()["detail"]


def test_una_columna_objetivo_inexistente_se_explica(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    r = _subir(cli, "/api/automl/entrenar", _csv(), objetivo="no_existe")
    assert r.status_code == 400
    assert "no_existe" in r.json()["detail"]


def test_un_archivo_que_no_es_tabla_se_rechaza_con_mensaje(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    r = cli.post("/api/automl/columnas",
                 files={"archivo": ("foto.png", b"\x89PNG\r\n\x1a\n rota",
                                    "image/png")})
    assert r.status_code == 400
    assert "CSV" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Permisos y rastro
# ---------------------------------------------------------------------------
def test_un_gestor_no_puede_entrenar(tmp_path, monkeypatch):
    """Entrenar un modelo con los datos de la empresa es una decisión de quien
    responde por esos datos."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api, rol="gestor")
    assert _subir(cli, "/api/automl/entrenar", _csv(),
                  objetivo="pago").status_code == 403


def test_el_entrenamiento_queda_en_el_linaje(tmp_path, monkeypatch):
    """Con gobernanza activa: qué modelo salió de qué archivo y con qué
    métrica. Es la pregunta de una auditoría sobre una decisión automatizada."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    _subir(cli, "/api/automl/entrenar", _csv(n=500, semilla=2), objetivo="pago")

    from kobra import gobernanza as kgob
    asientos = kgob.linaje("modelo_automl_pago")
    assert asientos, "el entrenamiento no dejó rastro"
    det = asientos[-1]["detalle"]
    assert det["modelo"] and det["auc_holdout"]


@pytest.mark.parametrize("ruta", ["/api/automl/columnas", "/api/automl/entrenar"])
def test_los_endpoints_piden_sesion(tmp_path, monkeypatch, ruta):
    from fastapi.testclient import TestClient
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = TestClient(api.app)
    r = cli.post(ruta, params={"objetivo": "pago"},
                 files={"archivo": ("x.csv", _csv(n=100), "text/csv")})
    assert r.status_code == 401
