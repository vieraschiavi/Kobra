# © 2026 Martín Viera. Todos los derechos reservados.

"""El tablero conversacional contra la API.

Lo que importa verificar acá:

  * que el tablero **no esté detrás de un módulo pago** — es la pantalla de
    inicio, y cobrarle al cliente por ver sus propios indicadores sería
    sacarle producto que ya compró;
  * que **abra sin proveedor de IA configurado**, que es el estado en que llega
    toda instalación nueva;
  * que la pregunta libre respete el enmascarado de gobernanza: si no, sería
    la vía para sacar por texto lo que la tabla protege.
"""
import importlib
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-tablero-api"

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


def _montar(tmp_path, monkeypatch, plan="basico"):
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
                          klic.emitir_licencia("cliente-tab", plan, secreto=SECRETO))

    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api, rol="admin"):
    from fastapi.testclient import TestClient
    cartera = pd.DataFrame({
        "id_deudor": [f"KB-{i}" for i in range(20)],
        "monto_deuda": [100.0] * 10 + [200.0] * 10,
        "dias_mora": list(range(0, 200, 10)),
        "segmento": ["Pyme"] * 8 + ["Individuo"] * 7 + ["Corp"] * 5,
        "contactabilidad": [0.8] * 20,
        "prob_pago": [0.9] * 6 + [0.2] * 14,
    })
    ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    cartera.to_csv(ruta, index=False)

    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token(rol, api.EMPRESA_DEFAULT)}"})
    return cli, cartera


# ---------------------------------------------------------------------------
# El tablero es de todos
# ---------------------------------------------------------------------------
def test_el_tablero_no_esta_detras_de_un_modulo_pago(tmp_path, monkeypatch):
    """Básico no tiene ningún módulo de la suite y tiene que ver su tablero:
    son sus propios datos."""
    api = _montar(tmp_path, monkeypatch, "basico")
    cli, cartera = _cliente(api)
    r = cli.get("/api/tablero")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["hechos"]["deuda_total"] == float(cartera["monto_deuda"].sum())


def _sin_ia(monkeypatch):
    """Fuerza 'no hay proveedor configurado'.

    No alcanza con no configurar nada: `kllm.disponible()` también mira
    variables de entorno del sistema, y en una corrida completa de la suite
    otro test puede haber dejado una clave puesta. Un test que depende de eso
    pasa solo o falla junto a los demás, según el orden.
    """
    from kobra import llm as kllm
    monkeypatch.setattr(kllm, "disponible", lambda *a, **k: False)


def test_el_tablero_abre_sin_proveedor_de_ia(tmp_path, monkeypatch):
    """Es el estado en que llega toda instalación nueva. Si la pantalla de
    inicio dependiera de una API externa, el producto abriría vacío."""
    api = _montar(tmp_path, monkeypatch)
    cli, _ = _cliente(api)
    _sin_ia(monkeypatch)
    d = cli.get("/api/tablero").json()
    assert d["ia_disponible"] is False
    assert d["hechos"]["deudores"] == 20
    assert isinstance(d["advertencias"], list)
    assert isinstance(d["acciones"], list)


def test_preguntar_sin_ia_da_409_y_no_500(tmp_path, monkeypatch):
    """No está roto: falta configurarlo, y el mensaje dice dónde."""
    api = _montar(tmp_path, monkeypatch)
    cli, _ = _cliente(api)
    _sin_ia(monkeypatch)
    r = cli.post("/api/tablero/preguntar", json={"pregunta": "¿cómo viene?"})
    assert r.status_code == 409
    assert "Configuración" in r.json()["detail"]


def test_si_el_proveedor_falla_no_es_un_500(tmp_path, monkeypatch):
    """Clave vencida, cuota agotada o API caída son problemas del proveedor,
    no de Kobra. El usuario tiene que ver 'no se pudo consultar', no una
    pantalla rota."""
    api = _montar(tmp_path, monkeypatch)
    cli, _ = _cliente(api)
    from kobra import llm as kllm
    monkeypatch.setattr(kllm, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(kllm, "generar", lambda *a, **k: None)

    r = cli.post("/api/tablero/preguntar", json={"pregunta": "¿cómo viene?"})
    assert r.status_code == 409, r.text
    assert "funcionan igual" in r.json()["detail"]


def test_una_pregunta_vacia_da_400(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    cli, _ = _cliente(api)
    r = cli.post("/api/tablero/preguntar", json={"pregunta": "   "})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Con IA
# ---------------------------------------------------------------------------
def test_la_respuesta_trae_los_hechos_para_verificar(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    cli, cartera = _cliente(api)

    from kobra import llm as kllm
    monkeypatch.setattr(kllm, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(kllm, "generar",
                        lambda *a, **k: "La deuda total es de $3.000.")

    d = cli.post("/api/tablero/preguntar",
                 json={"pregunta": "¿cuánta deuda hay?"}).json()
    assert d["respuesta"]
    assert d["hechos_usados"]["deuda_total"] == float(cartera["monto_deuda"].sum())


def test_la_pregunta_respeta_el_enmascarado_de_gobernanza(tmp_path, monkeypatch):
    """Sin esto, la pregunta libre sería la puerta para sacar por texto lo que
    la tabla protege."""
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli, _ = _cliente(api, rol="gestor")

    capturado = {}
    from kobra import llm as kllm
    monkeypatch.setattr(kllm, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(kllm, "generar",
                        lambda p, **k: capturado.update(prompt=p) or "ok")

    cli.post("/api/tablero/preguntar", json={"pregunta": "¿quiénes son?"})
    assert "KB-" not in capturado["prompt"], \
        "los identificadores llegaron al modelo pese al enmascarado"


def test_el_tablero_pide_sesion(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    api = _montar(tmp_path, monkeypatch)
    _cliente(api)
    assert TestClient(api.app).get("/api/tablero").status_code == 401
