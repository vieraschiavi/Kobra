# © 2026 Martín Viera. Todos los derechos reservados.

"""Logística y Proyectos contra la API: gateo, carga de datos y aislamiento.

Son los dos módulos que hacen de Kobra una plataforma en vez de un producto de
cobranzas. Lo que importa probar acá es lo que hace que esa decisión no
lastime lo que ya funcionaba:

  * que **se vendan sueltos de verdad** — una distribuidora compra logística
    sobre el plan más barato y la usa completa, sin pagar cobranzas;
  * que **no se filtren gratis** — ni Enterprise los trae por ser el plan caro;
  * que **no toquen la cartera** — un módulo de otro rubro que escriba sobre
    los datos de cobranzas sería un problema serio, no una molestia.
"""
import importlib
import io
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-modulos-otro-rubro"

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


def _montar(tmp_path, monkeypatch, plan="basico", extras=()):
    """La API con la licencia de `plan` más los módulos sueltos de `extras`."""
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
    feats = [*klic.PLANES[plan]["features"], *extras]
    token = klic.emitir_licencia("cliente-rubro", plan, features=feats,
                                 secreto=SECRETO)
    kconfig.guardar_extra("LICENCIA_TOKEN", token)

    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api, rol="admin"):
    from fastapi.testclient import TestClient
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token(rol, api.EMPRESA_DEFAULT)}"})
    return cli


