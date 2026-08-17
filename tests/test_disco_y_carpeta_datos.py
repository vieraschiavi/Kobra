# © 2026 Martín Viera. Todos los derechos reservados.

r"""Que el programa no se rompa por el disco, y que se pueda elegir cuál.

El problema real: la carpeta de INSTALACIÓN era elegible desde el primer día
(el asistente tiene botón Examinar), pero los DATOS iban siempre a
`%LOCALAPPDATA%` — o sea al disco del perfil de Windows, o sea C: en la
práctica totalidad de las máquinas. El que instalaba en D: porque su C: estaba
lleno chocaba igual contra C: en el primer import de cartera, y el error salía
lejos de la causa: un `OSError: [Errno 28]` a mitad de un pipeline, no un
"elegiste un disco sin lugar".

Lo que se prueba acá:

  * que la elección se guarde y se lea (`carpeta_datos.txt`);
  * que una elección ROTA —disco desconectado, permisos, pendrive sacado— NO
    tumbe el arranque, sino que caiga al default dejando el motivo a la vista;
  * que mover los datos no los destruya si el destino falla a mitad;
  * y que el instalador de Windows y el código que lo lee usen el MISMO nombre
    de archivo. Ese último es el que evita el peor bug de esta familia: el
    instalador escribiendo una elección que el programa nunca mira, en silencio
    y sin error en ningún lado.
"""
import importlib
import os
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def rutas(tmp_path, monkeypatch):
    """`kobra.rutas` recargado en modo instalado, con el perfil de usuario en
    un tmp_path: el puntero de la elección vive ahí y no toca la máquina."""
    perfil = tmp_path / "perfil"
    perfil.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(perfil))
    monkeypatch.setenv("HOME", str(perfil))
    monkeypatch.delenv("KOBRA_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    from kobra import rutas as kr
    importlib.reload(kr)
    yield kr
    # Igual que en test_rutas_escribibles.py: kobra.rutas lo comparte todo el
    # proceso de tests, así que hay que devolverlo a modo dev o el resto de la
    # suite hereda un DIR_DATOS de este tmp_path ya descartado.
    monkeypatch.undo()
    importlib.reload(kr)


# ---------------------------------------------------------------------------
# Revisar una carpeta antes de usarla
# ---------------------------------------------------------------------------
def test_una_carpeta_normal_sirve_y_reporta_espacio(rutas, tmp_path):
    d = rutas.revisar(str(tmp_path / "datos"))
    assert d["ok"], d["motivo"]
    assert d["total_mb"] > 0, "no se pudo leer el tamaño del disco"
    assert os.path.isdir(tmp_path / "datos"), "revisar() debe crear la carpeta"


def test_una_carpeta_que_no_se_puede_crear_no_lanza(rutas):
    """La respuesta es el diagnóstico, no una excepción: quien pregunta es una
    pantalla que tiene que mostrar el motivo."""
    d = rutas.revisar("/proc/no/se/puede/crear/esto")
    assert not d["ok"]
    assert d["motivo"], "un rechazo sin motivo no le sirve a nadie"


@pytest.mark.skipif(os.geteuid() == 0, reason="root escribe igual en 0o500")
def test_una_carpeta_sin_permiso_de_escritura_se_rechaza(rutas, tmp_path):
    """`os.access` no alcanza: en Windows mira los permisos declarados y dice
    que sí sobre carpetas donde escribir falla igual. Por eso se prueba
    escribiendo de verdad."""
    solo_lectura = tmp_path / "solo_lectura"
    solo_lectura.mkdir()
    os.chmod(solo_lectura, stat.S_IRUSR | stat.S_IXUSR)
    try:
        d = rutas.revisar(str(solo_lectura))
        assert not d["ok"]
        assert "escribir" in d["motivo"].lower()
    finally:
        os.chmod(solo_lectura, stat.S_IRWXU)


def test_si_el_sistema_rechaza_la_escritura_se_reporta(rutas, tmp_path, monkeypatch):
    """La misma rama que el test de arriba, pero sin depender de los permisos
    del proceso: como root —CI, contenedores— un `chmod 0o500` no impide nada,
    y esa rama quedaría sin probar justo donde más corre la suite.

    Se simula lo que hace el sistema operativo cuando la carpeta existe pero
    escribir falla igual: antivirus, unidad de red caída, cuota agotada.
    """
    import builtins
    carpeta = tmp_path / "vigilada"
    real_open = builtins.open

    def open_que_falla(archivo, *a, **kw):
        if str(archivo).endswith(".kobra_prueba_escritura"):
            raise OSError(13, "Permission denied")
        return real_open(archivo, *a, **kw)

    monkeypatch.setattr(builtins, "open", open_que_falla)
    d = rutas.revisar(str(carpeta))
    assert not d["ok"]
    assert "escribir" in d["motivo"].lower()
    assert "Permission denied" in d["motivo"]


def test_la_carpeta_vacia_se_rechaza(rutas):
    assert not rutas.revisar("   ")["ok"]


def test_discos_lista_lo_que_necesita_la_pantalla(rutas):
    ds = rutas.discos()
    assert ds, "no se detectó ningún disco"
    for d in ds:
        assert set(d) == {"unidad", "libre_mb", "total_mb", "suficiente"}
        assert d["total_mb"] > 0
    unidades = [d["unidad"] for d in ds]
    assert len(unidades) == len(set(unidades)), "hay discos repetidos en la lista"


# ---------------------------------------------------------------------------
# El puntero: guardar y leer la elección
# ---------------------------------------------------------------------------
def test_guardar_y_leer_la_eleccion(rutas, tmp_path):
    elegida = tmp_path / "D_simulado" / "MVKobra"
    rutas.guardar_eleccion(str(elegida))
    assert rutas.carpeta_elegida() == str(elegida)
    rutas.guardar_eleccion("")                      # vaciar = volver al default
    assert rutas.carpeta_elegida() == ""


def test_el_puntero_vive_en_la_ubicacion_por_defecto(rutas, tmp_path):
    """Y no en la elegida: si viviera en el disco elegido y ese disco se
    desconecta, no habría forma de saber a dónde apuntaba."""
    elegida = tmp_path / "otro_disco"
    rutas.guardar_eleccion(str(elegida))
    puntero = os.path.join(rutas.dir_preferencias(), rutas.ARCHIVO_ELECCION)
    assert os.path.isfile(puntero)
    assert str(elegida) not in rutas.dir_preferencias()


def test_la_carpeta_elegida_se_usa_al_arrancar(rutas, tmp_path, monkeypatch):
    elegida = tmp_path / "datos_en_D"
    elegida.mkdir()
    rutas.guardar_eleccion(str(elegida))
    importlib.reload(rutas)
    assert rutas.DIR_DATOS == str(elegida)
    assert rutas.MOTIVO_FALLBACK == ""


def test_una_carpeta_elegida_rota_no_tumba_el_arranque(rutas, tmp_path):
    """El caso del pendrive sacado o el disco de red caído. Un programa de
    cobranzas que no abre es peor que uno que abre avisando dónde guarda."""
    rutas.guardar_eleccion("/proc/disco/que/ya/no/esta")
    importlib.reload(rutas)
    assert rutas.DIR_DATOS == rutas.dir_preferencias(), \
        "no cayó a la carpeta por defecto"
    assert rutas.MOTIVO_FALLBACK, "cayó al default sin decir por qué"
    assert "/proc/disco/que/ya/no/esta" in rutas.MOTIVO_FALLBACK


def test_la_variable_de_entorno_le_gana_al_puntero(rutas, tmp_path, monkeypatch):
    """KOBRA_DATA_DIR es el override explícito y por proceso: tiene que seguir
    ganando, o no habría forma de aislar un arranque de prueba."""
    rutas.guardar_eleccion(str(tmp_path / "elegida"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "forzada"))
    importlib.reload(rutas)
    assert rutas.DIR_DATOS == str(tmp_path / "forzada")


def test_en_el_repo_el_puntero_no_cambia_nada(tmp_path, monkeypatch):
    """Contrato de dev: corriendo desde el código, DIR_DATOS es la raíz del
    repo. Un puntero que quedó en la máquina de alguien no puede cambiar en
    silencio a dónde escribe la suite de tests."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "perfil"))
    monkeypatch.setenv("HOME", str(tmp_path / "perfil"))
    monkeypatch.delenv("KOBRA_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    from kobra import rutas as kr
    importlib.reload(kr)
    kr.guardar_eleccion(str(tmp_path / "otro_lado"))
    importlib.reload(kr)
    assert kr.DIR_DATOS == kr.ROOT_REPO
    monkeypatch.undo()
    importlib.reload(kr)


# ---------------------------------------------------------------------------
# Mover los datos
# ---------------------------------------------------------------------------
def test_mover_copia_todo_y_deja_el_original(rutas, tmp_path):
    """Copia y DESPUÉS anota, nunca `move`: si el destino se queda sin espacio
    a mitad —el escenario exacto que trae acá al usuario— un move interrumpido
    deja los datos partidos entre dos discos, sin original al que volver."""
    origen = tmp_path / "origen"
    (origen / "data").mkdir(parents=True)
    (origen / "outputs").mkdir()
    (origen / "data" / "kobra_cartera.csv").write_text("id_deudor\nKB-1\n")
    (origen / "outputs" / "kobra_scored.csv").write_text("id_deudor\nKB-1\n")
    destino = tmp_path / "destino"

    r = rutas.mover_datos(str(destino), origen=str(origen))
    assert r["ok"], r["motivo"]
    assert (destino / "data" / "kobra_cartera.csv").read_text().startswith("id_deudor")
    assert (destino / "outputs" / "kobra_scored.csv").exists()
    assert (origen / "data" / "kobra_cartera.csv").exists(), \
        "el original se borró: si la copia estuviera mal, no habría vuelta atrás"
    assert rutas.carpeta_elegida() == str(destino)


def test_mover_a_un_destino_invalido_no_toca_nada(rutas, tmp_path):
    origen = tmp_path / "origen"
    (origen / "data").mkdir(parents=True)
    (origen / "data" / "kobra_cartera.csv").write_text("id_deudor\nKB-1\n")

    r = rutas.mover_datos("/proc/imposible", origen=str(origen))
    assert not r["ok"]
    assert r["motivo"]
    assert (origen / "data" / "kobra_cartera.csv").exists()
    assert rutas.carpeta_elegida() == "", "se anotó una elección que falló"


def test_mover_a_la_misma_carpeta_es_inocuo(rutas, tmp_path):
    misma = tmp_path / "misma"
    misma.mkdir()
    r = rutas.mover_datos(str(misma), origen=str(misma))
    assert r["ok"]
    assert rutas.carpeta_elegida() == str(misma)


def test_estado_trae_todo_lo_que_muestra_la_pantalla(rutas):
    e = rutas.estado()
    for clave in ("dir_datos", "elegida", "default", "forzada_por_entorno",
                  "motivo_fallback", "libre_mb", "total_mb", "poco_espacio",
                  "minimo_mb", "discos"):
        assert clave in e, f"falta {clave} en estado()"


# ---------------------------------------------------------------------------
# Que el instalador y el programa hablen el mismo idioma
# ---------------------------------------------------------------------------
def _leer(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_el_instalador_escribe_el_puntero_que_el_programa_lee():
    """El peor bug de esta familia sería silencioso: el instalador anotando la
    elección en un archivo que el programa nunca mira. Sin error, sin log, y
    con los datos yendo igual al disco lleno."""
    from kobra import rutas as kr
    nsh = _leer("electron/build/installer.nsh")
    assert kr.ARCHIVO_ELECCION in nsh, \
        f"el instalador NSIS no escribe {kr.ARCHIVO_ELECCION}"
    # Y en la misma carpeta que `dir_preferencias()` en Windows.
    assert "$LOCALAPPDATA\\MV Kobra AI\\" + kr.ARCHIVO_ELECCION in nsh


def test_electron_no_pisa_la_eleccion_del_usuario():
    """`KOBRA_DATA_DIR` tiene la máxima prioridad en rutas.py, así que si
    Electron lo pasa siempre —como hacía— la carpeta que eligió el usuario en
    Configuración no se aplica nunca."""
    from kobra import rutas as kr
    main = _leer("electron/main.js")
    assert kr.ARCHIVO_ELECCION in main, \
        "main.js no mira el puntero: va a pisar la elección con su heurística"
    assert "hayEleccionGuardada()" in main


def test_el_instalador_avisa_del_espacio_antes_de_copiar():
    """Quedarse sin disco a mitad deja una instalación rota con un mensaje que
    habla de un archivo .tmp y no del disco: nadie lo sabe interpretar."""
    nsh = _leer("electron/build/installer.nsh")
    assert "DriveSpace" in nsh, "el instalador no mira el espacio libre"
    assert "MVK_MIN_DATOS_MB" in nsh and "MVK_MIN_INSTALL_MB" in nsh


def test_el_minimo_del_instalador_coincide_con_el_del_programa():
    """Dos números que quieren decir lo mismo en dos archivos distintos: si se
    separan, el instalador acepta un disco que el programa después rechaza."""
    import re

    from kobra import rutas as kr
    nsh = _leer("electron/build/installer.nsh")
    m = re.search(r"!define\s+MVK_MIN_DATOS_MB\s+(\d+)", nsh)
    assert m, "no se encontró MVK_MIN_DATOS_MB en el instalador"
    assert int(m.group(1)) == kr.MIN_LIBRE_MB

    ps1 = _leer("packaging/instalar_windows.ps1")
    m2 = re.search(r"\$MinLibreMb\s*=\s*(\d+)", ps1)
    assert m2, "no se encontró $MinLibreMb en instalar_windows.ps1"
    assert int(m2.group(1)) == kr.MIN_LIBRE_MB


def test_el_script_de_instalacion_prueba_escribir_de_verdad():
    """Bug real de esta familia: dar por buena una carpeta porque `Test-Path`
    dice que existe, y descubrir en la primera escritura que el antivirus o
    una unidad de red la bloquean."""
    ps1 = _leer("packaging/instalar_windows.ps1")
    assert "Test-Carpeta" in ps1
    assert "prueba_escritura" in ps1
    assert 'Test-Carpeta $Datos' in ps1, "no se valida la carpeta de datos"
    assert 'Test-Carpeta $Destino' in ps1, "no se valida la carpeta de instalación"


# ---------------------------------------------------------------------------
# Desde el programa, no desde una consola
# ---------------------------------------------------------------------------
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    # HOME y LOCALAPPDATA también: el endpoint ESCRIBE el puntero de la
    # carpeta elegida, que vive en el perfil del usuario. Sin aislarlos, estos
    # tests le dejan una elección real en la máquina de quien corra la suite —
    # y el programa arranca después mirando un tmp_path que ya no existe.
    perfil = tmp_path / "perfil"
    perfil.mkdir()
    monkeypatch.setenv("HOME", str(perfil))
    monkeypatch.setenv("LOCALAPPDATA", str(perfil))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    kauth.establecer_password("gestor", "GestorTest123!")
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    yield TestClient(api.app)
    monkeypatch.undo()
    importlib.reload(kconfig)


def _h(cliente, password="AdminTest123!"):
    r = cliente.post("/api/auth/login", json={"password": password, "empresa": "principal"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_la_pantalla_ve_donde_esta_guardando(cliente):
    r = cliente.get("/api/almacenamiento", headers=_h(cliente))
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["dir_datos"] and e["total_mb"] > 0
    assert isinstance(e["discos"], list)


def test_elegir_carpeta_desde_el_programa(cliente, tmp_path):
    nueva = tmp_path / "disco_D" / "MVKobra"
    r = cliente.post("/api/almacenamiento", headers=_h(cliente),
                     json={"carpeta": str(nueva), "copiar_datos": True})
    assert r.status_code == 200, r.text
    assert r.json()["elegida"] == str(nueva)
    # El aviso tiene que decir que recién aplica al reiniciar: DIR_DATOS se
    # resuelve una vez al importar, y prometer que ya está aplicado sería
    # mentirle al usuario sobre dónde se están guardando sus datos.
    assert "abrir" in r.json()["aviso"].lower()


def test_una_carpeta_imposible_se_rechaza_con_motivo(cliente):
    r = cliente.post("/api/almacenamiento", headers=_h(cliente),
                     json={"carpeta": "/proc/no/existe", "copiar_datos": False})
    assert r.status_code == 400
    assert r.json()["detail"], "un rechazo sin motivo no le sirve a nadie"


def test_un_gestor_no_puede_mover_los_datos_de_la_empresa(cliente, tmp_path):
    """Esto elige una carpeta arbitraria del disco y copia datos ahí. No es una
    preferencia de usuario: es administración de la instalación."""
    h = _h(cliente, "GestorTest123!")
    assert cliente.get("/api/almacenamiento", headers=h).status_code == 403
    assert cliente.post("/api/almacenamiento", headers=h,
                        json={"carpeta": str(tmp_path / "x")}).status_code == 403


def test_sin_token_no_se_ve_la_ruta_de_los_datos(cliente):
    """La ruta de instalación es información de reconocimiento: dice el nombre
    de usuario de Windows y la estructura de discos de la máquina."""
    assert cliente.get("/api/almacenamiento").status_code == 401


# ---------------------------------------------------------------------------
# Que el instalador compile de verdad, no solo que se lea bien
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("makensis") is None,
                    reason="makensis no está instalado (apt-get install nsis)")
def test_el_script_del_instalador_compila(tmp_path):
    """Los tests de arriba leen el `.nsh` como texto, y eso no ve un macro sin
    cerrar, una variable inexistente ni un `${if}` mal armado. Esos errores
    aparecían recién en el runner de Windows, con el build completo por delante.

    Acá se compila el fragmento con los símbolos que le pone electron-builder
    alrededor (`$newDesktopLink`, `${isUpdated}`, las páginas de MUI2). No sale
    un instalador usable —falta todo el payload—, pero un error de sintaxis sí
    sale.

    Y se mira el **warning 6000** aparte del código de salida, que es la trampa
    de NSIS: una variable inexistente no es un error, es un aviso, y makensis
    termina con éxito igual. Con `warningsAsErrors: false` en la config de
    electron-builder —que está así para tolerar los avisos de sus propias
    plantillas—, un `${NSD_GetText} $variableQueNoExiste` compilaría, publicaría
    y dejaría la página del asistente rota en silencio. El texto del aviso es
    literalmente "detected, ignoring".
    """
    banco = tmp_path / "banco.nsi"
    shutil.copy(os.path.join(ROOT, "electron", "build", "installer.nsh"),
                tmp_path / "installer.nsh")
    banco.write_text(
        'Name "banco"\n'
        'OutFile "banco.exe"\n'
        "RequestExecutionLevel user\n"
        '!include "MUI2.nsh"\n'
        '!include "LogicLib.nsh"\n'
        "; Lo que aporta electron-builder alrededor del include:\n"
        "Var newDesktopLink\n"
        "Var newStartMenuLink\n"
        "Var mvkFingeUpdate\n"
        "!define isUpdated `$mvkFingeUpdate == \"1\"`\n"
        '!include "installer.nsh"\n'
        "!insertmacro customPageAfterChangeDir\n"
        "!insertmacro MUI_PAGE_INSTFILES\n"
        '!insertmacro MUI_LANGUAGE "Spanish"\n'
        '!insertmacro MUI_LANGUAGE "PortugueseBR"\n'
        '!insertmacro MUI_LANGUAGE "English"\n'
        "Function .onInit\n"
        "  !insertmacro customInit\n"
        # Se les escribe algo a las variables prestadas: si solo se leen,
        # NSIS avisa 6001 ("never set") y ese ruido tapa lo que importa.
        '  StrCpy $newDesktopLink ""\n'
        '  StrCpy $newStartMenuLink ""\n'
        '  StrCpy $mvkFingeUpdate ""\n'
        "FunctionEnd\n"
        'Section "principal"\n'
        "  !insertmacro customInstall\n"
        "SectionEnd\n", encoding="utf-8")

    r = subprocess.run(["makensis", "banco.nsi"], cwd=tmp_path,
                       capture_output=True, text=True)
    salida = r.stdout + r.stderr
    assert r.returncode == 0, f"el instalador no compila:\n{salida}"
    assert "warning 6000" not in salida, (
        "hay una variable o constante que no existe — NSIS la ignora y sigue, "
        f"así que la página queda rota sin que falle nada:\n{salida}")
    # Las tres páginas propias: carpeta de datos, accesos directos e instfiles.
    assert "3 pages" in salida, \
        f"faltan páginas del asistente — ¿se salteó alguna?\n{salida}"
