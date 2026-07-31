"""Que el programa quede INSTALADO en Windows, no solo que corra.

El pedido fue: «que el programa aparezca instalado con icono, menú de programas
y desinstalador». Al mirarlo, el paquete descargable traía un `INICIAR_*.bat` y
nada más: el programa funcionaba, pero no aparecía instalado en ningún lado.
Para abrirlo había que acordarse de dónde se había descomprimido la carpeta, y
para «desinstalarlo» había que borrarla a mano.

Estos tests no pueden ejecutar PowerShell ni `cmd.exe` desde Linux. Lo que
hacen es armar el paquete de verdad y verificar que trae las piezas, que las
rutas internas resuelven, y que los scripts toman las decisiones correctas.
"""
import importlib.util
import os
import re
import sys
import tempfile
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PS_INSTALAR = os.path.join(ROOT, "packaging", "instalar_windows.ps1")
PS_DESINSTALAR = os.path.join(ROOT, "packaging", "desinstalar_windows.ps1")
BOM = b"\xef\xbb\xbf"


def _leer(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def instalar():
    return _leer(PS_INSTALAR)


@pytest.fixture(scope="module")
def desinstalar():
    return _leer(PS_DESINSTALAR)


@pytest.fixture(scope="module")
def paquete_owner():
    """Arma el ZIP de la edición Owner de verdad y devuelve (rutas, lector)."""
    spec = importlib.util.spec_from_file_location(
        "build_release", os.path.join(ROOT, "packaging", "build_release.py"))
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)
    with tempfile.TemporaryDirectory() as tmp:
        z = br.build_edicion(tmp, "Owner")
        with zipfile.ZipFile(z) as f:
            yield f.namelist(), {n: f.read(n) for n in f.namelist()
                                 if n.endswith((".bat", ".json", ".ps1", ".txt"))}


# --- Lo que el usuario pidió: icono, menú y desinstalador -------------------
def test_crea_icono_propio(instalar):
    """Un .lnk guarda la RUTA del icono, no el icono. Si apunta a la carpeta
    del código y esa carpeta se mueve, el acceso queda en blanco."""
    assert "MVKobraAI.ico" in instalar
    assert "icon.ico" in instalar
    assert 'IconLocation' in instalar


def test_crea_entrada_en_el_menu_inicio(instalar):
    assert "Start Menu\\Programs\\MV Kobra AI" in instalar


def test_crea_acceso_en_el_escritorio(instalar):
    assert 'GetFolderPath("Desktop")' in instalar


def test_aparece_en_agregar_o_quitar_programas(instalar):
    reg = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
    assert reg in instalar
    for prop in ("DisplayName", "DisplayVersion", "Publisher", "DisplayIcon",
                 "InstallLocation", "UninstallString"):
        assert prop in instalar, f"falta la propiedad {prop}"


