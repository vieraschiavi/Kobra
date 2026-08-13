# © 2026 Martín Viera. Todos los derechos reservados.

"""El sello `edicion.json`: lo único que separa una copia cliente de la owner.

El instalador de clientes y el de owner salen del MISMO bundle de PyInstaller;
la diferencia la hace un archivo de 55 bytes que el workflow inyecta en
`_internal/` (o sea, en `sys._MEIPASS` cuando el .exe corre congelado):

    {"edition":"Owner","plan":null,"dias":null,"owner":true}

De ahí que `Owner.bat` pueda convertir una instalación ya hecha en la edición
del dueño sin recompilar nada. Estos tests fijan esa equivalencia — que es la
que hace que la herramienta sea correcta y no un truco frágil:

  * sin sello  → la app pide licencia (copia de cliente);
  * con sello  → entra directo, sin clave ni vencimiento;
  * y el sello que escribe `Owner.bat` es EXACTAMENTE el que produce el CI.
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import edicion as kedicion  # noqa: E402

SELLO_OWNER = {"edition": "Owner", "plan": None, "dias": None, "owner": True}


@pytest.fixture(autouse=True)
def _sin_owner_heredado(monkeypatch):
    """Cada caso arranca sin la variable puesta por otro test."""
    monkeypatch.delenv("KOBRA_OWNER", raising=False)


# --- La equivalencia que hace posible la conversión -------------------------
def test_sin_sello_la_copia_es_de_cliente(tmp_path):
    """Una instalación de cliente no trae `edicion.json`: no hay nada que
    activar y la app queda pidiendo licencia."""
    assert kedicion.activar(str(tmp_path)) is None
    assert os.environ.get("KOBRA_OWNER") is None


def test_con_el_sello_entra_como_owner(tmp_path):
    """Y con el archivo puesto —lo único que hace Owner.bat— la misma
    instalación pasa a ser la del dueño: sin clave y sin vencimiento."""
    (tmp_path / "edicion.json").write_text(json.dumps(SELLO_OWNER), encoding="utf-8")
    ed = kedicion.activar(str(tmp_path))
    assert ed["owner"] is True
    assert os.environ["KOBRA_OWNER"] == "1"
    v = kedicion.vigencia()
    assert v["ok"] and v["owner"] and v["dias_restantes"] is None


def test_un_sello_corrupto_no_rompe_el_arranque(tmp_path):
    """Si el archivo quedó a medio escribir, el programa tiene que abrir igual
    (como copia de cliente) y no morir con una excepción de JSON."""
    (tmp_path / "edicion.json").write_text('{"owner": tru', encoding="utf-8")
    assert kedicion.activar(str(tmp_path)) is None
    assert os.environ.get("KOBRA_OWNER") is None


# --- La herramienta escribe el mismo sello que el CI ------------------------
def _texto(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        return f.read()


@pytest.fixture(scope="module")
def owner_bat():
    ruta = os.path.join(ROOT, "packaging", "Owner.bat")
    if not os.path.exists(ruta):
        pytest.skip("falta packaging/Owner.bat")
    return _texto(ruta)


def test_el_sello_de_la_herramienta_es_el_del_ci(owner_bat):
    """Si el CI y la herramienta escribieran sellos distintos, la conversión
    andaría hoy y se rompería en la próxima release sin que nadie lo note."""
    ci = _texto(os.path.join(ROOT, ".github", "workflows", "release_owner.yml"))
    m = re.search(r"'(\{\"edition\":\"Owner\".*?\})'", ci)
    assert m, "no encontré el sello owner en el workflow"
    del_ci = json.loads(m.group(1))
    assert del_ci == SELLO_OWNER

    # Y el .bat escribe ese MISMO string, carácter por carácter.
    assert m.group(1) in owner_bat, (
        "el sello del .bat no es idéntico al del CI")


def test_la_herramienta_apunta_a_la_carpeta_correcta(owner_bat):
    """`_internal` es `sys._MEIPASS` del bundle congelado: si el sello va a
    otro lado, el programa no lo lee y la conversión no hace nada."""
    assert r"resources\backend\_internal" in owner_bat


def test_la_herramienta_verifica_lo_que_escribio(owner_bat):
    """Un permiso denegado o el programa abierto no pueden terminar en un
    «listo» que no es cierto."""
    assert "findstr" in owner_bat and "errorlevel 1" in owner_bat


def test_la_herramienta_es_auditable(owner_bat):
    """Batch puro y legible, sin PowerShell embebido en base64: ese patrón lo
    marcan los antivirus y deja un archivo que nadie puede revisar — mal
    negocio para algo que convierte una copia en la edición sin límites."""
    assert "EncodedCommand" not in owner_bat
    assert "FromBase64String" not in owner_bat


def test_el_sello_que_escribe_echo_lo_lee_el_programa(tmp_path, owner_bat):
    """La prueba de fondo: se reproduce EXACTAMENTE lo que `echo` de cmd.exe
    deja en disco (mismo texto, CRLF al final, sin BOM) y se comprueba con el
    código real que la copia queda en modo owner."""
    m = re.search(r'>"!INTERNO!\\edicion\.json" echo (.+)', owner_bat)
    assert m, "no encontré la línea que escribe el sello"
    (tmp_path / "edicion.json").write_bytes(
        (m.group(1) + "\r\n").encode("ascii"))

    ed = kedicion.activar(str(tmp_path))
    assert ed["owner"] is True
    assert os.environ["KOBRA_OWNER"] == "1"
    v = kedicion.vigencia()
    assert v["ok"] and v["owner"] and v["dias_restantes"] is None


def test_el_bat_es_ejecutable_por_cmd():
    """Sin CRLF y con BOM, `cmd.exe` directamente no lo abre."""
    ruta = os.path.join(ROOT, "packaging", "Owner.bat")
    if not os.path.exists(ruta):
        pytest.skip("falta packaging/Owner.bat")
    with open(ruta, "rb") as f:
        crudo = f.read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "el .bat tiene BOM"
    assert b"\r\n" in crudo, "el .bat no tiene saltos de Windows"
    assert b"\r\r\n" not in crudo, "el .bat tiene doble CR"


# --- La copia owner no pide clave por NINGUNA de las dos vías ---------------
def test_el_dashboard_no_pide_clave_en_la_edicion_owner(monkeypatch):
    """La app de escritorio ya entraba sola con el sello owner, pero el
    dashboard Streamlit seguía pidiendo crear una contraseña: la misma copia
    se comportaba distinto según por dónde se abriera. `render_gate` devuelve
    'admin' sin pedir nada cuando la edición es la del dueño."""
    pytest.importorskip("streamlit")
    from kobra import autenticacion as kauth

    monkeypatch.setenv("KOBRA_OWNER", "1")
    assert kauth.render_gate() == "admin"


def test_sin_sello_el_dashboard_sigue_pidiendo_acceso(monkeypatch, tmp_path):
    """Y el control negativo: una copia de CLIENTE no puede entrar sin clave
    por haber tocado esto."""
    st = pytest.importorskip("streamlit")
    import importlib

    from kobra import autenticacion as kauth
    from kobra import config as kconfig

    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    monkeypatch.delenv("KOBRA_DASHBOARD_SIN_LOGIN", raising=False)
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    importlib.reload(kconfig)
    # Se re-importa en vez de `reload`: otros tests de la suite borran
    # `kobra.*` de `sys.modules`, y recargar un módulo que ya no figura ahí
    # revienta con ImportError.
    from kobra import edicion as ked
    # `st.session_state` es un singleton del proceso: en la suite completa
    # otro test puede dejar una sesión abierta y el gate la respetaría (que es
    # lo correcto en producción, pero acá taparía lo que se quiere medir).
    st.session_state.pop(kauth._SESSION_KEY, None)

    # Lo que se verifica es que el atajo de owner NO se dispare sin sello.
    assert not ked.vigencia().get("owner")
    assert kauth.render_gate() is None


# --- Las tres ubicaciones desde donde se puede correr la herramienta --------
@pytest.mark.parametrize("subdirs,marcador", [
    ([os.path.join("resources", "backend", "_internal")], None),  # junto al .exe
    (["_internal"], None),                                        # en resources\backend
    ([], "base_library.zip"),                                     # dentro de _internal
])
def test_la_herramienta_funciona_copiada_al_lado_del_programa(tmp_path, owner_bat,
                                                              subdirs, marcador):
    """Lo más simple para el usuario es copiar el .bat a la carpeta del
    programa y hacer doble clic. Según a qué altura lo copie, `%~dp0` cae en
    un lugar distinto — las tres tienen que terminar en el mismo `_internal`.
    Se reproduce la resolución del .bat y se comprueba con el código real."""
    for d in subdirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    if marcador:
        (tmp_path / marcador).touch()

    # Mismo orden que el .bat: resources\backend\_internal, luego _internal,
    # luego la propia carpeta si tiene el marcador de PyInstaller.
    if (tmp_path / "resources" / "backend" / "_internal").is_dir():
        destino = tmp_path / "resources" / "backend" / "_internal"
    elif (tmp_path / "_internal").is_dir():
        destino = tmp_path / "_internal"
    elif (tmp_path / "base_library.zip").exists():
        destino = tmp_path
    else:
        pytest.fail("el .bat no resolvería esta ubicación")

    sello = re.search(r'>"!INTERNO!\\edicion\.json" echo (.+)', owner_bat).group(1)
    (destino / "edicion.json").write_bytes((sello + "\r\n").encode("ascii"))
    assert kedicion.activar(str(destino))["owner"] is True


def test_la_herramienta_busca_primero_su_propia_carpeta(owner_bat):
    """`%~dp0` antes que las rutas por defecto: si el usuario la copió al lado
    del programa, es ESA copia la que quiere convertir — no otra instalación
    que ande dando vueltas en la máquina."""
    pos_dp0 = owner_bat.index("%~dp0")
    pos_default = owner_bat.index("%LOCALAPPDATA%")
    assert pos_dp0 < pos_default
    assert "base_library.zip" in owner_bat, \
        "no reconoce el caso de estar copiada dentro de _internal"


# --- Después del sello, el programa entra sin ninguna traba ----------------
def test_despues_del_sello_la_app_entra_sin_clave_y_sin_cupo(tmp_path, monkeypatch,
                                                             owner_bat):
    """El recorrido completo del pedido: se instaló la versión CLIENTE, se
    ejecuta `Owner.bat` y a partir de ahí el programa tiene que entrar solo,
    sin licencia, sin vencimiento y sin tope de gestiones.

    Se reproduce el layout real de la instalación
    (`<install>\\resources\\backend\\_internal`), se escribe el sello con el
    MISMO texto que emite el .bat y se comprueba contra la API de verdad.
    """
    import importlib

    interno = tmp_path / "resources" / "backend" / "_internal"
    interno.mkdir(parents=True)
    sello = re.search(r'>"!INTERNO!\\edicion\.json" echo (.+)', owner_bat).group(1)
    (interno / "edicion.json").write_bytes((sello + "\r\n").encode("ascii"))

    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    from kobra import config as kconfig
    importlib.reload(kconfig)

    # Esto es lo que hace el launcher al arrancar la copia instalada.
    assert kedicion.activar(str(interno))["owner"] is True

    from kobra import plan as kplan
    importlib.reload(kplan)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    cliente = TestClient(api.app)

    # 1) Entra sin pedir nada.
    estado = cliente.get("/api/licencia/estado").json()
    assert estado["owner"] is True and estado["activa"] is True
    assert estado["dias_restantes"] is None, "una copia owner no puede vencer"

    r = cliente.post("/api/licencia/owner-login", json={})
    assert r.status_code == 200 and r.json()["rol"] == "admin"
    cab = {"Authorization": f"Bearer {r.json()['token']}"}

    # 2) Sin tope de gestiones — el cupo por plan no puede alcanzar al dueño.
    assert cliente.get("/api/plan", headers=cab).json()["ilimitado"] is True
    for _ in range(3):
        assert cliente.post("/api/gestor-ia/demo", json={"canal": "WhatsApp"},
                            headers=cab).status_code == 200

    # 3) Y las features que ningún plan pago trae, también.
    assert kplan.permite("white_label") and kplan.permite("sso")


# --- Que se pueda bajar de GitHub sin bajar el ZIP entero -------------------
def _workflow() -> str:
    return _texto(os.path.join(ROOT, ".github", "workflows", "release_owner.yml"))


def test_la_herramienta_se_publica_suelta_en_la_release():
    """El caso real de uso: el programa YA está instalado y solo hace falta
    sacarle las trabas. Bajar un ZIP de 270 MB para extraer un archivo de 2 KB
    no es una opción razonable, así que `Owner.bat` va suelto entre los
    assets."""
    ci = _workflow()
    assert "packaging/Owner.bat" in ci, (
        "Owner.bat no se publica suelto en la release")
    # Y regenerado en la corrida: si se publicara el archivo commiteado sin
    # regenerarlo, un cambio en el generador viajaría a medias.
    assert "python packaging/generar_owner_bat.py" in ci


def test_la_herramienta_tambien_viaja_dentro_del_zip():
    ci = _workflow()
    assert "Copy-Item packaging/Owner.bat stage/INSTALADOR/" in ci
    assert '"INSTALADOR/Owner.bat"' in ci, (
        "el ZIP no verifica que Owner.bat esté adentro antes de publicar")


def test_el_leeme_explica_que_va_despues_del_instalador():
    """El orden importa: primero se instala, después se convierte. Al revés no
    hay nada que sellar."""
    ci = _workflow()
    assert "Owner.bat  ->  PASAR UNA COPIA YA INSTALADA A OWNER" in ci
    assert "DESPUES del instalador" in ci
