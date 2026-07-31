"""La copia del dueño no puede tener ninguna puerta cerrada.

«Soy el dueño, no debería tener restricciones.» Al auditarlo, el modo owner ya
estaba limpio — pero eso no estaba verificado en ningún lado, así que nada
impedía que una restricción nueva se le colara encima sin que nadie lo notara:
alcanza con un `if MODO_STANDALONE:` puesto sin el `and not MODO_OWNER`.

Se levanta la MISMA app dos veces —owner y cliente standalone— y se compara a
qué llega cada una. La copia del cliente sirve de control: si un día el test
pasara porque *nadie* tiene restricciones, la comparación lo delata.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Todas las pantallas del producto, incluidas las descargas.
RUTAS = [
    "/api/kpis", "/api/graficos/resumen", "/api/cartera/filtros",
    "/api/cartera?pagina=1&tamano=5", "/api/agenda?pagina=1&tamano=5",
    "/api/gestores/resumen", "/api/calidad/comparativa", "/api/calidad/panel",
    "/api/calidad/fuentes", "/api/calidad/evaluaciones", "/api/paises",
    "/api/tenant/pais", "/api/cartera/origen", "/api/originacion/cola",
    "/api/originacion/metricas", "/api/config/estado",
    "/api/config/proveedor_ia", "/api/informe/programacion",
    "/api/cartera/export.csv", "/api/agenda/export.xlsx",
    "/api/calidad/export.xlsx", "/api/informe/ejecutivo.pdf",
]


def _levantar(owner: bool, datos: str):
    """Recarga la app con el modo pedido: MODO_OWNER se lee al importar."""
    for k in list(sys.modules):
        if k.startswith(("webapp", "kobra")):
            del sys.modules[k]
    os.environ["KOBRA_DATA_DIR"] = datos
    os.environ["KOBRA_MODO_STANDALONE"] = "1"
    if owner:
        os.environ["KOBRA_OWNER"] = "1"
    else:
        os.environ.pop("KOBRA_OWNER", None)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    return api, TestClient(api.app)


@pytest.fixture
def datos(tmp_path):
    """Copia mínima de la cartera scoreada: sin ella los endpoints responden
    vacío y el test no probaría nada."""
    import shutil
    for sub, arch in (("outputs", "kobra_scored.csv"),
                      ("data", "kobra_gestiones.csv")):
        origen = os.path.join(ROOT, sub, arch)
        if not os.path.exists(origen):
            pytest.skip(f"falta {sub}/{arch} (correr python -m kobra.pipeline)")
        (tmp_path / sub).mkdir(exist_ok=True)
        shutil.copy2(origen, tmp_path / sub / arch)
    return str(tmp_path)


@pytest.fixture(autouse=True)
def _restaurar_entorno():
    previo = {k: os.environ.get(k) for k in
              ("KOBRA_OWNER", "KOBRA_MODO_STANDALONE", "KOBRA_DATA_DIR")}
    yield
    for k, v in previo.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for k in list(sys.modules):
        if k.startswith(("webapp", "kobra")):
            del sys.modules[k]


def test_el_dueno_entra_sin_licencia_ni_password(datos):
    _, c = _levantar(True, datos)
    r = c.post("/api/licencia/owner-login")
    assert r.status_code == 200, "la entrada directa del dueño dejó de funcionar"
    assert r.json()["rol"] == "admin"


def test_la_licencia_del_dueno_no_vence(datos):
    _, c = _levantar(True, datos)
    lic = c.get("/api/licencia/estado").json()
    assert lic["activa"] is True and lic["owner"] is True
    assert lic["plan"] == "owner"
    assert lic["trial"] is False
    assert lic["dias_restantes"] is None, "al dueño le quedó un contador de días"


def test_el_dueno_llega_a_todas_las_pantallas(datos):
    _, c = _levantar(True, datos)
    token = c.post("/api/licencia/owner-login").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    cerradas = [(r, c.get(r, headers=h).status_code) for r in RUTAS]
    cerradas = [x for x in cerradas if x[1] != 200]
    assert not cerradas, f"al dueño le cerraron pantallas: {cerradas}"


def test_la_copia_de_un_cliente_sigue_pidiendo_licencia(datos):
    """El control. Sin esto, el test de arriba pasaría igual si un día se
    abrieran TODAS las copias — que es exactamente el bug opuesto y peor."""
    _, c = _levantar(False, datos)
    assert c.post("/api/licencia/owner-login").status_code == 404, \
        "la entrada del dueño quedó expuesta en la copia de un cliente"
    assert c.post("/api/auth/setup", json={"password": "Admin12345"}).status_code == 404, \
        "un cliente puede crear contraseña y saltear el vencimiento"
    abiertas = [r for r in RUTAS if c.get(r).status_code == 200]
    assert not abiertas, f"un cliente sin licencia llega a: {abiertas}"


def test_el_cumplimiento_sigue_activo_tambien_para_el_dueno():
    """No es una restricción comercial: es lo que hace legal usar el producto
    con deudores reales (Ley 18.331). Si algún día alguien lo saltea "porque es
    el dueño", el expuesto es el dueño. Queda fijado a propósito."""
    import inspect

    from kobra import cumplimiento
    fuente = inspect.getsource(cumplimiento)
    assert "KOBRA_OWNER" not in fuente and "MODO_OWNER" not in fuente, \
        "el motor de cumplimiento empezó a mirar si es el dueño"
