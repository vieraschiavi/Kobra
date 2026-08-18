# © 2026 Martín Viera. Todos los derechos reservados.

r"""La edición Owner no se publica donde cualquiera la baje, y sabe explicarse.

Dos fallas encontradas persiguiendo un "no funciona ningún instalador".

1. **El instalador Owner estaba publicado en un repositorio público.** Todo
   `release_owner.yml` se escribió sobre la premisa de que `vieraschiavi/Kobra`
   era privado —está en su comentario de cabecera— y la premisa era falsa. Esa
   edición arranca sin licencia, sin trial y sin vencimiento: publicada en
   abierto es el producto completo regalado, con URL de descarga directa y sin
   necesidad de cuenta. Un comentario no protege nada; el workflow tiene que
   comprobarlo y cortar.

2. **`Owner.bat` decía "no encontre la instalacion" y nada más.** Sin listar
   dónde buscó y sin distinguir el caso peor: el programa instalado pero con el
   motor a medias. Ahí el mensaje mandaba a copiar el .bat "a la carpeta donde
   está el programa" — que era justo donde ya estaba. Callejón sin salida.

Estos tests no ejecutan batch ni corren el workflow: fijan las decisiones.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAT = os.path.join(ROOT, "packaging", "Owner.bat")
WF = os.path.join(ROOT, ".github", "workflows", "release_owner.yml")


def _leer(ruta):
    with open(ruta, encoding="utf-8", errors="replace") as f:
        return f.read()


def _sin_rem(texto):
    """El .bat sin sus líneas `rem`: los comentarios citan a propósito los
    mensajes viejos para explicar por qué cambiaron, y sin filtrarlos el
    comentario que documenta un arreglo hace fallar al test que lo verifica."""
    return "\n".join(ln for ln in texto.splitlines()
                     if not ln.strip().lower().startswith("rem"))


@pytest.fixture(scope="module")
def bat():
    return _leer(BAT)


# ---------------------------------------------------------------------------
# El workflow no publica la edición sin licencia en abierto
# ---------------------------------------------------------------------------
def test_el_workflow_owner_exige_repo_privado():
    """El gate que faltaba. Sin esto, subir la versión y mergear volvía a
    publicar el instalador sin licencia con URL pública."""
    wf = _leer(WF)
    assert "visibility" in wf, \
        "el workflow no consulta la visibilidad del repositorio"
    # Se busca la comparación contra "private" en cualquiera de sus dos
    # sentidos: la primera versión preguntaba `!= "private"` y la de ahora
    # pregunta `= "private"` para salir temprano. Lo que importa es que
    # compare, no cómo — atar el test a la sintaxis lo hace fallar en cada
    # reescritura sin que nada esté roto.
    assert re.search(r'(!=|=)\s*"private"', wf), \
        "no hay una comprobación de que el repo sea privado"
    # Y que efectivamente CORTE, no que solo avise: un warning en un log que
    # nadie lee no evita que el .exe se suba igual.
    bloque = wf[wf.index("El repo tiene que ser privado"):][:2600]
    assert "exit 1" in bloque, "detecta el repo público pero publica igual"


def test_el_gate_corre_antes_de_construir_nada():
    """Tiene que estar en el job del que dependen los otros dos: si estuviera
    al final, el instalador ya se habría construido y subido."""
    wf = _leer(WF)
    i_gate = wf.index("El repo tiene que ser privado")
    i_publicar = wf.index("\n  publicar:")
    i_instalador = wf.index("\n  instalador:")
    assert i_gate < i_publicar and i_gate < i_instalador, \
        "el chequeo de visibilidad corre después de los jobs que publican"


# ---------------------------------------------------------------------------
# Owner.bat sabe decir qué pasó
# ---------------------------------------------------------------------------
def test_cuando_no_encuentra_nada_dice_donde_busco(bat):
    """"No encontre la instalacion" a secas no le sirve a nadie: ni al usuario
    para corregirlo, ni a quien tenga que diagnosticarlo después."""
    codigo = _sin_rem(bat)
    assert "DIAG" in codigo, "no registra las carpetas que probó"
    assert 'type "!DIAG!"' in codigo, "las registra pero nunca las muestra"
    assert "Busque en estas carpetas" in codigo


def test_distingue_una_instalacion_a_medias(bat):
    """El caso peor: el .exe está pero falta `resources\\backend\\_internal`
    (el motor). Antes se reportaba como "no está instalado" y el mensaje
    mandaba a copiar el .bat a la carpeta donde ya estaba."""
    codigo = _sin_rem(bat)
    assert "PARCIAL" in codigo, "no detecta la instalación incompleta"
    assert 'if exist "%~1\\MV Kobra AI.exe"' in codigo, \
        "no busca el ejecutable para distinguir 'a medias' de 'no instalado'"
    assert "quedo a medias" in codigo, "no lo dice con todas las letras"
    # Y que proponga la salida correcta, que es reinstalar y no copiar el .bat.
    i = codigo.index("quedo a medias")
    assert "MVKobraAI_Setup.exe" in codigo[i:i + 700], \
        "detecta la instalación rota pero no dice cómo arreglarla"


def test_prueba_tambien_las_rutas_de_instalacion_para_todos_los_usuarios(bat):
    """Con `allowElevation: true` el asistente ofrece instalar para todos los
    usuarios, y ahí NSIS usa Archivos de programa. Las variantes Owner no
    estaban: quien instalaba el .exe del dueño así no aparecía por ninguna
    vía."""
    codigo = _sin_rem(bat)
    for ruta in (r"%ProgramFiles%\MV Kobra AI Owner",
                 r"%ProgramFiles(x86)%\MV Kobra AI Owner",
                 r"%LOCALAPPDATA%\Programs\MV Kobra AI Owner"):
        assert ruta in codigo, f"no busca en {ruta}"


def test_el_bat_sigue_siendo_ascii_y_crlf():
    """Dos cosas que ya rompieron .bat de este repo: un BOM y cmd.exe no abre
    el archivo; \\n suelto y el parser se confunde."""
    crudo = open(BAT, "rb").read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "el .bat quedó con BOM"
    crudo.decode("ascii")            # lanza si alguien metió una tilde
    assert b"\r\n" in crudo, "el .bat no tiene saltos CRLF"
    # Sacando los CRLF completos no puede quedar ningún \r ni \n suelto: eso
    # detecta tanto un \n huérfano como el \r\r\n que deja escribir "\r\n" a
    # mano sobre un archivo abierto con newline="" — los dos ya rompieron .bat
    # de este repo.
    sueltos = crudo.replace(b"\r\n", b"")
    assert b"\n" not in sueltos and b"\r" not in sueltos, \
        "hay saltos de línea que no son CRLF limpios"


def test_el_bat_del_repo_es_el_que_genera_el_script():
    """`Owner.bat` está versionado pero lo produce `generar_owner_bat.py`.
    Editarlo a mano y olvidarse del generador deja los dos divergiendo hasta
    que el próximo build pisa el arreglo."""
    import subprocess
    import sys
    antes = open(BAT, "rb").read()
    subprocess.run([sys.executable, os.path.join(ROOT, "packaging", "generar_owner_bat.py")],
                   check=True, capture_output=True)
    despues = open(BAT, "rb").read()
    assert antes == despues, (
        "packaging/Owner.bat no coincide con lo que genera "
        "packaging/generar_owner_bat.py — corré el generador y commiteá")


# ---------------------------------------------------------------------------
# Una sola versión
# ---------------------------------------------------------------------------
def test_la_version_es_la_misma_en_todos_lados():
    """`packaging/build_release.py` tenía su propio `VERSION = "1.4.0"` escrito
    a mano mientras el CI armaba el instalador con `kobra.__version__`. El
    número que anuncia un paquete no puede ser distinto del que reporta el
    programa: "tengo la 1.4.0" deja de decir qué código hay adentro.

    Además la versión es el disparador de las releases —un push a main que
    toca `kobra/__init__.py` publica—, así que un desfasaje también publica
    con la etiqueta equivocada.
    """
    import json
    import sys
    sys.path.insert(0, ROOT)
    import kobra
    sys.path.insert(0, os.path.join(ROOT, "packaging"))
    import build_release

    assert build_release.VERSION == kobra.__version__, (
        f"el empaquetador dice {build_release.VERSION} y el programa "
        f"{kobra.__version__}")

    with open(os.path.join(ROOT, "electron", "package.json"), encoding="utf-8") as f:
        electron = json.load(f)["version"]
    assert electron == kobra.__version__, (
        f"electron/package.json dice {electron} y el programa {kobra.__version__}")


def test_la_salida_de_emergencia_exige_escribir_la_palabra():
    """El dueño puede querer publicarla igual —para probar el instalador antes
    de cerrar el repo—, y esa es su decisión. Pero tiene que costar un acto
    deliberado: un checkbox se tilda sin leer, escribir PUBLICO no.
    """
    wf = _leer(WF)
    assert "publicar_aunque_el_repo_sea_publico" in wf, \
        "no hay forma de publicarla a conciencia con el repo abierto"
    assert '== "PUBLICO"' in wf or "= \"PUBLICO\"" in wf, \
        "la salida no exige una palabra escrita"
    # Y avisa en el resumen del run, no solo en un log que nadie abre.
    assert "GITHUB_STEP_SUMMARY" in wf, \
        "publica en abierto sin dejar constancia visible"


def test_la_salida_de_emergencia_no_alcanza_a_un_push():
    """Un push a main que toca la versión NO puede publicarla en abierto: en un
    push `inputs` viene vacío, así que la comparación falla y el gate corta.
    Si esto se rompiera, subir la versión regalaría el producto en silencio —
    que es exactamente el agujero que este gate vino a tapar."""
    wf = _leer(WF)
    bloque = wf[wf.index("El repo tiene que ser privado"):][:2200]
    assert "inputs.publicar_aunque_el_repo_sea_publico" in bloque, \
        "la salida no se lee de los inputs del disparo manual"
    # `github.event.inputs` también existe en push (vacío), pero usar `inputs`
    # deja explícito que es del workflow_dispatch.
    assert "exit 1" in bloque, "el gate dejó de cortar"
