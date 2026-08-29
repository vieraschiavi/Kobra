# © 2026 Martín Viera. Todos los derechos reservados.

"""End-to-end por HTTP: cada escenario de demo contra la API real.

`test_demo_escenarios.py` prueba el dominio; esto prueba el PRODUCTO: el
mismo camino que recorre un cliente — login con licencia, activar un
escenario desde la pantalla de Configuración, y después abrir cada módulo
por su endpoint. Si un módulo exige un permiso de plan que la licencia no
trae, o un endpoint espera una columna que el escenario no genera, acá se
rompe — que es donde tiene que romperse, no en la demo con un prospecto.

La licencia del test es enterprise + módulos sueltos: el punto es verificar
que TODO funciona de punta a punta, y para eso hace falta la llave que abre
todas las puertas. Los tests de planes (test_plan_diferenciado.py) ya cubren
que cada puerta cierre para quien no pagó.
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-e2e-escenarios"

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


def _montar(tmp_path, monkeypatch):
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
    # Enterprise + los dos módulos sueltos: la llave que abre todas las
    # puertas, porque el objetivo es recorrerlas todas.
    features = [*klic.PLANES["enterprise"]["features"], "logistica", "proyectos"]
    kconfig.guardar_extra(
        "LICENCIA_TOKEN",
        klic.emitir_licencia("cliente-e2e", "enterprise", secreto=SECRETO,
                             cupo_mensual=None, features=features))

    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api, rol="admin"):
    from fastapi.testclient import TestClient
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token(rol, api.EMPRESA_DEFAULT)}"})
    return cli


@pytest.fixture(scope="module", params=["financiera", "distribuidora"])
def montado(request, tmp_path_factory):
    """Backend montado con el escenario YA activado vía el endpoint — una vez
    por escenario para todo el módulo (activar scorea con el modelo real).

    Fixture de módulo con monkeypatch propio: el de función no sirve para
    scope=module, y remontar el backend por test multiplicaría por diez el
    tiempo de la suite sin verificar nada nuevo.
    """
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    tmp = tmp_path_factory.mktemp(f"e2e_{request.param}")
    api = _montar(tmp, mp)
    cli = _cliente(api)
    r = cli.post(f"/api/demo/escenarios/{request.param}")
    assert r.status_code == 200, f"activar {request.param}: {r.text}"
    yield {"api": api, "cli": cli, "escenario": request.param,
           "activado": r.json()}
    mp.undo()
    _recargar_todo()


# ---------------------------------------------------------------------------
# Activación y catálogo
# ---------------------------------------------------------------------------
def test_el_catalogo_lista_los_dos_escenarios(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    cli = _cliente(api, rol="gestor")            # leer el catálogo no es de admin
    d = cli.get("/api/demo/escenarios").json()
    ids = {e["id"] for e in d["escenarios"]}
    assert {"financiera", "distribuidora"} <= ids


def test_activar_es_solo_de_admin(tmp_path, monkeypatch):
    """Cambia lo que ve todo el equipo: un gestor no puede pisarle la demo al
    resto en el medio de una presentación."""
    api = _montar(tmp_path, monkeypatch)
    cli = _cliente(api, rol="gestor")
    assert cli.post("/api/demo/escenarios/financiera").status_code == 403


def test_un_escenario_inventado_da_404(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    cli = _cliente(api)
    assert cli.post("/api/demo/escenarios/panaderia").status_code == 404


def test_verificar_sin_escenario_activo_explica(tmp_path, monkeypatch):
    api = _montar(tmp_path, monkeypatch)
    cli = _cliente(api)
    r = cli.post("/api/demo/verificacion")
    assert r.status_code == 409
    assert "escenario" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# El recorrido: cada módulo por su endpoint, con el escenario activo
# ---------------------------------------------------------------------------
def test_tablero(montado):
    d = montado["cli"].get("/api/tablero")
    assert d.status_code == 200, d.text
    hechos = d.json()["hechos"]
    assert hechos["deudores"] == montado["activado"]["deudores"]
    assert hechos["deuda_total"] == pytest.approx(
        montado["activado"]["deuda_total"])


def test_cartera_priorizada(montado):
    r = montado["cli"].get("/api/cartera")
    assert r.status_code == 200, r.text
    filas = r.json()
    filas = filas.get("filas", filas) if isinstance(filas, dict) else filas
    assert len(filas) > 0


def test_gobernanza(montado):
    cli = montado["cli"]
    for ruta in ("/api/gobernanza/resumen", "/api/gobernanza/catalogo",
                 "/api/gobernanza/calidad"):
        r = cli.get(ruta)
        assert r.status_code == 200, f"{ruta}: {r.text}"


def test_kpis_propios(montado):
    """Probar una fórmula contra la cartera del escenario — el botón 'Probar'
    de la pantalla de KPIs propios."""
    r = montado["cli"].post("/api/medidas/validar", json={
        "nombre": "Ticket promedio", "formula": "promedio(monto_deuda)",
        "formato": "moneda"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"], d
    assert d.get("vista_previa") is not None


def test_logistica(montado):
    r = montado["cli"].get("/api/logistica/resumen")
    assert r.status_code == 200, r.text
    assert r.json()["indicadores"]


def test_proyectos(montado):
    r = montado["cli"].get("/api/proyectos/resumen")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["salud"] and d["backlog"]


def test_agenda(montado):
    """La pantalla que devolvía 500 con el escenario activo: las gestiones
    del escenario no traían `fecha_gestion`. Acá se pide por HTTP, como la
    página, y tiene que venir con promesas vencidas — no vacía."""
    r = montado["cli"].get("/api/agenda?pagina=1&tamano=25")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] > 0, "la agenda del escenario quedó vacía"
    assert d["vencidas"][0]["id_deudor"]


def test_gestores(montado):
    """La otra pantalla en 500: faltaba `gestor_id`. El ranking tiene que
    salir con varios gestores y sus totales."""
    r = montado["cli"].get("/api/gestores/resumen")
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["ranking"]) >= 5, f"ranking corto: {len(d['ranking'])}"
    assert d["totales"]["gestiones"] > 0


def test_calidad_con_llamadas_evaluadas(montado):
    """El panel de calidad no puede abrir con "todavía no hay llamadas
    evaluadas" en una demo recién activada."""
    cli = montado["cli"]
    r = cli.get("/api/calidad/panel")
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 30, "el panel de calidad quedó vacío"
    r = cli.get("/api/calidad/comparativa")
    assert r.status_code == 200, r.text


