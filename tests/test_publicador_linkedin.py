"""Engancha la suite del publicador de LinkedIn al CI de Kobra.

La herramienta vive en `marketing/linkedin/` con sus propios tests
(`unittest`, sin red, contra un LinkedIn falso en localhost). El CI de este
repo corre `pytest -q tests/` y nada más: sin este archivo, esos 29 tests
existirían pero no correría ninguno en ningún push, que es la peor forma de
tener tests — la carpeta se ve cubierta y no lo está.

Se corre como subproceso a propósito. La suite se apoya en el `sys.path` que
arma `unittest discover` desde su propio directorio; importarla acá la haría
depender del rootdir de pytest, que cambia según desde dónde se invoque.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERRAMIENTA = Path(__file__).resolve().parents[1] / "marketing" / "linkedin"


def test_la_suite_del_publicador_de_linkedin_pasa():
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        cwd=HERRAMIENTA, capture_output=True, text=True, timeout=180,
    )
    # La salida cruda va al assert: si esto se pone en rojo, el motivo tiene
    # que leerse acá y no obligar a nadie a reproducirlo a mano.
    assert r.returncode == 0, f"\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
