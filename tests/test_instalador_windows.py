"""Tests del instalador de Windows (electron-builder + NSIS).

El pedido fue que el programa tenga un instalador que deje **elegir dónde
instalar, como un programa profesional**. Al mirarlo, la elección de carpeta ya
estaba configurada; lo que fallaba era otra cosa y peor: **el instalador no se
podía descargar**. La landing apuntaba a `MVKobraAI_Setup.exe` y el build
producía `MVKobraAI_Setup_v1.3.0.exe`, así que el enlace daba 404.

Y le faltaban las señales que distinguen a un instalador comercial de uno
casero: sin pantalla de licencia, sin marca en el asistente y sin editor
declarado (Windows mostraba "Editor desconocido").

Estos tests no pueden compilar un .exe de Windows desde Linux. Lo que sí hacen
es blindar la configuración y los archivos que consume: cada cosa que se
arregló acá tiene su verificación, para que no vuelva a degradarse en silencio.
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ELECTRON = os.path.join(ROOT, "electron")
BUILD = os.path.join(ELECTRON, "build")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build_windows.yml")


@pytest.fixture(scope="module")
def cfg():
    with open(os.path.join(ELECTRON, "package.json"), encoding="utf-8") as f:
        return json.load(f)


# --- lo que el usuario pidió ----------------------------------------------
def test_deja_elegir_la_carpeta_de_instalacion(cfg):
    """El asistente tiene que mostrar la página de carpeta destino. Con
    `oneClick` en true, NSIS instala sin preguntar nada y ni siquiera aparece
    esa pantalla."""
    nsis = cfg["build"]["nsis"]
    assert nsis["oneClick"] is False, "un instalador de un clic no pregunta nada"
    assert nsis["allowToChangeInstallationDirectory"] is True


def test_deja_elegir_para_quien_se_instala(cfg):
    """`perMachine: false` + `allowElevation` hace que NSIS muestre la página
    'para todos los usuarios / solo para mí'. Sin `allowElevation` el cliente
    no puede instalarlo en Archivos de programa aunque sea administrador."""
    nsis = cfg["build"]["nsis"]
    assert nsis["perMachine"] is False
    assert nsis["allowElevation"] is True


def test_muestra_la_licencia_antes_de_instalar(cfg):
    """Un programa que se cobra hace aceptar el EULA. Es de las cosas que más
    rápido delatan a un instalador que no es de un producto comercial."""
    assert "license" in cfg["build"]["nsis"], "el asistente no muestra licencia"


def test_windows_sabe_quien_publica_el_programa(cfg):
    """Sin `publisherName`, el aviso de UAC dice "Editor desconocido" y en
    "Aplicaciones instaladas" el programa figura sin responsable."""
    win = cfg["build"]["win"]
    assert win.get("publisherName"), "falta el editor: Windows dirá 'desconocido'"
    assert cfg["build"].get("copyright")


def test_queda_desinstalador_registrado(cfg):
    """Que aparezca en "Agregar o quitar programas" es parte de lo que se
    espera de un programa instalado, no un extra."""
    assert cfg["build"]["nsis"].get("uninstallDisplayName")


# --- el defecto que impedía siquiera bajarlo -------------------------------
def test_el_nombre_del_instalador_coincide_con_el_enlace_de_descarga(cfg):
    """Regresión del defecto que dejaba el producto sin instalador: la landing
    pide un nombre fijo a `/releases/latest/download/`, y el build generaba uno
    con la versión adentro. El enlace daba 404 en cada release."""
    artefacto = cfg["build"]["artifactName"]
    assert "${version}" not in artefacto, (
        "con la versión en el nombre, el enlace 'latest' se rompe en cada release")

    with open(os.path.join(ROOT, "landing", "descarga.html"), encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"INSTALADOR_URL\s*=\s*'([^']+)'", html)
    assert m, "no encontré el enlace de descarga en la landing"
    assert m.group(1).endswith("/" + artefacto), (
        f"la landing pide {m.group(1).rsplit('/', 1)[-1]!r} y el build "
        f"produce {artefacto!r}")


def test_el_workflow_busca_el_mismo_archivo_que_produce_el_build(cfg):
    """Si el workflow verifica un nombre y electron-builder escribe otro, el
    build falla en verde o publica un release vacío."""
    with open(WORKFLOW, encoding="utf-8") as f:
        yml = f.read()
    artefacto = cfg["build"]["artifactName"]
    assert artefacto in yml
    assert not re.search(r"MVKobraAI_Setup_v?\$\{|MVKobraAI_Setup_\*", yml), (
        "quedó una referencia al nombre viejo, con versión o comodín")


# --- archivos que consume el asistente ------------------------------------
@pytest.mark.parametrize("idioma", ["es", "pt", "en"])
def test_hay_licencia_en_cada_idioma_del_instalador(idioma, cfg):
    """electron-builder elige `license_<idioma>.txt` según el idioma que el
    cliente seleccione. Si falta uno, esa pantalla queda vacía."""
    assert idioma.upper() in " ".join(
        idm.upper() for idm in cfg["build"]["nsis"]["installerLanguages"]).replace("_", " ")
    ruta = os.path.join(BUILD, f"license_{idioma}.txt")
    assert os.path.exists(ruta), f"falta {os.path.basename(ruta)}"
    crudo = open(ruta, "rb").read()
    assert crudo.startswith(b"\xef\xbb\xbf"), "sin BOM el RichEdit come los acentos"
    assert b"\n" not in crudo.replace(b"\r\n", b""), (
        "saltos de línea de Unix: NSIS muestra el texto en un solo renglón")
    assert b"MV KOBRA AI" in crudo.upper()


def test_las_licencias_llevan_la_version_del_producto():
    """Regresión posible: se bumpea VERSION y el instalador sigue mostrando el
    EULA de una versión vieja."""
    # Se carga por ruta: el directorio `packaging/` del repo lo tapa la
    # librería `packaging` de PyPI, que está instalada y gana el import.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_lic_inst", os.path.join(ROOT, "packaging", "licencias_instalador.py"))
    li = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(li)

    version = li._version()
    for idioma, texto in li.textos().items():
        assert version in texto, f"la licencia {idioma} no dice v{version}"


@pytest.mark.parametrize("nombre,tamano", [
    ("installerSidebar.bmp", (164, 314)),
    ("installerHeader.bmp", (150, 57)),
])
def test_las_imagenes_del_asistente_son_bmp_del_tamano_exacto(nombre, tamano):
    """NSIS no escala estas imágenes: recorta. Y solo acepta BMP — un PNG
    renombrado hace fallar la compilación del instalador."""
    from PIL import Image
    ruta = os.path.join(BUILD, nombre)
    assert os.path.exists(ruta), f"falta {nombre}"
    with Image.open(ruta) as im:
        assert im.format == "BMP", f"{nombre} es {im.format}, no BMP"
        assert im.size == tamano, f"{nombre} mide {im.size}, NSIS espera {tamano}"


def test_el_texto_del_encabezado_no_toca_el_borde():
    """Regresión: con la tipografía real el texto quedaba a 3 px del borde y en
    pantallas con escalado se cortaba."""
    np = pytest.importorskip("numpy")
    from PIL import Image
    with Image.open(os.path.join(BUILD, "installerHeader.bmp")) as im:
        a = np.asarray(im.convert("RGB"))
    columnas = np.where((a.mean(axis=2) < 245).any(axis=0))[0]
    assert columnas.size, "el encabezado salió en blanco"
    assert a.shape[1] - 1 - columnas.max() >= 8, "el texto queda pegado al borde"


def test_el_config_apunta_a_archivos_que_existen(cfg):
    """Una ruta mal escrita en el config no se nota hasta que alguien intenta
    compilar el instalador en Windows."""
    nsis = cfg["build"]["nsis"]
    rutas = [nsis.get("include"), nsis.get("license"), nsis.get("installerSidebar"),
             nsis.get("uninstallerSidebar"), nsis.get("installerHeader"),
             cfg["build"]["win"].get("icon")]
    for rel in filter(None, rutas):
        assert os.path.exists(os.path.join(ELECTRON, rel)), f"no existe {rel}"