def test_cuentas_por_cobrar(montado):
    r = montado["cli"].get("/api/cxc/antiguedad")
    assert r.status_code == 200, r.text
    d = r.json()["antiguedad"]
    assert d["tramos"] and d["deudores"] == montado["activado"]["deudores"]


def test_plan_de_contacto_por_contactabilidad(montado):
    """El canal del plan sale AUTOMÁTICO de la contactabilidad real del
    deudor cuando hay historial, y por regla cuando no — con `canal_origen`
    diciendo cuál de las dos decidió."""
    r = montado["cli"].get("/api/campana/plan?limite=20")
    assert r.status_code == 200, r.text
    d = r.json()
    if not d["total"]:
        # Fuera del horario legal de contacto el plan queda vacío A PROPÓSITO
        # —el cumplimiento manda—, pero entonces tiene que explicar por qué:
        # una tabla vacía sin motivo parece un programa roto. Este test corre
        # a cualquier hora, así que las dos ramas son legítimas.
        assert d["bloqueo"] and d["bloqueo"]["motivo"], \
            "el plan salió vacío y sin explicar el motivo"
        assert d["bloqueo"]["casos"] > 0
        return
    assert d["con_historial"] > 0, (
        "ningún canal elegido por contactabilidad: el automático no funciona")
    assert {p["canal_origen"] for p in d["contactos"]} <= {"historial", "regla"}
    # La clave NO puede llamarse `plan`: el interceptor del frontend toma
    # cualquier respuesta con esa clave como el estado del plan de licencia
    # y pisa el chip de consumo (se vio "undefined de undefined" en cámara).
    assert "plan" not in d


def test_chatbot_de_ayuda(montado):
    """Sin proveedor de IA configurado — el estado de una instalación nueva —
    el asistente contesta igual, con la búsqueda local en docs."""
    r = montado["cli"].post("/api/ayuda", json={
        "pregunta": "¿cómo activo las llamadas por teléfono?"})
    assert r.status_code == 200, r.text
    cuerpo = str(r.json())
    assert len(cuerpo) > 50


def test_verificacion_punta_a_punta_en_verde(montado):
    """El gate del pedido, por el mismo endpoint del botón de la pantalla:
    todos los módulos ejecutados con el escenario activo, todos en verde."""
    r = montado["cli"].post("/api/demo/verificacion")
    assert r.status_code == 200, r.text
    d = r.json()
    fallas = [p for p in d["pasos"] if not p["ok"]]
    assert d["ok"] and not fallas, "fallas: " + "; ".join(
        f"{p['modulo']} → {p['detalle']}" for p in fallas)
    assert len(d["pasos"]) >= 10


def test_ingenieria_de_datos_sobre_la_cartera_del_escenario(montado):
    """Subir la propia cartera del escenario como archivo y perfilarla — el
    circuito completo de la pestaña de ingeniería de datos."""
    api, cli = montado["api"], montado["cli"]
    ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    with open(ruta, "rb") as f:
        r = cli.post("/api/datos/analizar-archivo",
                     files={"archivo": ("cartera.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["perfiles"]
