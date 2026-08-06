"""Lo que importa la suite tiene que estar DECLARADO en algún requirements.

Bug real: `tests/test_instalador_owner.py` importaba `yaml` (PyYAML), que en la
máquina de desarrollo estaba instalado por transitividad —lo arrastran uvicorn
y watchdog— pero no figuraba en ningún requirements. La suite pasaba local
(718 passed) y el CI moría en la fase de *colección*, antes de correr un solo
test:

    ImportError while importing test module 'tests/test_instalador_owner.py'
    ModuleNotFoundError: No module named 'yaml'

Un fallo en colección es peor que un test rojo: pytest aborta la corrida
entera, así que los otros 717 tests tampoco se ejecutan. Y la señal aparece
recién en CI, cuando el trabajo ya está commiteado y pusheado.

Este test cierra el hueco desde el lado que importa: no pide que las versiones
coincidan ni que el entorno esté limpio, solo que **cada paquete de terceros
que la suite importa esté nombrado en `requirements.txt` o en
`requirements-dev.txt`**. Es la diferencia entre "me anda a mí" y "anda en una
máquina limpia", que es justamente lo que `requirements-dev.txt` vino a
resolver.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# Paquetes del propio proyecto: no van a ningún requirements.
PROPIOS = {"kobra", "webapp", "backend_venta", "realtime", "data", "marketing",
           "app", "packaging", "tests", "electron", "owner"}

# Import → nombre en PyPI, cuando no coinciden.
EQUIVALENCIAS = {
    "yaml": "pyyaml",
    "jwt": "pyjwt",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "pptx": "python-pptx",
    "dateutil": "python-dateutil",
    "cv2": "opencv-python",
    "soundfile": "soundfile",
    "anyio": "anyio",
}


def _importados_por_la_suite():
    """Paquetes de terceros importados **a nivel de módulo** en `tests/`.

    Solo el nivel de módulo, y es la parte importante. Un import ahí que
    falla rompe la COLECCIÓN: pytest aborta la corrida entera y no se ejecuta
    ningún test, ni siquiera los que no tienen nada que ver. Un import dentro
    de una función solo hace fallar ese test, y en esta suite los que están
    así (`PIL`, `anyio`) o van guardados con `pytest.importorskip`
    (`playwright`) se saltean solos cuando el paquete no está.

    Por eso se recorre `arbol.body` y no `ast.walk`: exigirle a un import
    opcional que esté declarado obligaría a instalar Playwright —cientos de
    MB— para correr tests que no lo usan.
    """
    encontrados = set()
    for archivo in TESTS.glob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if isinstance(nodo, ast.Import):
                encontrados |= {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                encontrados.add(nodo.module.split(".")[0])
    return encontrados - set(sys.stdlib_module_names) - PROPIOS


def _declarados():
    """Nombres de paquete que aparecen en los dos requirements."""
    nombres = set()
    for req in ("requirements.txt", "requirements-dev.txt"):
        ruta = ROOT / req
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            # "pandas>=2.0", "PyYAML>=6.0", "httpx>=0.27" -> nombre pelado
            m = re.match(r"^([A-Za-z0-9_.\-]+)", linea)
            if m:
                nombres.add(m.group(1).lower().replace("_", "-"))
    return nombres


def test_todo_lo_que_importa_la_suite_esta_declarado():
    """El defecto exacto: PyYAML importado y no declarado. Local pasaba por
    transitividad; en CI la colección abortaba y no corría NINGÚN test."""
    declarados = _declarados()
    faltan = []
    for paquete in sorted(_importados_por_la_suite()):
        pypi = EQUIVALENCIAS.get(paquete, paquete).lower().replace("_", "-")
        if pypi not in declarados:
            faltan.append(f"{paquete} (pip: {pypi})")
    assert not faltan, (
        "la suite importa paquetes que no estan en ningun requirements —"
        f" en una maquina limpia la coleccion aborta: {faltan}")


def test_pyyaml_esta_en_las_de_desarrollo_y_no_en_las_de_ejecucion():
    """Dónde se declara importa: `requirements.txt` viaja DENTRO del instalador
    de Windows, y el programa no usa PyYAML — solo lo usan los tests que leen
    los workflows y la config de electron-builder."""
    ejecucion = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    desarrollo = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "pyyaml" in desarrollo, "PyYAML no esta declarada como dependencia de test"
    lineas = [ln.strip() for ln in ejecucion.splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
    assert not any(ln.startswith("pyyaml") for ln in lineas), \
        "PyYAML quedo en requirements.txt: viajaria en el instalador sin usarse"


def test_el_ci_instala_las_dos_listas():
    """Si el workflow instalara solo `requirements.txt`, declarar las de test
    en el archivo correcto no serviría de nada."""
    wf = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "requirements-dev.txt" in wf, "el CI no instala las dependencias de test"
    assert "requirements.txt" in wf
