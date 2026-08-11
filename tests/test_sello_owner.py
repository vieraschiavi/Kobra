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
