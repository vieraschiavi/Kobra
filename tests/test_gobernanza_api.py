# © 2026 Martín Viera. Todos los derechos reservados.

"""Gobernanza contra la API real: gateo por plan y protección efectiva.

`tests/test_gobernanza.py` prueba el motor. Acá se prueba lo que decide si el
módulo sirve o es decorativo:

  * que **sin el módulo nada cambie** — quien no lo compró tiene que seguir
    viendo su cartera igual que siempre. Un módulo que al no comprarse empeora
    el producto es un rehén, no un upsell.
  * que **con el módulo la protección alcance al export**. Es la parte que se
    olvida: si la pantalla enmascara y el CSV sale en claro, alcanza con
    apretar "Exportar" para llevarse la cartera nominal completa.
  * que quien no lo pagó reciba una **invitación a mejorar el plan**, no un
    error técnico.
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-gobernanza-api"

# Módulos que leen el entorno al importarse: recargarlos con el entorno del
# test los deja apuntando a la carpeta temporal. `monkeypatch` restaura las
# variables al terminar, pero NO deshace un `importlib.reload`, así que hay que
# volver a recargarlos a mano — si no, el test siguiente hereda esta licencia y
# esta carpeta de datos, y falla por algo que no tiene nada que ver con él.
_RECARGABLES = ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
                "webapp.backend.api")


def _recargar_todo():
    for nombre in _RECARGABLES:
        modulo = sys.modules.get(nombre)
        if modulo is not None:
            importlib.reload(modulo)


@pytest.fixture(autouse=True)
def _dejar_los_modulos_como_estaban(monkeypatch):
    """Devuelve los módulos al entorno real después de cada test."""
    yield
    monkeypatch.undo()
    _recargar_todo()


def _montar(tmp_path, monkeypatch, plan):
    """La API como la ve un cliente instalado con la licencia de `plan`."""
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
    token = klic.emitir_licencia("cliente-gob", plan, secreto=SECRETO)
    kconfig.guardar_extra("LICENCIA_TOKEN", token)

    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente_y_cartera(api, tmp_path, rol="gestor"):
    """Un TestClient autenticado con `rol` y una cartera sintética cargada."""
    import pandas as pd
    from fastapi.testclient import TestClient

    cartera = pd.DataFrame({
        "id_deudor": [f"KB-{100000 + i}" for i in range(5)],
        "segmento": ["Pyme", "Individuo", "Pyme", "Corp", "Individuo"],
        "departamento": ["Salto", "Montevideo", "Rivera", "Canelones", "Colonia"],
        "monto_deuda": [231530.0, 45000.0, 120000.0, 890000.0, 15000.0],
        "dias_mora": [13, 45, 3, 120, 7],
        "cuotas_atrasadas": [1, 2, 1, 4, 1],
        "score_buro": [576, 620, 780, 410, 690],
        "ingreso_estimado": [37300.0, 52000.0, 91000.0, 28000.0, 64000.0],
        "contactabilidad": [0.749, 0.5, 0.9, 0.2, 0.66],
        "canal_preferido": ["Llamada", "WhatsApp", "Llamada", "Email", "WhatsApp"],
        "prob_pago": [0.8, 0.4, 0.9, 0.1, 0.6],
    })
    ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    cartera.to_csv(ruta, index=False)

    token = api._emitir_token(rol, api.EMPRESA_DEFAULT)
    cli = TestClient(api.app)
    cli.headers.update({"Authorization": f"Bearer {token}"})
    return cli, cartera


# ---------------------------------------------------------------------------
# Sin el módulo: nada cambia
# ---------------------------------------------------------------------------
def test_sin_el_modulo_la_cartera_se_ve_como_siempre(tmp_path, monkeypatch):
    """Básico no incluye gobernanza. Ese cliente tiene que seguir viendo su
    cartera en claro: activarle el enmascarado por no haber comprado sería
    empeorarle el producto que sí pagó."""
    api = _montar(tmp_path, monkeypatch, "basico")
    cli, cartera = _cliente_y_cartera(api, tmp_path, rol="gestor")

    r = cli.get("/api/cartera")
    assert r.status_code == 200, r.text
    ids = {f["id_deudor"] for f in r.json()["filas"]}
    assert ids & set(cartera["id_deudor"]), \
        "sin el módulo se está enmascarando igual"
    assert r.json()["enmascarado"] is False


def test_sin_el_modulo_los_endpoints_invitan_a_mejorar_el_plan(tmp_path, monkeypatch):
    """No un 404: el cliente tiene que entender que existe y se compra."""
    api = _montar(tmp_path, monkeypatch, "basico")
    cli, _ = _cliente_y_cartera(api, tmp_path)

    r = cli.get("/api/gobernanza/resumen")
    assert r.status_code == 403
    cuerpo = r.json()
    assert cuerpo["motivo"] == "feature_no_incluida"
    assert "gobernanza de datos" in cuerpo["detail"]
    assert "mvkobranzaia.com" in cuerpo["detail"]


# ---------------------------------------------------------------------------
# Con el módulo: protege
# ---------------------------------------------------------------------------
def test_con_el_modulo_el_gestor_no_ve_identificadores(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente_y_cartera(api, tmp_path, rol="gestor")

    r = cli.get("/api/cartera")
    assert r.status_code == 200, r.text
    filas = r.json()["filas"]
    ids = {f["id_deudor"] for f in filas}
    assert not ids & set(cartera["id_deudor"]), \
        "el gestor ve identificadores en claro con gobernanza activa"
    assert r.json()["enmascarado"] is True


def test_con_el_modulo_el_gestor_igual_puede_gestionar(tmp_path, monkeypatch):
    """La otra mitad: proteger sin dejarlo sin trabajo."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente_y_cartera(api, tmp_path, rol="gestor")

    filas = cli.get("/api/cartera").json()["filas"]
    montos = {f["monto_deuda"] for f in filas}
    assert montos & set(cartera["monto_deuda"]), \
        "al gestor le enmascararon el monto: no puede cobrar"


