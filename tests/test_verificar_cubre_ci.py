# © 2026 Martín Viera. Todos los derechos reservados.

"""`verificar.py` corre lo mismo que CI, y no se puede desactualizar callado.

Un pull request en rojo casi nunca es culpa de CI: es que en la máquina se
corrió MENOS de lo que corre allá. Las dos últimas fallas de este repo fueron
exactamente eso — `ruff check .` una vez, y un test que se encontró a sí mismo
la otra. Las dos se habrían visto localmente en dos minutos, y las dos las
produjo alguien (yo) que corrió `pytest` y dio por hecho que eso era todo.

`verificar.py` corre las cuatro verificaciones del PR. Este test es la parte
que hace que eso siga siendo cierto: si mañana CI suma un gate —un typecheck,
un audit de dependencias, un build del frontend— y nadie lo agrega al script,
esto falla y lo dice con el comando exacto que falta.

Un script de verificación que quedó viejo es peor que no tenerlo: da la
tranquilidad sin dar la cobertura.
"""
import os
import re

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
SCRIPT = os.path.join(ROOT, "verificar.py")

# Pasos de CI que preparan el entorno, no que verifican. Acá el entorno ya
# está: correr `apt-get` o `npm ci` en la máquina de alguien sería invasivo.
PREPARACION = ("instalar", "configurar", "generar dataset")


def _pasos_de_ci():
    """(nombre, comando) de cada paso de CI que verifica algo en un PR."""
    with open(CI, encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    for paso in wf["jobs"]["test"]["steps"]:
        if "run" not in paso:
            continue
        nombre = paso.get("name", "")
        # Los pasos `if: push` son de main, no del PR — un PR nunca los corre,
        # así que exigirlos localmente sería pedir tres minutos de más.
        if "push" in str(paso.get("if", "")):
            continue
        if any(p in nombre.lower() for p in PREPARACION):
            continue
        yield nombre, paso["run"].strip()


def _script():
    with open(SCRIPT, encoding="utf-8") as f:
        return f.read()


def test_hay_algo_que_verificar():
    """Si el parseo de ci.yml se rompe, los otros tests pasarían por vacíos."""
    pasos = list(_pasos_de_ci())
    assert len(pasos) >= 2, f"solo se detectaron {len(pasos)} pasos de CI: {pasos}"


@pytest.mark.parametrize("nombre,comando", list(_pasos_de_ci()))
def test_cada_verificacion_de_ci_esta_en_el_script(nombre, comando):
    """El gate que evita el rojo: lo que corre CI tiene que poder correrse acá."""
    script = _script()
    # Se compara por la herramienta y sus argumentos distintivos, no por la
    # línea entera: el script invoca Python con `sys.executable` y no con
    # `python`, que es lo correcto dentro de un venv.
    piezas = comando.split()
    herramienta = piezas[0] if piezas[0] != "python" else piezas[2]
    assert herramienta in script, (
        f"CI corre «{comando}» en el paso «{nombre}» y verificar.py no lo "
        f"tiene. Agregalo a GATES o un PR va a poder ponerse en rojo por algo "
        f"que nadie pudo ver antes de pushear.")


def test_el_script_corre_el_linter_y_los_tests_de_node():
    """Los dos que se saltean más seguido: `ruff` porque es rápido y se olvida,
    y `npm test` porque nadie asocia "cambié Python" con "hay 70 tests de Node
    que cuidan el cobro"."""
    script = _script()
    assert '"ruff", "check", "."' in script, "verificar.py no corre ruff"
    assert '"npm", "test"' in script, "verificar.py no corre los tests de Node"


def test_el_script_avisa_si_falta_la_herramienta():
    """Un `FileNotFoundError: ruff` no le dice a nadie qué hacer."""
    script = _script()
    assert "shutil.which" in script, "no comprueba que la herramienta exista"
    assert "requirements-dev.txt" in script, \
        "no dice cómo instalar lo que falta"


def test_el_script_sale_con_codigo_distinto_de_cero_si_algo_falla():
    """Sin esto el hook de pre-push dejaría pasar todo."""
    script = _script()
    assert re.search(r"return 1", script), "nunca devuelve un código de error"
    assert "--no-verify" in script, \
        "el hook no documenta cómo saltearse una vez (y entonces se borra)"



# ---------------------------------------------------------------------------
# Que la promesa siga siendo cierta
# ---------------------------------------------------------------------------
def test_ci_es_el_unico_workflow_que_corre_en_un_pull_request():
    """`verificar.py` cubre `ci.yml`. Esa cobertura vale el 100% solo mientras
    `ci.yml` sea el único workflow que se dispara en un PR.

    Si mañana `build_windows.yml` suma `pull_request` —construir el instalador
    en cada PR es una idea razonable—, un PR va a poder ponerse en rojo por un
    build de Windows que nadie puede reproducir localmente, y el script diría
    "todo verde" igual. Este test obliga a decidirlo a conciencia.
    """
    import glob
    otros = []
    for ruta in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
        with open(ruta, encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        # PyYAML lee la clave `on:` como el booleano True (norma YAML 1.1).
        disparadores = wf.get("on", wf.get(True)) or {}
        if "pull_request" not in disparadores:
            continue
        nombre = os.path.basename(ruta)
        if nombre != "ci.yml":
            otros.append(nombre)
    assert not otros, (
        "estos workflows corren en un pull request además de ci.yml: "
        f"{', '.join(otros)}. O los cubrís en verificar.py, o un PR se puede "
        "poner en rojo por algo que nadie pudo ver antes de pushear.")


def test_el_script_muestra_los_tests_salteados():
    """Un test salteado acá no verificó nada acá — y puede correr en CI.

    El caso concreto: `test_una_carpeta_sin_permiso_de_escritura_se_rechaza` se
    saltea como root (contenedores, CI de otros) y CORRE en el runner de
    GitHub, que no es root. Verde local, rojo remoto. `-rs` los lista con el
    motivo para que se vean en vez de perderse entre mil puntos.
    """
    script = _script()
    assert '"-rs"' in script, \
        "pytest corre sin -rs: los salteados quedan invisibles"
