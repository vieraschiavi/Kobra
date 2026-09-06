# © 2026 Martín Viera. Todos los derechos reservados.

"""Dos formas de instalar, el mismo programa.

Pedido: *"una opción sea instalación normal y otra VM del cliente por las
dudas (cliente Conaprole y laptop de mi empresa que me contrata Practia por
ejemplo)... bien discriminadas las formas de instalar y funcione igual"*.

El escenario es concreto: el consultor llega con su laptop —donde instala lo
que quiere— o le dan una VM del cliente, donde no es administrador, el
antivirus bloquea ejecutables sin firma y a veces no se puede ni escribir en
la carpeta que le asignaron.

Lo que se fija acá:

  * **Que sea el mismo programa.** Dos caminos de instalación que producen
    versiones distintas es peor que tener uno solo: el bug que el cliente
    reporta no se reproduce, porque no está usando lo mismo.
  * **Que el portable no deje rastro.** Es lo primero que pregunta el área de
    seguridad del cliente antes de autorizar cualquier cosa.
  * **Que el diagnóstico diga qué pedir.** Un diagnóstico que dice «falló» y
    no dice qué pedirle a IT deja al consultor donde estaba.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import entorno as kentorno  # noqa: E402

PORTABLE = os.path.join(ROOT, "packaging", "portable")
BAT_PORTABLE = os.path.join(PORTABLE, "MVKobraAI_Portable.bat")
BAT_DIAG = os.path.join(PORTABLE, "MVKobraAI_Diagnostico.bat")
LEEME = os.path.join(PORTABLE, "LEEME.txt")
BAT_BUILD = os.path.join(ROOT, "packaging", "construir_portable.bat")
BAT_INSTALADOR = os.path.join(ROOT, "packaging", "construir_instalador.bat")


def _texto(ruta):
    with open(ruta, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def _bat_efectivo(ruta):
    """El .bat sin comentarios ni `echo`.

    Los comentarios de estos scripts NOMBRAN a propósito lo que no hacen
    ("no arma su propio motor de PyInstaller"), así que buscar sobre el texto
    crudo da un test que falla por la explicación en vez de por el código —
    y el arreglo obvio sería borrar el comentario.
    """
    return "\n".join(
        linea for linea in _texto(ruta).splitlines()
        if not linea.strip().lower().startswith(("rem ", "::", "echo")))


def _cuerpo_sin_docstring(fn):
    """El código de una función, sin su docstring.

    Mismo motivo: el docstring de `puede_escribir` explica que NO se usa
    `os.access`, así que el test se encontraba a sí mismo en la explicación.
    """
    import ast
    import inspect
    import textwrap
    arbol = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    fn_def = arbol.body[0]
    if (fn_def.body and isinstance(fn_def.body[0], ast.Expr)
            and isinstance(fn_def.body[0].value, ast.Constant)):
        fn_def.body = fn_def.body[1:]
    return ast.unparse(arbol)


# --- El diagnóstico: la parte que se corre en la máquina ajena -------------
def test_el_diagnostico_corre_y_no_rompe_nada():
    """Tiene que poder correrse en una máquina desconocida sin efectos: es lo
    primero que se hace en la VM de un cliente."""
    r = kentorno.diagnosticar()
    assert set(r) == {"apto", "modo_sugerido", "chequeos", "bloqueos"}
    assert r["chequeos"], "no ejecutó ningún chequeo"
    assert r["modo_sugerido"] in ("instalador", "portable")


def test_cada_falla_dice_que_pedirle_a_IT():
    """El valor entero del diagnóstico. «No se puede escribir» no le sirve a
    nadie; «pedile a IT permiso de escritura en esa carpeta» sí."""
    sin_remedio = []
    for chequeo in (kentorno.puede_escribir("/proc/no-se-puede-escribir-aca"),
                    kentorno.espacio_disponible("/no-existe-esta-ruta")):
        assert not chequeo.ok, "el chequeo negativo pasó: no prueba nada"
        if not chequeo.remedio.strip():
            sin_remedio.append(chequeo.id)
    assert not sin_remedio, f"fallas sin remedio: {sin_remedio}"


def test_la_escritura_se_prueba_escribiendo_de_verdad(tmp_path):
    """`os.access` mira permisos POSIX y no la ACL de Windows, así que da
    verde en carpetas que después no dejan escribir. El chequeo crea un
    archivo real."""
    assert kentorno.puede_escribir(str(tmp_path)).ok
    fuente = _cuerpo_sin_docstring(kentorno.puede_escribir)
    assert "os.access" not in fuente, "volvió a confiar en os.access"
    assert "NamedTemporaryFile" in fuente


def test_no_ser_administrador_no_bloquea():
    """El programa NO necesita administrador. Marcarlo como falla haría que
    alguien abandone una instalación que iba a funcionar perfecto."""
    c = kentorno.admin()
    assert c.ok, "sin admin marcaría el diagnóstico en rojo"
    assert not c.bloqueante


def test_sin_admin_recomienda_portable(monkeypatch):
    """La recomendación es la salida útil del diagnóstico: sin permisos, el
    camino es la carpeta portable."""
    monkeypatch.setattr(kentorno, "_es_admin", lambda: False)
    assert kentorno.diagnosticar()["modo_sugerido"] == "portable"
    monkeypatch.setattr(kentorno, "_es_admin", lambda: True)
    assert kentorno.diagnosticar()["modo_sugerido"] == "instalador"


def test_declara_que_no_necesita_internet():
    """Es la pregunta que hace seguridad del cliente antes de autorizar.
    Tenerla contestada por escrito en el diagnóstico ahorra la reunión."""
    c = kentorno.sin_internet()
    assert c.ok and not c.bloqueante
    assert "no manda datos afuera" in c.detalle.lower()


def test_el_informe_se_puede_pegar_en_un_mail():
    """Así se usa de verdad: se corre en la VM y se manda el texto a IT."""
    texto = kentorno.informe_texto()
    assert "Diagnostico del entorno" in texto
    assert "RESULTADO:" in texto
    assert texto.isascii(), \
        "con acentos, la consola de Windows lo muestra roto y no se puede pegar"


def test_el_localhost_se_explica_como_no_es_internet(monkeypatch):
    """El malentendido que traba una autorización: IT lee «abre un puerto» y
    lo rechaza. El remedio tiene que aclarar que es tráfico interno."""
    def _falla(*_a, **_k):
        raise OSError("bloqueado por política")
    monkeypatch.setattr(kentorno.socket, "socket", _falla)
    c = kentorno.puerto_disponible()
    assert not c.ok
    assert "no es acceso a internet" in c.remedio.lower()
    assert "127.0.0.1" in c.remedio or "localhost" in c.remedio.lower()


# --- El modo portable ------------------------------------------------------
def test_el_portable_guarda_los_datos_en_su_propia_carpeta():
    """Lo que hace que se pueda borrar sin dejar rastro. Si guardara en el
    perfil del usuario, al borrar la carpeta quedarían datos del cliente
    dispersos en una máquina que no es nuestra."""
    bat = _texto(BAT_PORTABLE)
    assert 'KOBRA_DATA_DIR=%~dp0datos' in bat
    assert 'KOBRA_CONFIG_DIR=%~dp0datos' in bat


def test_el_portable_no_instala_nada():
    """Si tocara el registro o pidiera admin, dejaría de servir para el caso
    que existe para resolver."""
    bat = _bat_efectivo(BAT_PORTABLE).lower()
    for prohibido in ("reg add", "reg.exe", "schtasks", "sc create",
                      "msiexec", "runas"):
        assert prohibido not in bat, f"el portable ejecuta '{prohibido}'"


def test_el_portable_avisa_si_no_puede_escribir_donde_esta():
    """El caso real: se descomprime en una carpeta de solo lectura. Sin este
    aviso, el programa arranca y falla después con un error que no orienta."""
    bat = _texto(BAT_PORTABLE)
    assert "No puedo crear la carpeta de datos" in bat
    assert "donde puedas escribir" in bat


def test_hay_un_diagnostico_de_doble_clic():
    """El consultor en la VM del cliente no va a abrir una consola."""
    assert os.path.exists(BAT_DIAG)
    bat = _texto(BAT_DIAG)
    assert "--diagnostico" in bat
    assert "pause" in bat, "sin pause la ventana se cierra y no se lee nada"
    assert "IT" in bat, "no dice qué hacer cuando falla"


def test_el_launcher_entiende_el_flag_de_diagnostico():
    """Las dos mitades tienen que encajar: el .bat llama `--diagnostico` y el
    programa tiene que atenderlo."""
    codigo = _texto(os.path.join(ROOT, "packaging", "kobra_launcher.py"))
    assert '"--diagnostico" in sys.argv' in codigo
    # Y ANTES de levantar nada: si el entorno no da, arrancar el servidor
    # falla justo en lo que se está diagnosticando.
    assert codigo.index("--diagnostico") < codigo.index("KOBRA_MODO_STANDALONE")


# --- Que sea el MISMO programa --------------------------------------------
def test_el_portable_reusa_la_tuberia_del_instalador():
    """Dos tuberías de compilación producen, con el tiempo, dos programas
    distintos: el bug que el cliente reporta no se reproduce porque no está
    usando lo mismo."""
    bat = _texto(BAT_BUILD)
    assert "construir_instalador.bat" in bat, \
        "el portable armó su propia tubería de compilación"
    assert "solo-motor" in bat


def test_el_modo_solo_motor_existe_y_corta_antes_del_instalador():
    bat = _texto(BAT_INSTALADOR)
    assert 'if /i "%~1"=="solo-motor" set "SOLO_MOTOR=1"' in bat
    corte = bat.index("if defined SOLO_MOTOR")
    electron = bat.index("Construyendo el instalador")
    assert corte < electron, "solo-motor corta después de armar el instalador"


def test_el_portable_no_arma_su_propio_motor():
    """El control opuesto del anterior: que no llame a PyInstaller por su
    cuenta con otros parámetros."""
    bat = _bat_efectivo(BAT_BUILD)
    assert "PyInstaller" not in bat, "el portable compila el motor por su lado"


# --- Los dos modos, discriminados donde el usuario los lee -----------------
@pytest.mark.parametrize("archivo", [LEEME, BAT_BUILD])
def test_se_explica_cuando_usar_cada_modo(archivo):
    """«Bien discriminadas» era el pedido: quien lo lee tiene que saber cuál
    le toca sin preguntarle a nadie."""
    texto = _texto(archivo).lower()
    assert "portable" in texto and "instalador" in texto
    assert "administrador" in texto or "instalar" in texto


def test_el_leeme_dice_que_los_dos_modos_corren_lo_mismo():
    """Si el cliente sospecha que el portable es una versión recortada, no lo
    usa — y el modo existe justamente para el cliente que no puede instalar."""
    texto = _texto(LEEME).upper()
    assert "EL MISMO PROGRAMA" in texto


def test_el_leeme_contesta_lo_que_pregunta_seguridad():
    """Las cuatro preguntas que traban una autorización, contestadas antes de
    que las hagan."""
    texto = _texto(LEEME).lower()
    for tema in ("no manda datos a internet", "no abre puertos hacia afuera",
                 "no instala servicios", "no modifica el registro"):
        assert tema in texto, f"el LEEME no contesta: {tema}"


def test_el_leeme_es_legible_en_el_bloc_de_notas():
    """Se abre en la VM del cliente, con Notepad, en Windows. Sin CRLF queda
    todo en una línea; con acentos fuera de ASCII, con símbolos raros."""
    with open(LEEME, "rb") as f:
        crudo = f.read()
    assert b"\r\n" in crudo, "sin saltos de Windows"
    assert crudo.isascii(), "tiene caracteres que Notepad puede mostrar mal"


@pytest.mark.parametrize("ruta", [BAT_PORTABLE, BAT_DIAG, BAT_BUILD])
def test_los_bat_son_ejecutables_por_cmd(ruta):
    with open(ruta, "rb") as f:
        crudo = f.read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "tiene BOM"
    assert b"\r\n" in crudo, "no tiene saltos de Windows"
    assert b"\r\r\n" not in crudo, "tiene doble CR"