def test_no_pide_permisos_de_administrador(instalar):
    """HKCU y el perfil del usuario, no HKLM ni Archivos de programa: pedir
    admin para instalar tu propia copia es fricción sin beneficio.

    Se miran solo las líneas de código: los comentarios nombran HKLM
    justamente para explicar por qué NO se usa — hay que sacar tanto los
    comentarios de línea (#) como el bloque de ayuda (<# … #>) del encabezado."""
    sin_bloque = re.sub(r"<#.*?#>", "", instalar, flags=re.S)
    codigo = [ln for ln in sin_bloque.splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
    for linea in codigo:
        assert "HKLM" not in linea, f"escribe en HKLM: {linea.strip()}"
        assert "ProgramFiles" not in linea, f"instala en Archivos de programa: {linea.strip()}"
    assert "HKCU:" in instalar


def test_el_acceso_directo_no_abre_una_ventana_de_consola(instalar):
    """Sin esto, cada arranque parpadea una consola negra — la señal más clara
    de «esto es un script» en vez de un programa."""
    assert "MVKobraAI.vbs" in instalar
    assert "wscript.exe" in instalar
    assert ", 0, False" in instalar, "el .vbs no está arrancando oculto"


def test_el_acceso_apunta_a_wscript_y_no_al_vbs_suelto(instalar):
    """Si el usuario tiene los .vbs asociados a otro programa o bloqueados por
    política, un acceso directo al .vbs no abriría nada."""
    assert "System32\\wscript.exe" in instalar


# --- Que el acceso directo realmente abra algo -----------------------------
def test_verifica_que_el_launcher_exista_antes_de_crear_el_acceso(instalar):
    """Un .lnk a un archivo inexistente se crea igual y falla en silencio: al
    hacer clic no pasa nada y no hay ningún error que leer."""
    assert "No encontre kobra_launcher.py" in instalar


def test_encuentra_el_launcher_en_los_dos_layouts(instalar):
    """El repo lo tiene en `packaging\\` y el ZIP lo copia a la raíz de
    `kobra_software\\`. Los dos son válidos."""
    assert '(Join-Path $Codigo "kobra_launcher.py")' in instalar
    assert '(Join-Path $Codigo "packaging\\kobra_launcher.py")' in instalar


def test_verifica_que_el_python_indicado_exista(instalar):
    assert "No existe el ejecutable de Python indicado" in instalar


def test_el_modo_owner_se_pasa_al_lanzador(instalar):
    assert "set KOBRA_OWNER=1" in instalar
    assert 'if ($Owner)' in instalar


# --- Desinstalar sin perder la cartera --------------------------------------
def test_al_desinstalar_los_datos_no_se_borran_por_defecto(desinstalar):
    """Mismo criterio que el instalador .exe: una desinstalación no puede ser
    la forma accidental de perder datos de cobranza."""
    assert "BorrarDatos" in desinstalar
    assert "datos CONSERVADOS" in desinstalar
    assert 'Escribi BORRAR' in desinstalar, "borra sin confirmación explícita"


def test_desinstalar_quita_accesos_y_registro(desinstalar):
    assert "Start Menu\\Programs\\MV Kobra AI" in desinstalar
    assert "CurrentVersion\\Uninstall" in desinstalar
    assert "Remove-Item" in desinstalar


def test_no_borra_la_carpeta_del_menu_si_quedo_otra_edicion(desinstalar):
    """Owner y cliente comparten la carpeta del Menú Inicio: desinstalar una no
    puede dejar a la otra sin su acceso."""
    assert "Get-ChildItem -LiteralPath $MenuDir" in desinstalar


def test_limpia_la_memoria_de_donde_instalar(desinstalar):
    """Si queda, la próxima instalación propone una carpeta que ya no existe."""
    assert "owner_destino.txt" in desinstalar


# --- El paquete descargable trae todo lo necesario --------------------------
def test_el_zip_owner_trae_el_instalador(paquete_owner):
    nombres, _ = paquete_owner
    for esperado in ("INSTALAR.bat",
                     "kobra_software/packaging/instalar_windows.ps1",
                     "kobra_software/packaging/desinstalar_windows.ps1",
                     "kobra_software/electron/build/icon.ico",
                     "kobra_software/kobra_launcher.py",
                     "kobra_software/edicion.json"):
        assert esperado in nombres, f"falta en el ZIP: {esperado}"


def test_las_rutas_del_instalador_resuelven_dentro_del_zip(paquete_owner):
    """El INSTALAR.bat arma rutas a mano; si el layout del paquete cambia, el
    .bat sigue existiendo y apunta a la nada."""
    nombres, cont = paquete_owner
    bat = cont["INSTALAR.bat"].decode("utf-8")
    for m in re.findall(r"%CODIGO%\\([^\"]+)", bat):
        ruta = "kobra_software/" + m.replace("\\", "/")
        assert ruta in nombres, f"el INSTALAR.bat apunta a algo que no está: {ruta}"


def test_el_paquete_owner_no_lleva_licencia_ni_vencimiento(paquete_owner):
    """Es la copia del dueño: sin licencia, sin trial, sin días."""
    import json
    _, cont = paquete_owner
    ed = json.loads(cont["kobra_software/edicion.json"])
    assert ed["owner"] is True
    assert ed["dias"] is None and ed["plan"] is None
    assert "token" not in ed and "secreto" not in ed


def test_el_zip_owner_explica_como_dejarlo_instalado(paquete_owner):
    _, cont = paquete_owner
    leeme = cont["LEEME.txt"].decode("utf-8-sig")
    assert "INSTALAR.bat" in leeme
    assert "Menú Inicio" in leeme
    assert "desinstalador" in leeme
    assert "tus datos NO se borran" in leeme


# --- El BOM que rompía todos los .bat del paquete --------------------------
def test_ningun_bat_del_paquete_arranca_con_BOM(paquete_owner):
    """cmd.exe no saltea el BOM: se lo come como parte del primer comando y la
    ventana arranca con «'∩╗┐@echo' no se reconoce...». No se había notado
    porque los .bat que se venían usando son los del repo, escritos a mano y
    sin BOM; los generados sí lo llevaban — y son los que abre quien descarga
    el ZIP."""
    _, cont = paquete_owner
    for nombre, datos in cont.items():
        if nombre.lower().endswith((".bat", ".cmd")):
            assert not datos.startswith(BOM), f"{nombre} arranca con BOM"


def test_los_txt_del_paquete_si_llevan_BOM(paquete_owner):
    """El BOM en un .txt no es un descuido: sin él, el Bloc de notas de Windows
    muestra los acentos rotos. La regla es por tipo de archivo, no global."""
    _, cont = paquete_owner
    # Solo los que GENERA el empaquetador: requirements.txt y demás archivos
    # copiados del repo se distribuyen tal cual, y ahí el BOM no aplica.
    generados = ["LEEME.txt", "VERSION.txt"]
    for nombre in generados:
        assert nombre in cont, f"el paquete quedó sin {nombre}"
        assert cont[nombre].startswith(BOM), f"{nombre} perdió el BOM"


def test_los_bat_del_paquete_usan_saltos_de_linea_de_windows(paquete_owner):
    _, cont = paquete_owner
    for nombre, datos in cont.items():
        if nombre.lower().endswith(".bat"):
            assert b"\r\n" in datos, f"{nombre} quedó con saltos de Unix"


def test_los_bat_del_repo_tampoco_llevan_BOM():
    """Los del repo ya estaban bien; se blindan para que no se degraden."""
    for rel in ("owner/MVKobraAI_Owner_desde_codigo.bat",
                "owner/MVKobraAI_Owner.bat",
                "packaging/construir_instalador.bat"):
        with open(os.path.join(ROOT, rel), "rb") as f:
            assert not f.read(3).startswith(BOM), f"{rel} ganó un BOM"
