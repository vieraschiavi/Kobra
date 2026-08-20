# © 2026 Martín Viera. Todos los derechos reservados.

"""AutoML conectado a la base de datos del cliente.

La vía archivo ya estaba probada; esto cubre la otra fuente: servidor,
usuario y contraseña. Se prueba contra una base REAL (SQLite vía SQLAlchemy —
el mismo camino de código que recorre Postgres o SQL Server, cambiando solo
el dialecto), y lo que más importa acá es lo que rodea a la conexión:

  * que el nombre de tabla que llega por HTTP no pueda inyectar SQL con las
    credenciales que el propio cliente cargó;
  * que la contraseña no termine en el linaje ni en los mensajes de error;
  * que una contraseña con caracteres especiales no rompa la URL;
  * que el gateo por plan cubra también esta puerta.
"""
import importlib
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-prueba-automl-bd"

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


def _montar(tmp_path, monkeypatch, plan="enterprise"):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_AUDIT_LOG", str(tmp_path / "auditoria.log"))
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
    token = klic.emitir_licencia("cliente-bd", plan, secreto=SECRETO)
    kconfig.guardar_extra("LICENCIA_TOKEN", token)

    from webapp.backend import api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token('admin', api.EMPRESA_DEFAULT)}"})
    return api, cli


@pytest.fixture()
def base_cliente(tmp_path):
    """Una base real con una tabla entrenable (400 filas, señal de verdad)."""
    from sqlalchemy import create_engine
    ruta = str(tmp_path / "cliente.db")
    rng = np.random.default_rng(42)
    n = 400
    ingreso = rng.uniform(10000, 90000, n)
    mora = rng.integers(0, 200, n)
    # El objetivo depende de las variables: sin señal, el AUC del holdout
    # sería ruido y el test de entrenamiento no probaría nada.
    prob = 1 / (1 + np.exp(-(ingreso / 30000 - mora / 60)))
    df = pd.DataFrame({
        "ingreso": ingreso.round(0),
        "dias_mora": mora,
        "antiguedad": rng.integers(1, 120, n),
        "pago": (rng.uniform(0, 1, n) < prob).astype(int),
    })
    eng = create_engine(f"sqlite:///{ruta}")
    df.to_sql("deudores", eng, index=False)
    pd.DataFrame({"x": [1]}).to_sql("otra_tabla", eng, index=False)
    return ruta


def _conexion(ruta, **extra):
    return {"motor": "sqlite", "base": ruta, **extra}


# ---------------------------------------------------------------------------
# El flujo completo: conectar → listar → columnas → entrenar
# ---------------------------------------------------------------------------
def test_conecta_y_lista_las_tablas(tmp_path, monkeypatch, base_cliente):
    _, cli = _montar(tmp_path, monkeypatch)
    r = cli.post("/api/automl/bd/tablas", json=_conexion(base_cliente))
    assert r.status_code == 200, r.text
    assert "deudores" in r.json()["tablas"]


