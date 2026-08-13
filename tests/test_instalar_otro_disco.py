# © 2026 Martín Viera. Todos los derechos reservados.

"""No usar el disco C: si el usuario no lo pidió.

Reporte real: el instalador moría antes de abrir la primera pantalla, con

    Extrayendo: error escribiendo al archivo
    C:\\Users\\<usuario>\\AppData\\Local\\Temp\\nsXXXX.tmp\\LangDLL.dll

La pantalla que deja elegir carpeta de destino existe (`nsis.allowToChange
InstallationDirectory`), pero el error es ANTERIOR: todo instalador NSIS se
auto-descomprime en `%TEMP%` para sacar sus plugins. Si `%TEMP%` está en C: y
C: no tiene espacio —o el antivirus bloquea esa carpeta— la instalación no
arranca, elija el usuario la carpeta que elija.

No existe forma de compilar un .exe que no use `%TEMP%`. Lo que sí se puede es
apuntar `%TEMP%` a otro disco antes de lanzarlo, y eso hace
`Instalar_en_otro_disco.bat`.

Y hay un segundo uso de C: que dura para siempre y que nadie pidió: los datos
del programa (cartera, gestiones, configuración) van a %LOCALAPPDATA% aunque
la instalación esté en D:. `electron/main.js::dirDatosElegido` lo corrige.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BAT = os.path.join(ROOT, "packaging", "Instalar_en_otro_disco.bat")
MAIN_JS = os.path.join(ROOT, "electron", "main.js")


@pytest.fixture(scope="module")
def bat():
    if not os.path.exists(BAT):
        pytest.skip("falta packaging/Instalar_en_otro_disco.bat")
    with open(BAT, encoding="ascii") as f:
        return f.read()


@pytest.fixture(scope="module")
def main_js():
    with open(MAIN_JS, encoding="utf-8") as f:
        return f.read()


# --- El .bat manda los temporales a otro disco ------------------------------
def test_redirige_temp_y_tmp(bat):
    """Las dos variables: hay instaladores que leen una y no la otra."""
    assert 'set "TEMP=!TRABAJO!"' in bat
    assert 'set "TMP=!TRABAJO!"' in bat


def test_la_carpeta_de_trabajo_esta_junto_al_bat(bat):
    """`%~dp0` = la carpeta del propio .bat. Si el usuario lo copió a D:, los
    temporales quedan en D: — que es el punto del ejercicio. Una ruta fija
    como %TEMP% o C:\\ no serviría para nada acá."""
    m = re.search(r'set "TRABAJO=([^"]+)"', bat)
    assert m, "no define la carpeta de trabajo"
    assert m.group(1).startswith("%~dp0"), m.group(1)


def test_espera_a_que_termine_el_instalador(bat):
    """Sin `/wait`, el .bat borraría los temporales mientras el instalador
    todavía los está usando."""
    assert 'start "" /wait' in bat
    assert bat.index('start "" /wait') < bat.index("rd /s /q")


def test_limpia_lo_que_creo(bat):
    assert "rd /s /q" in bat


def test_encuentra_el_instalador_de_las_dos_ediciones(bat):
    for nombre in ("MVKobraAI_Setup_OWNER.exe", "MVKobraAI_Setup.exe"):
        assert nombre in bat, f"no busca {nombre}"
    assert '"%~1"' in bat, "no acepta el .exe arrastrado encima"


def test_avisa_si_no_puede_escribir_en_ese_disco(bat):
    """Si la carpeta de trabajo no se puede crear, hay que decirlo y parar —
    no seguir y morir después con el mismo error del principio."""
    assert "No pude crear la carpeta de trabajo" in bat
    assert "exit /b 1" in bat


def test_el_bat_lo_abre_cmd():
    with open(BAT, "rb") as f:
        crudo = f.read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "tiene BOM"
    assert b"\r\n" in crudo and b"\r\r\n" not in crudo


def test_no_toca_la_configuracion_de_windows(bat):
    """`set` dentro del proceso, no `setx`: cambiar TEMP a nivel del sistema
    afectaría a todos los programas del usuario para siempre."""
    assert "setx" not in bat.lower()


# --- Los datos siguen al programa, no se quedan en C: -----------------------
def test_los_datos_van_al_disco_de_la_instalacion(main_js):
    """Si el usuario instaló en D: porque su C: está justo, los datos no
    pueden seguir cayendo en %LOCALAPPDATA%."""
    assert "function dirDatosElegido" in main_js
    assert "KOBRA_DATA_DIR: datos" in main_js, \
        "no le pasa la carpeta elegida al backend"
    assert "process.resourcesPath" in main_js


def test_respeta_una_ruta_explicita(main_js):
    """`KOBRA_DATA_DIR` puesto a mano gana sobre cualquier heurística."""
    i = main_js.index("function dirDatosElegido")
    cuerpo = main_js[i:i + 1600]
    assert "if (process.env.KOBRA_DATA_DIR) return process.env.KOBRA_DATA_DIR;" in cuerpo


def test_no_le_mueve_los_datos_a_quien_ya_tenia_instalado(main_js):
    """La regla que evita el peor desenlace: que alguien actualice y crea que
    perdió su cartera porque el programa empezó a mirar otra carpeta."""
    i = main_js.index("function dirDatosElegido")
    cuerpo = main_js[i:i + 1600]
    assert "fs.existsSync(estandar)" in cuerpo and "return null" in cuerpo


def test_si_ya_esta_en_c_no_cambia_nada(main_js):
    """Instalación normal en C:: comportamiento idéntico al de siempre."""
    i = main_js.index("function dirDatosElegido")
    cuerpo = main_js[i:i + 1600]
    assert "discoInstalacion === discoEstandar" in cuerpo


def test_un_fallo_de_permisos_no_impide_abrir_el_programa(main_js):
    """Si no puede crear la carpeta, que decida rutas.py — nunca romper el
    arranque por dónde van los datos."""
    i = main_js.index("function dirDatosElegido")
    cuerpo = main_js[i:i + 1600]
    assert "catch" in cuerpo and cuerpo.count("return null") >= 3


# --- La pantalla de elegir carpeta sigue estando ----------------------------
def test_el_instalador_sigue_dejando_elegir_la_carpeta():
    """Nada de lo anterior puede haber sacado la opción de destino: es la
    forma normal de instalar fuera de C:."""
    import json
    with open(os.path.join(ROOT, "electron", "package.json"), encoding="utf-8") as f:
        nsis = json.load(f)["build"]["nsis"]
    assert nsis["allowToChangeInstallationDirectory"] is True
    assert nsis["oneClick"] is False, "con oneClick no hay pantalla de destino"