def test_el_admin_sigue_viendo_todo(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente_y_cartera(api, tmp_path, rol="admin")

    r = cli.get("/api/cartera")
    ids = {f["id_deudor"] for f in r.json()["filas"]}
    assert ids & set(cartera["id_deudor"])
    assert r.json()["enmascarado"] is False


def test_el_export_tambien_esta_protegido(tmp_path, monkeypatch):
    """El agujero clásico: la pantalla enmascara y el CSV sale en claro. El
    export es justo por donde el dato se va y no vuelve."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente_y_cartera(api, tmp_path, rol="gestor")

    csv = cli.get("/api/cartera/export.csv").text
    for ident in cartera["id_deudor"]:
        assert ident not in csv, \
            f"el export se lleva {ident} en claro: la protección es decorativa"
    assert "anon:" in csv, "el export no quedó seudonimizado"


def test_el_export_del_admin_queda_asentado_en_el_linaje(tmp_path, monkeypatch):
    """Quién se llevó qué y cuándo. Es la pregunta de una auditoría."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="admin")

    cli.get("/api/cartera/export.csv")
    from kobra import gobernanza as kgob
    asientos = kgob.linaje("export_cartera_csv")
    assert asientos, "el export no dejó rastro en el linaje"
    assert (asientos[-1]["detalle"] or {}).get("rol") == "admin"


# ---------------------------------------------------------------------------
# Los endpoints del módulo
# ---------------------------------------------------------------------------
def test_el_resumen_trae_clasificacion_calidad_e_integridad(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, cartera = _cliente_y_cartera(api, tmp_path, rol="admin")

    d = cli.get("/api/gobernanza/resumen").json()
    assert d["filas"] == len(cartera)
    assert d["clasificacion"]["score_buro"] == "sensible"
    assert d["calidad"]["apto"] is True
    assert d["integridad_log"]["ok"] is True


def test_el_catalogo_dice_que_ve_cada_rol(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="gestor")

    d = cli.get("/api/gobernanza/catalogo").json()
    assert d["visibles"]["id_deudor"] is False
    assert d["visibles"]["monto_deuda"] is True


def test_la_calidad_reporta_las_dimensiones(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="admin")

    d = cli.get("/api/gobernanza/calidad").json()
    assert d["apto"] is True
    assert d["por_dimension"], "no se puntuó ninguna dimensión"


def test_el_linaje_se_consulta_por_destino(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="admin")

    from kobra import gobernanza as kgob
    kgob.registrar_linaje("kpis", ["cartera_scoreada"], "agregación")
    kgob.registrar_linaje("cartera_scoreada", ["cartera_cruda"], "ProbPago")

    d = cli.get("/api/gobernanza/linaje", params={"destino": "kpis"}).json()
    assert "cartera_cruda" in d["aguas_arriba"], \
        "el linaje no llega al origen a través de la API"


@pytest.mark.parametrize("ruta", [
    "/api/gobernanza/resumen", "/api/gobernanza/catalogo",
    "/api/gobernanza/calidad", "/api/gobernanza/linaje",
])
def test_los_endpoints_piden_sesion(tmp_path, monkeypatch, ruta):
    """Gobernanza expone el mapa de dónde está cada dato personal: es
    justamente lo que no puede quedar abierto sin autenticar."""
    from fastapi.testclient import TestClient
    api = _montar(tmp_path, monkeypatch, "enterprise")
    _cliente_y_cartera(api, tmp_path)
    assert TestClient(api.app).get(ruta).status_code == 401


# ---------------------------------------------------------------------------
# Enforcement y glosario (portados de MV Data Governance)
# ---------------------------------------------------------------------------
def test_el_enforcement_es_solo_para_admin(tmp_path, monkeypatch):
    """Devuelve el mapa de qué columna es sensible y qué rol debería verla —
    justo lo que le sirve a alguien para saber dónde apuntar."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="gestor")
    assert cli.get("/api/gobernanza/enforcement").status_code == 403


def test_el_admin_obtiene_el_ddl_listo_para_el_dba(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="admin")

    d = cli.get("/api/gobernanza/enforcement").json()
    assert "REVOKE ALL" in d["guion"]
    assert "no ejecutado" in d["guion"], \
        "el guion no aclara que Kobra no lo aplica: alguien puede creer que ya está hecho"
    assert d["sentencias_acceso"] > 0


def test_un_motor_no_soportado_da_400_y_no_500(tmp_path, monkeypatch):
    """Es un pedido inválido del cliente, no una falla del servidor."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="admin")

    r = cli.get("/api/gobernanza/enforcement", params={"motor": "oracle"})
    assert r.status_code == 400
    assert "postgresql" in r.json()["detail"]


def test_el_glosario_sale_en_los_dos_idiomas(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="gestor")

    es = cli.get("/api/gobernanza/glosario").json()["terminos"]
    pt = cli.get("/api/gobernanza/glosario", params={"idioma": "pt-BR"}).json()["terminos"]
    assert len(es) == len(pt) > 0
    assert {t["id"] for t in es} == {t["id"] for t in pt}


def test_sin_el_modulo_tampoco_hay_enforcement_ni_glosario(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch, "basico")
    cli, _ = _cliente_y_cartera(api, tmp_path, rol="admin")
    for ruta in ("/api/gobernanza/glosario", "/api/gobernanza/enforcement"):
        r = cli.get(ruta)
        assert r.status_code == 403
        assert r.json()["motivo"] == "feature_no_incluida", ruta
