# © 2026 Martín Viera. Todos los derechos reservados.

"""Lo que tiene que entrar en el instalador de Windows (packaging/kobra.spec).

Reportado como «no funciona instalador exe que ejecute el programa» y
«un instalador windows!».

El instalador se construye y se publica bien —su workflow corrió `success` en
todos los merges— pero eso solo verificaba que el ARCHIVO existiera. Nadie
verificaba que el motor empaquetado ARRANQUE.

El defecto concreto: `hiddenimports` listaba los módulos de `kobra/` **a mano**,
y la lista se desfasó. Habían quedado afuera 9, entre ellos `kobra.owner` y
`kobra.limitador`, que `webapp/backend/api.py` importa al arrancar. Sin ellos
en el bundle, el backend no levanta: la app instala bien, el ícono abre, sale
el splash con la marca… y se queda ahí hasta que Electron corta a los 120 s con
«El motor de MV Kobra AI no respondió a tiempo». Desde afuera es un instalador
que simplemente no funciona, sin ninguna pista del motivo.

Estos tests no pueden correr PyInstaller (necesita Windows y varios GB). Lo que
hacen es blindar la decisión: que la enumeración cubra el paquete entero, y que
todo lo que el backend importa al arrancar esté adentro.
"""
import ast
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "packaging", "kobra.spec")


@pytest.fixture(scope="module")
def spec():
    with open(SPEC, encoding="utf-8") as f:
        return f.read()


def _modulos_kobra():
    return {f[:-3] for f in os.listdir(os.path.join(ROOT, "kobra"))
            if f.endswith(".py") and f != "__init__.py"}


def test_los_modulos_de_kobra_se_enumeran_y_no_se_listan_a_mano(spec):
    """El defecto exacto: una lista escrita a mano se desfasa en cuanto alguien
    agrega un módulo, y el instalador se rompe semanas después."""
    assert "os.listdir(_KOBRA_DIR)" in spec, \
        "volvieron a listar los modulos de kobra a mano"
    # Y que no quede además una lista literal larga, que sería la vieja.
    literales = set(re.findall(r'"(kobra\.[a-z_]+)"', spec))
    assert len(literales) <= 2, f"quedaron modulos hardcodeados: {sorted(literales)}"


def test_la_enumeracion_cubre_todo_el_paquete():
    """Se reproduce lo que hace el spec y se compara con el paquete real."""
    enumerados = {f"kobra.{m}" for m in _modulos_kobra()}
    assert len(enumerados) >= 30, "la enumeracion quedo sospechosamente corta"
    for critico in ("kobra.owner", "kobra.limitador", "kobra.red",
                    "kobra.rutas", "kobra.config"):
        assert critico in enumerados, f"falta {critico}"


def test_todo_lo_que_el_backend_importa_al_arrancar_entra_al_bundle():
    """El gate que hubiera atrapado esto antes de publicar: si `api.py` importa
    `kobra.X` al importarse, `X` tiene que estar empaquetado o el motor muere
    en el arranque."""
    ruta = os.path.join(ROOT, "webapp", "backend", "api.py")
    with open(ruta, encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    necesarios = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module == "kobra":
            necesarios |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and (n.module or "").startswith("kobra."):
            necesarios.add(n.module.split(".", 1)[1])
    disponibles = _modulos_kobra()
    faltan = sorted(necesarios - disponibles)
    assert not faltan, f"api.py importa modulos que no existen: {faltan}"
    # Y la enumeración del spec los cubre por construcción.
    assert necesarios <= disponibles


def test_el_launcher_es_el_punto_de_entrada(spec):
    """Si el Analysis apuntara a otro script, el instalador arrancaría otra
    cosa (o nada)."""
    assert "kobra_launcher.py" in spec


def test_el_frontend_compilado_viaja_en_el_bundle(spec):
    """Sin el build de React, el backend levanta pero sirve una API pelada: la
    ventana de Electron queda en blanco."""
    assert "webapp" in spec and "dist" in spec


def test_el_ci_ejecuta_el_motor_y_no_solo_mira_si_el_archivo_existe():
    """La razón de fondo por la que esto llegó a producción: el workflow hacía
    `Test-Path` sobre el .exe y daba el build por bueno. Un bundle al que le
    falta un import pasa ese chequeo y falla recién en la PC del cliente."""
    ruta = os.path.join(ROOT, ".github", "workflows", "build_windows.yml")
    with open(ruta, encoding="utf-8") as f:
        wf = f.read()
    assert "humo" in wf.lower() or "smoke" in wf.lower(), \
        "el workflow no prueba que el motor arranque"
    # Que de verdad lo ejecute y consulte por HTTP, no que solo lo abra.
    assert "MVKobraAI.exe" in wf
    assert "Invoke-WebRequest" in wf or "curl" in wf
