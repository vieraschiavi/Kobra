# © 2026 Martín Viera. Todos los derechos reservados.

"""Dónde quedó instalado el programa: una sola metodología para todos.

El asistente de instalación deja elegir la carpeta con **Examinar**, y cuando
`C:` está justo de espacio lo que recomendamos es justamente eso: instalar en
otro disco. A partir de ahí, cualquier script que busque la instalación
probando rutas fijas se equivoca.

`owner/MVKobraAI_Owner.bat` ya lo resolvía bien (rutas, registro, carpeta
anotada), pero `packaging/Owner.bat` —el que convierte una copia instalada en
la edición Owner— probaba solo cuatro rutas fijas: con una instalación en
`D:\\MVKobraAI` daba el programa por no instalado y no había forma de pasarlo
a Owner sin copiar el .bat a mano hasta la carpeta.

Estos tests no pueden ejecutar un `.bat` desde Linux. Lo que blindan es que la
metodología esté completa en TODOS los scripts que buscan la instalación, y
que siga viniendo de un solo lugar (`packaging/deteccion_instalacion.py`): si
mañana se agrega una vía nueva de detección, o cambia el nombre de un archivo
de memoria, ningún script se queda atrás en silencio.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packaging"))

import deteccion_instalacion as deteccion  # noqa: E402

# Los scripts que tienen que encontrar una instalación ya hecha. `Owner.bat`
# se genera; el lanzador está escrito a mano.
SCRIPTS = {
    "packaging/Owner.bat": os.path.join(ROOT, "packaging", "Owner.bat"),
    "owner/MVKobraAI_Owner.bat": os.path.join(ROOT, "owner", "MVKobraAI_Owner.bat"),
}


@pytest.fixture(scope="module", params=sorted(SCRIPTS), ids=sorted(SCRIPTS))
def script(request):
    with open(SCRIPTS[request.param], encoding="utf-8", errors="replace") as f:
        return f.read()


def test_le_pregunta_al_registro_donde_quedo(script):
    """La única vía que aguanta el botón Examinar: el instalador anota la
    carpeta elegida en `InstallLocation`, la misma clave que usa «Agregar o
    quitar programas». Adivinar rutas no alcanza."""
    assert "InstallLocation" in script, "no consulta el registro"
    for rama in ("HKCU:", "HKLM:", "WOW6432Node"):
        assert rama in script, f"no mira la rama {rama}"


def test_mira_las_dos_convenciones_de_carpeta_anotada(script):
    """Conviven dos nombres para el archivo donde el instalador anota el
    destino elegido, y hay instalaciones en la calle con cada uno: mirar solo
    uno deja sin encontrar a la mitad."""
    for nombre in ("destino_owner.txt", "owner_destino.txt"):
        assert nombre in script, f"no mira {nombre}"


def test_prueba_las_rutas_por_defecto(script):
    """El caso barato y más común: nadie tocó Examinar.

    La comparación ignora mayúsculas porque las variables de entorno de
    Windows no distinguen (`%LocalAppData%` y `%LOCALAPPDATA%` son la misma) y
    cada script las escribe a su manera."""
    plano = script.lower()
    for ruta in deteccion.RUTAS_DEFAULT:
        assert ruta.lower() in plano, f"no prueba la ruta por defecto {ruta}"


def test_busca_antes_de_darse_por_vencido(script):
    """El orden es el arreglo: si el mensaje de «no lo encontré» quedara antes
    de la búsqueda, volvería el bug que se está corrigiendo.

    Se mira la INVOCACIÓN y no la definición de la subrutina: en batch las
    subrutinas viven al final del archivo, después del `exit /b`, así que su
    posición no dice nada sobre el orden en que se ejecutan."""
    sin_rem = "\n".join(ln for ln in script.splitlines()
                        if not ln.strip().lower().startswith("rem"))
    fin = min((sin_rem.index(m) for m in ("No encontre la instalacion",
                                          "todavia no esta instalado")
               if m in sin_rem), default=None)
    assert fin is not None, "no avisa cuando no encuentra la instalacion"
    invoca = [sin_rem.index(c) for c in ("call :buscar_en_registro",
                                         "call :buscar_instalado")
              if c in sin_rem]
    assert invoca, "no invoca la busqueda por registro"
    assert min(invoca) < fin, "consulta el registro DESPUES de darse por vencido"


# --- El generador y su salida no se pueden separar -------------------------
def test_owner_bat_esta_regenerado(tmp_path):
    """`packaging/Owner.bat` se genera; si alguien edita el generador y no lo
    corre, el .bat versionado queda viejo y nadie se entera hasta que un
    cliente lo ejecuta."""
    guardado = os.path.join(ROOT, "packaging", "Owner.bat")
    with open(guardado, "rb") as f:
        antes = f.read()
    r = subprocess.run([sys.executable, "packaging/generar_owner_bat.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"el generador falla:\n{r.stdout}\n{r.stderr}"
    with open(guardado, "rb") as f:
        despues = f.read()
    assert antes == despues, (
        "packaging/Owner.bat no coincide con lo que genera "
        "packaging/generar_owner_bat.py — correlo y commiteá el resultado")


def test_el_bat_generado_es_ascii_puro():
    """Se escribe con `encoding="ascii"`: una tilde en el texto rompe la
    generación. Y `cmd.exe` no abre un archivo con BOM."""
    with open(os.path.join(ROOT, "packaging", "Owner.bat"), "rb") as f:
        crudo = f.read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "quedó con BOM"
    crudo.decode("ascii")   # lanza si se coló un carácter no-ASCII


def test_el_bat_generado_usa_crlf():
    """Saltos de línea de Windows: con LF solo, `cmd.exe` se confunde."""
    with open(os.path.join(ROOT, "packaging", "Owner.bat"), "rb") as f:
        crudo = f.read()
    assert b"\r\n" in crudo
    assert crudo.count(b"\n") == crudo.count(b"\r\n"), "hay saltos sueltos sin \\r"


def test_la_subrutina_del_registro_no_deja_basura(script):
    """Escribe la respuesta en un temporal (para no pelear con el parser de
    cmd) y lo borra siempre, incluso si no encontró nada."""
    for tmp in ("!KOBRA_RESP_DIR!", "!KOBRA_RESP_APP!"):
        if tmp in script:
            assert script.count(f'del "{tmp}"') >= 2, \
                f"{tmp} no se borra en todos los caminos"
            return
    pytest.fail("la subrutina del registro no usa un archivo temporal propio")
