# © 2026 Martín Viera. Todos los derechos reservados.

"""Los instaladores .bat que genera packaging/build_release.py.

Reportado desde una instalación real en Windows, en este orden:

1. «Espacio en disco insuficiente» e inmediatamente después «No pude descargar
   Python (¿sin internet?)» — dos mensajes que se contradicen. La causa: el
   instalador bajaba Python a `%TEMP%` (que vive en C:) ANTES de preguntar la
   carpeta y de medir el disco. Con C: lleno, la descarga fallaba por espacio y
   el script culpaba a la red.
2. «Que permita elegir directorio y disco de instalación.» `INSTALAR.bat`
   preguntaba la carpeta pero no la validaba, e `INSTALAR_Y_EJECUTAR.bat` (la
   edición Producción) no preguntaba nada.
3. «Que tenga iconos en Escritorio y Programas.» Producción era la única
   edición que no dejaba el programa instalado en ningún lado.

Los .bat no se pueden ejecutar desde Linux. Lo que se blinda acá son las
decisiones del script y las propiedades del archivo generado — que es lo que
falla en la máquina del usuario y no se ve en ningún test que corra el pipeline.
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


def _codigo_bat(texto):
    """El .bat sin sus lineas `rem`.

    Varios gates son busquedas de texto, y los comentarios del generador citan
    a proposito los mensajes viejos para explicar por que se cambiaron. Sin
    descartarlos, el comentario que documenta un arreglo hace fallar el test
    que verifica ese mismo arreglo."""
    return "\n".join(ln for ln in texto.splitlines()
                     if not ln.strip().lower().startswith("rem"))


def _load(nombre, rel):
    """packaging/ choca con el paquete pip homónimo: se carga por ruta."""
    spec = importlib.util.spec_from_file_location(nombre, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


br = _load("br_instaladores", "packaging/build_release.py")


@pytest.fixture(scope="module")
def bats_owner():
    """Arma la edición Owner de verdad y devuelve {nombre: bytes} de sus .bat."""
    tmp = tempfile.mkdtemp()
    try:
        z = br.build_edicion(tmp, "Owner")
        with zipfile.ZipFile(z) as zf:
            return {n: zf.read(n) for n in zf.namelist() if n.lower().endswith(".bat")}
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def instalar(bats_owner):
    return bats_owner["INSTALAR.bat"].decode("utf-8").replace("\r\n", "\n")


# --- Propiedades del archivo (lo que rompe la ventana antes de leer nada) ---
def test_ningun_bat_lleva_bom(bats_owner):
    """cmd.exe no saltea el BOM: se lo come como parte del primer comando y la
    ventana arranca con «'∩╗┐@echo' no se reconoce como un comando»."""
    for nombre, b in bats_owner.items():
        assert not b.startswith(b"\xef\xbb\xbf"), nombre


def test_ningun_bat_tiene_doble_retorno_de_carro(bats_owner):
    """`_write(crlf=True)` ya convierte \\n -> \\r\\n. Escribir \\r\\n en el
    contenido dejaba \\r\\r\\n en el archivo."""
    for nombre, b in bats_owner.items():
        assert b.count(b"\r\r\n") == 0, f"{nombre}: doble CR"


def test_ningun_bat_tiene_caracteres_no_ascii(bats_owner):
    """Un .bat no se lee en UTF-8 sino en la code page de la consola (850/437).
    El título de la edición Owner («dueño del producto · sin límites») salía
    como «due├▒o ┬╖ sin l├¡mites» en la barra de la ventana."""
    for nombre, b in bats_owner.items():
        malos = [bytes([c]) for c in b if c > 127]
        assert not malos, f"{nombre}: {len(malos)} bytes no-ASCII -> mojibake"


def test_las_lineas_terminan_en_crlf(bats_owner):
    for nombre, b in bats_owner.items():
        assert b.count(b"\n") == b.count(b"\r\n"), f"{nombre}: hay LF sueltos"


def test_ascii_transliterado_conserva_el_sentido():
    assert br._ascii("Owner (dueño del producto · sin límites)") == \
        "Owner (dueno del producto - sin limites)"
    assert br._ascii("Pro · Todo incluido") == "Pro - Todo incluido"


# --- 1) El orden: elegir y medir ANTES de descargar -------------------------
def test_pregunta_la_carpeta_antes_de_descargar_python(instalar):
    """El bug del reporte. Con la descarga primero, un C: lleno hacía fallar el
    `Invoke-WebRequest` y el script lo reportaba como problema de red."""
    assert instalar.index('set /p "DESTINO=') < instalar.index("Invoke-WebRequest")


def test_mide_el_disco_antes_de_descargar_python(instalar):
    assert instalar.index("call :libres") < instalar.index("Invoke-WebRequest")


def test_python_se_descarga_al_disco_elegido_y_no_a_temp(instalar):
    """Si baja a %TEMP% (C:), elegir D: no cambia nada y el ENOSPC vuelve."""
    assert 'set "KOBRA_PY_DEST=!PYINST!"' in instalar
    assert 'set "PYINST=!TRABAJO!\\python311_kobra.exe"' in instalar
    assert "%TEMP%\\python" not in instalar


def test_python_se_instala_en_el_disco_elegido_y_no_en_localappdata(instalar):
    """La descarga y el venv ya iban al disco elegido, pero el instalador
    oficial de python.org por defecto SIEMPRE pone el intérprete en
    `%LocalAppData%\\Programs\\Python\\Python311` (C:), sin importar qué disco
    haya elegido el usuario para todo lo demás. TargetDir lo corrige."""
    assert 'set "PYDIR=!DESTINO!\\python311"' in instalar
    assert 'TargetDir="!PYDIR!"' in instalar
    codigo = _codigo_bat(instalar)
    # Lo que no puede pasar es que se INSTALE en C:. Buscarlo ahi despues, como
    # respaldo por si el instalador ignoro TargetDir, es correcto: no escribe
    # nada, solo mira. Por eso el gate va sobre la linea que lo invoca.
    invoca = [ln for ln in codigo.splitlines() if "/quiet" in ln]
    assert invoca, "no encontre la invocacion al instalador de Python"
    for ln in invoca:
        assert "%LocalAppData%" not in ln, f"instala en C: pese a TargetDir: {ln.strip()}"
    assert codigo.index('"!PYDIR!\\python.exe"') < \
        codigo.index('"%LocalAppData%\\Programs\\Python\\Python311\\python.exe"')
    assert "PrependPath=0" in instalar and "PrependPath=1" not in instalar


def test_si_falla_la_descarga_muestra_el_motivo_real(instalar):
    """«¿sin internet?» ante un disco lleno mandó al usuario a revisar la
    conexión durante toda una tarde. Ahora se imprime el error de PowerShell y
    se nombran las dos causas posibles."""
    assert "KOBRA_PY_ERR" in instalar
    assert re.search(r"type\s+\"!KOBRA_PY_ERR!\"", instalar)
    assert "Si habla de ESPACIO" in instalar and "Si habla de RED" in instalar


# --- 2) Elegir directorio y disco, sin romperse -----------------------------
def test_pregunta_donde_instalar(instalar):
    assert re.search(r"set\s*/p\s+\"?DESTINO=", instalar)


def test_enter_acepta_la_sugerida(instalar):
    assert 'if "!DESTINO!"=="" set "DESTINO=!SUGERIDO!"' in instalar


def test_la_eleccion_se_recuerda(instalar):
    assert 'set "MEMORIA=' in instalar and '>"!MEMORIA!" echo !DESTINO!' in instalar


@pytest.mark.parametrize("caso,fragmento", [
    ("comillas de arrastrar la carpeta", 'set "DESTINO=!DESTINO:"=!"'),
    ("barra final", 'if "!DESTINO:~-1!"=="\\" set "DESTINO=!DESTINO:~0,-1!"'),
])
def test_limpia_lo_que_el_usuario_escribe(instalar, caso, fragmento):
    """`"D:\\Kobra"` con comillas y `D:\\Kobra\\` con barra final son las dos
    formas en que una ruta pegada rompe todo lo que se le concatene."""
    assert fragmento in instalar, f"no maneja: {caso}"


def test_verifica_que_puede_escribir_antes_de_seguir(instalar):
    """Una carpeta puede existir y ser de solo lectura: crear el venv ahí falla
    veinte líneas después con un error que no dice qué pasó."""
    assert ".kobra_prueba" in instalar


def test_mide_el_disco_de_destino_con_la_api_de_dotnet(instalar):
    """`dir` cambia de formato según el idioma de Windows y el separador de
    miles; DriveInfo devuelve bytes del volumen real de la ruta."""
    assert 'call :libres "!DESTINO!"' in instalar
    assert "DriveInfo" in instalar and "AvailableFreeSpace" in instalar
    assert "findstr" not in instalar


def test_no_se_planta_si_no_puede_medir(instalar):
    """Un chequeo de disco que falla es un aviso, no un requisito."""
    assert 'if "!LIBRE_DESTINO!"=="?"' in instalar


def test_avisa_antes_de_empezar_si_no_entran_las_dependencias(instalar):
    assert re.search(r"if\s+!LIBRE_DESTINO!\s+LSS\s+3", instalar)


def test_lleva_la_subrutina_que_mide(instalar):
    """Sin `:libres` en el archivo, el `call` falla en silencio y el chequeo no
    se hace nunca."""
    assert re.search(r"^:libres$", instalar, re.M)


# --- 3) Que el entorno y las dependencias vayan al disco elegido ------------
def test_el_entorno_y_los_datos_van_a_la_carpeta_elegida(instalar):
    assert 'set "VENV=!DESTINO!\\entorno"' in instalar
    assert 'set "DATOS=!DESTINO!\\datos"' in instalar
    assert 'set "TRABAJO=!DESTINO!\\temp"' in instalar


@pytest.mark.parametrize("var", ["TEMP", "TMP", "TMPDIR"])
def test_manda_el_temporal_de_pip_al_disco_elegido(instalar, var):
    """pip descomprime en el temporal del sistema aunque se le pase
    --no-cache-dir. Si ese temporal queda en C:, elegir D: no cambia nada."""
    assert f'set "{var}=!TRABAJO!"' in instalar


def test_el_temporal_se_redirige_antes_de_instalar(instalar):
    assert instalar.index('set "TMPDIR=!TRABAJO!"') < instalar.index("requirements.txt")


def test_instala_las_dependencias_en_un_entorno_propio(instalar):
    """Antes creaba los accesos apuntando al pythonw del SISTEMA sin instalar
    nada: el icono quedaba pero al hacer clic el programa moría con ImportError
    si ese Python no tenía uvicorn/fastapi."""
    assert "-m venv" in instalar
    assert 'pip install --no-cache-dir -r "!CODIGO!\\requirements.txt"' in instalar


# --- 4) Iconos en Escritorio y Programas ------------------------------------
def test_deja_el_programa_instalado_con_accesos(instalar):
    assert "instalar_windows.ps1" in instalar
    assert "-Destino \"!DESTINO!\"" in instalar


def test_los_accesos_apuntan_al_python_del_entorno_y_no_al_del_sistema(instalar):
    """Es el que tiene las dependencias recién instaladas."""
    assert 'set "PYW=!VENV!\\Scripts\\pythonw.exe"' in instalar
    assert '-Python "!PYW!"' in instalar


def test_pasa_la_carpeta_de_datos_al_instalador(instalar):
    """Sin -Datos, el programa escribiría al lado del código en vez de en la
    carpeta que el usuario eligió."""
    assert '-Datos "!DATOS!"' in instalar


# --- 5) Que no se rompa la ventana ------------------------------------------
def test_los_pasos_estan_numerados_sin_saltos(instalar):
    pasos = re.findall(r"\[(\d)/(\d)\]", instalar)
    assert pasos
    total = {t for _, t in pasos}
    assert len(total) == 1, f"el total de pasos no es consistente: {total}"
    n = int(total.pop())
    assert sorted({int(p) for p, _ in pasos}) == list(range(1, n + 1))


def test_cada_salida_por_error_deja_leer_el_mensaje(instalar):
    """Sin `pause`, la ventana se cierra sola y el usuario no ve el error."""
    for linea in _codigo_bat(instalar).splitlines():
        if "exit /b 1" in linea:
            assert "pause" in linea, f"salida sin pause: {linea.strip()}"


def test_usa_expansion_retardada(instalar):
    """Todo el script lee variables que se asignan dentro de bloques `if (...)`.
    Sin enabledelayedexpansion, `!DESTINO!` queda literal y se instala en una
    carpeta llamada «!DESTINO!»."""
    assert "setlocal enabledelayedexpansion" in instalar


def test_el_iniciar_prefiere_el_entorno_instalado(bats_owner):
    """Si ya se instaló, el Python del sistema puede no tener las dependencias;
    arrancar con él daba ImportError pese a estar todo instalado."""
    iniciar = bats_owner["INICIAR_OWNER.bat"].decode("utf-8")
    assert "entorno\\Scripts\\python.exe" in iniciar
    assert iniciar.index("entorno\\Scripts\\python.exe") < iniciar.index("where python")


# --- 6) La edición Producción, que no tenía nada de esto --------------------
@pytest.fixture(scope="module")
def produccion():
    """Genera el .bat de Producción sin armar el ZIP entero (copia pesada)."""
    fuente = open(os.path.join(ROOT, "packaging", "build_release.py"),
                  encoding="utf-8").read()
    ini = fuente.index('_write(os.path.join(stage, "INSTALAR_Y_EJECUTAR.bat")')
    fin = fuente.index("_write(os.path.join(stage, \"instalar_y_ejecutar.sh\")")
    return fuente[ini:fin]


def test_produccion_pregunta_la_carpeta_y_mide_el_disco(produccion):
    """Era la única edición que instalaba sin preguntar nada."""
    assert "_bat_elegir_carpeta(1," in produccion
    assert "_bat_espacio(2," in produccion


def test_produccion_deja_iconos_en_escritorio_y_programas(produccion):
    assert "instalar_windows.ps1" in produccion
    assert "-Datos" in produccion


def test_produccion_arranca_con_un_puerto_libre(produccion):
    """`streamlit run` asume 8501 fijo: si otra app lo tiene, o falla o se corre
    de puerto sin avisar. kobra_streamlit.py elige uno libre antes."""
    assert "kobra_streamlit.py" in produccion
    assert "-Lanzador" in produccion


def test_produccion_conserva_la_opcion_docker(produccion):
    """Es una función documentada de la edición: no se puede perder al agregar
    la instalación normal."""
    assert "docker compose up" in produccion
    assert ":docker" in produccion


def test_produccion_avisa_si_docker_choca_de_puerto(produccion):
    """docker-compose.yml publica 8501 y 8000 fijos."""
    assert "puerto ocupado" in produccion


def test_el_zip_de_produccion_lleva_lo_necesario_para_instalar():
    """Sin el .ps1 y el icono en PROD_ITEMS, el paso de accesos falla y la
    edición vuelve a quedar sin iconos."""
    for req in ("packaging/instalar_windows.ps1",
                "packaging/desinstalar_windows.ps1",
                "electron/build/icon.ico"):
        assert req in br.PROD_ITEMS, f"falta {req} en PROD_ITEMS"


# --- 7) El bootstrap de Python no puede reportar exito cuando fallo ---------
# Reportado como «instala todo vacío D:\MVKobraAI», con la carpeta conteniendo
# solo `datos\` y `temp\`. Al pasar a PrependPath=0 quedó sin actualizar el
# camino de fallo: si tras instalar no encontraba python.exe donde lo pidió,
# imprimía «volvé a ejecutar para que Windows lo tome» y salía con exit /b 0
# (ÉXITO). Con PrependPath=0 Windows nunca lo iba a tomar, así que reabrir
# repetía el ciclo: descargar, instalar, salir. Nunca se llegaba a crear el
# entorno ni a instalar la app.
def test_el_fallo_de_python_no_sale_como_exito(instalar):
    assert "pause & exit /b 0" not in _codigo_bat(instalar), \
        "hay una salida de ERROR marcada como exito (exit /b 0)"


def test_no_promete_que_windows_va_a_tomar_python_solo(instalar):
    codigo = _codigo_bat(instalar)
    for frase in ("para que Windows lo tome", "una vez mas para que Windows"):
        assert frase not in codigo, f"sigue prometiendo lo imposible: {frase!r}"


def test_comprueba_que_el_interprete_realmente_arranca(instalar):
    """Una instalación a medias deja el .exe pero el intérprete no corre."""
    assert '"!PYEXE!" --version' in instalar


def test_muestra_el_codigo_de_salida_del_instalador(instalar):
    """Sin el exit code no hay forma de distinguir permisos, espacio o una
    cancelación del usuario."""
    assert 'set "PYRC=!errorlevel!"' in instalar
    assert "1603" in instalar