def test_lee_las_columnas_de_la_tabla_elegida(tmp_path, monkeypatch, base_cliente):
    _, cli = _montar(tmp_path, monkeypatch)
    r = cli.post("/api/automl/bd/columnas",
                 json=_conexion(base_cliente, tabla="deudores"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d["columnas"]) == {"ingreso", "dias_mora", "antiguedad", "pago"}
    assert len(d["vista"]) == 5


def test_entrena_directo_desde_la_base(tmp_path, monkeypatch, base_cliente):
    """El caso completo: las credenciales entran, el modelo sale."""
    _, cli = _montar(tmp_path, monkeypatch)
    r = cli.post("/api/automl/bd/entrenar",
                 json=_conexion(base_cliente, tabla="deudores", objetivo="pago"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["holdout"]["auc"] > 0.5, \
        "el modelo no encontró la señal que los datos tienen a propósito"
    assert "brecha_seleccion_holdout" in d, \
        "falta la brecha selección→holdout: es la honestidad del módulo"


# ---------------------------------------------------------------------------
# Seguridad alrededor de la conexión
# ---------------------------------------------------------------------------
def test_una_tabla_inventada_no_llega_al_sql(tmp_path, monkeypatch, base_cliente):
    """El nombre viene del pedido HTTP y termina dentro de una consulta: sin
    la lista blanca del inspector sería inyección con las credenciales del
    propio cliente."""
    _, cli = _montar(tmp_path, monkeypatch)
    r = cli.post("/api/automl/bd/columnas",
                 json=_conexion(base_cliente,
                                tabla='deudores"; DROP TABLE deudores; --'))
    assert r.status_code == 400
    assert "no existe" in r.json()["detail"]
    # y la tabla sigue viva
    r2 = cli.post("/api/automl/bd/tablas", json=_conexion(base_cliente))
    assert "deudores" in r2.json()["tablas"]


def test_credenciales_malas_dan_400_con_motivo_y_sin_url(tmp_path, monkeypatch):
    """El cliente necesita saber QUÉ corregir; el navegador no necesita ver la
    URL con la contraseña adentro."""
    _, cli = _montar(tmp_path, monkeypatch)
    r = cli.post("/api/automl/bd/tablas",
                 json={"motor": "postgresql", "servidor": "127.0.0.1",
                       "puerto": 1, "base": "x", "usuario": "u",
                       "contrasena": "secreta-123"})
    assert r.status_code == 400
    assert "secreta-123" not in r.text, "la contraseña volvió en el error"


def test_la_contrasena_no_queda_en_el_linaje(tmp_path, monkeypatch, base_cliente):
    """El log de auditoría se lee y se exporta: una credencial ahí es una
    filtración con firma de hash incluida."""
    _, cli = _montar(tmp_path, monkeypatch)
    cli.post("/api/automl/bd/entrenar",
             json=_conexion(base_cliente, tabla="deudores", objetivo="pago",
                            usuario="admin", contrasena="ClaveSecreta99"))
    from kobra import auditoria as kaud
    entradas = kaud.leer()
    volcado = str(entradas)
    assert "ClaveSecreta99" not in volcado, "la contraseña quedó en la auditoría"
    assert any(e.get("accion") == "linaje" for e in entradas), \
        "el entrenamiento no dejó rastro de linaje"


def test_una_contrasena_con_arroba_no_rompe_la_url(tmp_path, monkeypatch):
    """`p@ss:word` es una contraseña fuerte típica; sin escaparla, la URL se
    parte en el `@` y el error resultante no dice nada útil."""
    from webapp.backend import api
    datos = api.AutomlBdIn(motor="postgresql", servidor="host", base="b",
                           usuario="u", contrasena="p@ss:word/!")
    url = api._url_bd(datos)
    assert "p@ss" not in url, "la contraseña quedó sin escapar en la URL"
    assert url.count("@") == 1, "la URL tiene más de un @: se parte al parsear"


def test_un_motor_desconocido_dice_cuales_hay(tmp_path, monkeypatch):
    _, cli = _montar(tmp_path, monkeypatch)
    r = cli.post("/api/automl/bd/tablas", json={"motor": "oracle", "base": "x"})
    assert r.status_code == 400
    assert "postgresql" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Gateo
# ---------------------------------------------------------------------------
def test_sin_el_modulo_automl_la_bd_tambien_corta(tmp_path, monkeypatch, base_cliente):
    """La puerta nueva tiene que tener el mismo candado que la vieja."""
    _, cli = _montar(tmp_path, monkeypatch, plan="basico")
    for ruta in ("/api/automl/bd/tablas", "/api/automl/bd/columnas",
                 "/api/automl/bd/entrenar"):
        r = cli.post(ruta, json=_conexion(base_cliente, tabla="deudores",
                                          objetivo="pago"))
        assert r.status_code == 403, f"{ruta} no gatea"
        assert r.json()["motivo"] == "feature_no_incluida"


def test_conectarse_es_solo_para_admin(tmp_path, monkeypatch, base_cliente):
    """Cargar credenciales de la base de la empresa no es de cualquier sesión."""
    api, cli = _montar(tmp_path, monkeypatch)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token('gestor', api.EMPRESA_DEFAULT)}"})
    r = cli.post("/api/automl/bd/tablas", json=_conexion(base_cliente))
    assert r.status_code == 403