def _csv(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


PRODUCTOS = pd.DataFrame({
    "sku": ["A-1", "A-2"], "nombre": ["Filtro", "Aceite"],
    "categoria": ["Filtros", "Lubricantes"], "precio": [100.0, 400.0],
    "costo": [70.0, 300.0], "stock": [900, 10], "stock_min": [50, 20],
    "lead_time_dias": [7, 12],
})
VENTAS = pd.DataFrame({
    "fecha": pd.date_range("2026-01-01", periods=120).astype(str).tolist() * 1,
    "sku": ["A-2"] * 120, "cantidad": [3] * 120,
    "cliente_id": ["C1"] * 120, "venta_id": [f"V{i}" for i in range(120)],
})
PROYECTOS = pd.DataFrame({
    "proyecto_id": ["P1"], "nombre": ["Migración"], "dueno": ["Ana"],
    "criticidad": ["Alta"], "presupuesto": [100000.0], "ejecutado": [60000.0],
})
TAREAS = pd.DataFrame({
    "tarea_id": ["T1", "T2"], "proyecto_id": ["P1", "P1"],
    "estado": ["todo", "blocked"], "responsable": ["Ana", None],
    "prioridad": ["Alta", "Media"],
    "vencimiento": ["2026-01-01", "2027-01-01"], "depende_de": [None, "T1"],
})


def _subir(cli, modulo, tabla, df):
    return cli.post(f"/api/modulo/{modulo}/cargar/{tabla}",
                    files={"archivo": (f"{tabla}.csv", _csv(df), "text/csv")})


# ---------------------------------------------------------------------------
# Se venden sueltos
# ---------------------------------------------------------------------------
def test_una_distribuidora_usa_logistica_con_el_plan_mas_barato(tmp_path, monkeypatch):
    """El caso comercial que justifica todo esto: compra logística sobre
    Básico y la usa completa, sin pagar el motor de cobranzas."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    cli = _cliente(api)

    assert _subir(cli, "logistica", "productos", PRODUCTOS).status_code == 200
    assert _subir(cli, "logistica", "ventas", VENTAS).status_code == 200

    d = cli.get("/api/logistica/resumen")
    assert d.status_code == 200, d.text
    cuerpo = d.json()
    assert cuerpo["indicadores"]["valor_stock"] > 0
    assert isinstance(cuerpo["ofertas"], list)
    assert isinstance(cuerpo["reposicion"], list)


def test_proyectos_tambien_va_suelto(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "basico", extras=("proyectos",))
    cli = _cliente(api)

    assert _subir(cli, "proyectos", "proyectos", PROYECTOS).status_code == 200
    assert _subir(cli, "proyectos", "tareas", TAREAS).status_code == 200

    d = cli.get("/api/proyectos/resumen")
    assert d.status_code == 200, d.text
    assert d.json()["proyectos"] == 1
    assert 0 <= d.json()["indice_general"] <= 100


def test_comprar_uno_no_regala_el_otro(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    cli = _cliente(api)
    r = cli.get("/api/proyectos/resumen")
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"


# ---------------------------------------------------------------------------
# No se filtran gratis
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ruta", ["/api/logistica/resumen", "/api/proyectos/resumen"])
def test_ni_enterprise_los_trae(tmp_path, monkeypatch, ruta):
    """Enterprise es el plan más completo *de cobranzas*, no un combo de todos
    los productos de la casa."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    r = _cliente(api).get(ruta)
    assert r.status_code == 403
    assert "mvkobranzaia.com" in r.json()["detail"]


@pytest.mark.parametrize("modulo,tabla", [("logistica", "productos"),
                                          ("proyectos", "tareas")])
def test_sin_el_modulo_tampoco_se_pueden_cargar_datos(tmp_path, monkeypatch,
                                                      modulo, tabla):
    """Si la carga no estuviera gateada, se podrían subir los datos y leerlos
    por otra vía."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    r = _subir(_cliente(api), modulo, tabla, PRODUCTOS)
    assert r.status_code == 403


@pytest.mark.parametrize("ruta", ["/api/logistica/resumen", "/api/proyectos/resumen"])
def test_los_endpoints_piden_sesion(tmp_path, monkeypatch, ruta):
    from fastapi.testclient import TestClient
    api = _montar(tmp_path, monkeypatch, "basico",
                  extras=("logistica", "proyectos"))
    assert TestClient(api.app).get(ruta).status_code == 401


def test_cargar_datos_es_solo_para_admin(tmp_path, monkeypatch):
    """Define los datos sobre los que después decide toda la empresa."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    r = _subir(_cliente(api, rol="gestor"), "logistica", "productos", PRODUCTOS)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# No tocan la cartera
# ---------------------------------------------------------------------------
def test_los_datos_del_modulo_no_pisan_la_cartera(tmp_path, monkeypatch):
    """Un módulo de otro rubro que escriba sobre los datos de cobranzas sería
    un problema serio, no una molestia."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    cli = _cliente(api)

    cartera = pd.DataFrame({"id_deudor": ["KB-1"], "monto_deuda": [1000.0],
                            "dias_mora": [10], "prob_pago": [0.5]})
    ruta_cartera = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    os.makedirs(os.path.dirname(ruta_cartera), exist_ok=True)
    cartera.to_csv(ruta_cartera, index=False)

    _subir(cli, "logistica", "productos", PRODUCTOS)
    _subir(cli, "logistica", "ventas", VENTAS)

    despues = pd.read_csv(ruta_cartera)
    pd.testing.assert_frame_equal(despues, cartera)


# ---------------------------------------------------------------------------
# Errores que el cliente puede arreglar
# ---------------------------------------------------------------------------
def test_sin_datos_cargados_avisa_que_hay_que_subirlos(tmp_path, monkeypatch):
    """Un 500 diría "el programa está roto"; un 404 con instrucción dice qué
    hacer para empezar a usarlo."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    r = _cliente(api).get("/api/logistica/resumen")
    assert r.status_code == 404
    assert "Subila" in r.json()["detail"] or "cargaste" in r.json()["detail"]


def test_un_archivo_al_que_le_falta_una_columna_lo_dice(tmp_path, monkeypatch):
    """Es lo único que el cliente puede arreglar, así que el mensaje tiene que
    nombrar la columna, no decir 'error al procesar'."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    cli = _cliente(api)
    _subir(cli, "logistica", "productos", PRODUCTOS)
    _subir(cli, "logistica", "ventas", VENTAS.drop(columns=["cantidad"]))

    r = cli.get("/api/logistica/resumen")
    assert r.status_code == 400
    assert "cantidad" in r.json()["detail"]


def test_una_tabla_desconocida_no_se_guarda(tmp_path, monkeypatch):
    """El nombre de la tabla llega desde el pedido y termina siendo parte de un
    nombre de archivo en disco, así que solo pueden pasar los declarados."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    r = _subir(_cliente(api), "logistica", "cualquier_cosa", PRODUCTOS)
    assert r.status_code == 400, r.text
    assert "productos" in r.json()["detail"], \
        "el mensaje no dice cuáles son las tablas válidas"


def test_no_se_puede_escribir_fuera_de_la_carpeta_de_la_empresa(tmp_path, monkeypatch):
    """El caso peligroso del punto anterior: un nombre con `../` que salga de
    la carpeta de datos. Lo corta el router al normalizar la URL, antes de
    llegar al código — pero se verifica igual, porque de eso depende que la
    lista blanca no sea la única barrera."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    r = _subir(_cliente(api), "logistica", "../../etc/passwd", PRODUCTOS)
    assert r.status_code in (400, 404, 405), r.text
    assert not os.path.exists("/etc/passwd.csv")


def test_un_modulo_desconocido_da_404(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    r = _subir(_cliente(api), "inventado", "productos", PRODUCTOS)
    assert r.status_code == 404


def test_la_carga_queda_asentada_en_el_linaje(tmp_path, monkeypatch):
    """De dónde salió cada tabla y quién la subió: la pregunta de auditoría."""
    api = _montar(tmp_path, monkeypatch, "basico", extras=("logistica",))
    _subir(_cliente(api), "logistica", "productos", PRODUCTOS)

    from kobra import gobernanza as kgob
    asientos = kgob.linaje("logistica_productos")
    assert asientos, "la carga no dejó rastro"
    assert (asientos[-1]["detalle"] or {}).get("filas") == len(PRODUCTOS)
