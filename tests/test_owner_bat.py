"""El .bat de la versión OWNER: elegir carpeta y no mentir sobre el disco.

Dos fallas reportadas desde una instalación real en Windows:

1. **«No space left on device» con ~523 GB libres.** El chequeo medía el disco
   donde está el código y anunciaba los 523 GB de ese disco — pero pip
   descomprime cada wheel en `%TEMP%`, que vive en `C:`. Con `C:` lleno, el
   chequeo daba OK y la instalación moría igual, a mitad de bajar plotly. El
   número que mostraba no era el número que importaba.

2. **No dejaba elegir dónde instalar.** Metía el entorno (~2 GB) y los datos
   al lado del código, sin preguntar.

Estos tests no pueden ejecutar un `.bat` desde Linux. Lo que hacen es blindar
las decisiones del script: que pregunte, que mida el disco correcto y que
mande el temporal de pip al disco elegido — que es lo que convierte «elegí
otro disco» en una solución de verdad y no en un consejo.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAT = os.path.join(ROOT, "owner", "MVKobraAI_Owner_desde_codigo.bat")


@pytest.fixture(scope="module")
def bat():
    with open(BAT, encoding="utf-8", errors="replace") as f:
        return f.read()


# --- 1) Elegir la carpeta de instalación -----------------------------------
def test_pregunta_donde_instalar(bat):
    assert re.search(r"set\s*/p\s+\"?DESTINO=", bat), \
        "el .bat volvió a instalar sin preguntar la carpeta"


def test_enter_acepta_la_sugerida_sin_escribir_nada(bat):
    """Si dar Enter dejara DESTINO vacío, el script armaría rutas como
    `\\entorno` y se instalaría en la raíz del disco."""
    assert 'if "!DESTINO!"=="" set "DESTINO=!SUGERIDO!"' in bat


def test_la_eleccion_se_recuerda_para_la_proxima_vez(bat):
    assert "MEMORIA=" in bat and ">\"!MEMORIA!\" echo !DESTINO!" in bat


@pytest.mark.parametrize("caso,fragmento", [
    ("comillas de arrastrar la carpeta", 'set "DESTINO=!DESTINO:"=!"'),
    ("barra final", 'if "!DESTINO:~-1!"=="\\" set "DESTINO=!DESTINO:~0,-1!"'),
])
def test_limpia_lo_que_el_usuario_escribe(bat, caso, fragmento):
    """`"D:\\Kobra"` con comillas y `D:\\Kobra\\` con barra final son las dos
    formas en que una ruta pegada rompe todo lo que se le concatene."""
    assert fragmento in bat, f"no maneja: {caso}"


def test_verifica_que_puede_escribir_antes_de_seguir(bat):
    """Una carpeta puede existir y ser de solo lectura: crear el venv ahí falla
    veinte líneas después, con un error que no dice qué pasó."""
    assert ".kobra_prueba" in bat


# --- 2) El espacio en disco que se mide es el que se usa -------------------
def test_mide_el_disco_de_destino_y_no_el_del_codigo(bat):
    """El defecto exacto del reporte: medir un disco y llenar otro."""
    assert 'call :libres "!DESTINO!"' in bat
    assert 'dir /-c "%CD%"' not in bat, \
        "volvió a medir el disco donde está el código"


def test_no_mide_el_disco_parseando_la_salida_de_dir(bat):
    """`dir` cambia de formato según el idioma de Windows y el separador de
    miles. Se mide con la API de .NET, que devuelve bytes del volumen real."""
    assert "findstr" not in bat
    assert "DriveInfo" in bat and "AvailableFreeSpace" in bat


def test_no_se_planta_si_no_puede_medir(bat):
    """Un chequeo de disco que falla no puede impedir instalar: es un aviso,
    no un requisito."""
    assert 'if "!LIBRE_DESTINO!"=="?"' in bat


def test_avisa_antes_de_empezar_si_no_entran_las_dependencias(bat):
    assert re.search(r"if\s+!LIBRE_DESTINO!\s+LSS\s+3", bat)


# --- 3) Lo que hace que «elegí otro disco» funcione de verdad --------------
def test_python_se_instala_en_el_disco_elegido_y_no_en_localappdata(bat):
    """El defecto que sobrevivió a la primera ronda de arreglos: la descarga y
    el venv ya iban al disco elegido, pero el instalador oficial de Python
    (python-3.11.9-amd64.exe) por defecto SIEMPRE pone el intérprete en
    `%LocalAppData%\\Programs\\Python\\Python311` — que vive en C: — sin
    importar qué disco haya elegido el usuario para todo lo demás. Con C:
    justo de espacio (el motivo original de este .bat), instalar el
    intérprete ahí podía volver a fallar por lo mismo que se vino a arreglar."""
    assert 'set "PYDIR=!DESTINO!\\python311"' in bat
    assert 'TargetDir="!PYDIR!"' in bat
    codigo = "\n".join(ln for ln in bat.splitlines() if not ln.strip().lower().startswith("rem"))
    assert "%LocalAppData%\\Programs\\Python" not in codigo, \
        "sigue habiendo una linea de codigo (no comentario) que asume C:"
    assert 'if exist "!PYDIR!\\python.exe" set "PYEXE=!PYDIR!\\python.exe"' in bat


def test_no_pisa_el_path_del_usuario_con_una_ruta_borrable(bat):
    """PrependPath=1 agregaría al PATH una ruta dentro de la carpeta elegida:
    si el usuario la borra o la mueve, el PATH del usuario queda con una
    entrada rota. El .bat no lo necesita — ya guarda la ruta exacta a PYEXE."""
    assert "PrependPath=0" in bat
    assert "PrependPath=1" not in bat


def test_manda_el_temporal_de_pip_al_disco_elegido(bat):
    """La pieza central. pip descomprime en el temporal del sistema aunque se
    le pase --no-cache-dir: verificado observando la instalación, crea ahí
    `pip-unpack-*`, `pip-install-*`, `pip-metadata-*` y
    `pip-ephem-wheel-cache-*` (12 carpetas para pandas). Si ese temporal
    queda en C:, elegir D: no cambia nada y el ENOSPC vuelve igual.

    Se ponen las tres variables porque `tempfile` de Python las mira en orden
    TMPDIR → TEMP → TMP y basta con que una apunte al disco lleno."""
    for var in ("TEMP", "TMP", "TMPDIR"):
        assert f'set "{var}=!TRABAJO!"' in bat, f"falta redirigir {var}"


def test_el_temporal_se_redirige_antes_de_instalar(bat):
    """Ponerlo después del `pip install` sería no ponerlo."""
    assert bat.index('set "TMPDIR=!TRABAJO!"') < bat.index("-r \"!CODIGO!\\requirements.txt\"")


def test_el_entorno_y_los_datos_van_a_la_carpeta_elegida(bat):
    assert 'set "VENV=!DESTINO!\\entorno"' in bat
    assert 'set "DATOS=!DESTINO!\\datos"' in bat
    assert 'set "TRABAJO=!DESTINO!\\temp"' in bat
    assert 'set "KOBRA_DATA_DIR=!DATOS!"' in bat, \
        "el programa seguiría escribiendo al lado del código"


def test_el_codigo_se_referencia_por_ruta_absoluta(bat):
    """Con el entorno en otro disco, cualquier ruta relativa al código deja de
    resolver."""
    assert 'set "CODIGO=%CD%"' in bat
    for ruta in ("!CODIGO!\\requirements.txt",
                 "!CODIGO!\\packaging\\kobra_launcher.py",
                 "!CODIGO!\\owner\\ui_dist"):
        assert ruta in bat, f"quedó relativo: {ruta}"
    # Y nada quedó apuntando al venv viejo, que vivía junto al código.
    assert ".kobra_venv" not in bat


# --- 4) Que no se rompa la ventana ------------------------------------------
def test_los_pasos_estan_numerados_sin_saltos(bat):
    """La versión anterior imprimía 1, 3, 4, 5: el paso 2 existía en el código
    pero no se anunciaba, y parecía que algo había fallado."""
    pasos = re.findall(r"\[(\d)/(\d)\]", bat)
    assert pasos, "no quedó ningún paso numerado"
    total = {t for _, t in pasos}
    assert len(total) == 1, f"el total de pasos no es consistente: {total}"
    n = int(total.pop())
    assert sorted({int(p) for p, _ in pasos}) == list(range(1, n + 1)), \
        "hay saltos en la numeración de pasos"


def test_cada_salida_por_error_deja_leer_el_mensaje(bat):
    """Sin `pause`, la ventana se cierra sola y el usuario no ve el error."""
    for linea in bat.splitlines():
        if "exit /b 1" in linea:
            assert "pause" in linea, f"salida sin pause: {linea.strip()}"
