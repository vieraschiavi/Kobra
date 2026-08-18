#!/usr/bin/env python3
# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Correr lo mismo que corre CI, antes de pushear
=============================================================
Un pull request en rojo casi nunca es culpa de CI: es que en la máquina se
corrió MENOS de lo que corre allá. Las dos últimas fallas de este repo fueron
exactamente eso —`ruff` una vez, un test que se encontró a sí mismo la otra— y
las dos se habrían visto acá en dos minutos.

CI corre cuatro verificaciones en cada PR. Con `python3 -m pytest` solo se
cubren una. Este script corre las cuatro, en el mismo orden y con los mismos
comandos, y `tests/test_verificar_cubre_ci.py` falla si CI suma una y este
script no se entera. Esa es la parte que importa: la lista no se puede
desactualizar en silencio.

Uso:
    python3 verificar.py              # todo (lo que corre un PR)
    python3 verificar.py --rapido     # sin la suite de Python (~10 s)
    python3 verificar.py --instalar-hook   # correrlo solo antes de cada push
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# El generador de datos escribe en `data/kobra_cartera.csv`, que está
# versionado. En CI eso da igual —la máquina se tira al terminar—, pero acá
# dejaría el árbol sucio y el archivo entra al próximo `git add -A` sin que
# nadie lo note: el dataset del repo tiene 12.000 filas y el de CI 3.000, así
# que el commit pisaría uno con el otro. Se manda a un temporal; lo que se
# verifica —que el generador corra con la semilla fija— es lo mismo.
_CSV_TEMPORAL = os.path.join(tempfile.gettempdir(), "kobra_verificar_cartera.csv")

# Las verificaciones de `.github/workflows/ci.yml`, en su mismo orden. Los
# pasos de instalación (pip, npm ci, apt) no van: acá el entorno ya está.
#
# Si agregás una verificación a CI, agregala también acá — hay un test que lo
# comprueba y que falla hasta que las dos listas coinciden.
GATES = [
    ("Linter (ruff)", ["ruff", "check", "."], False),
    ("Tests de pagos y licencias (node)", ["npm", "test"], False),
    ("Dataset con semilla fija", [sys.executable, "data/generate_dataset.py",
                                  "--n", "3000", "--seed", "42",
                                  "--out", _CSV_TEMPORAL], False),
    ("Suite de Python", [sys.executable, "-m", "pytest", "-q", "-rs", "tests/"], True),
]


def _falta(cmd: list[str]) -> str:
    """Si la herramienta no está, decirlo con el comando para instalarla en vez
    de escupir un FileNotFoundError."""
    if shutil.which(cmd[0]) is None:
        remedios = {"ruff": "pip install -r requirements-dev.txt",
                    "npm": "instalá Node 22+"}
        return f"falta `{cmd[0]}` — {remedios.get(cmd[0], 'instalalo y volvé a probar')}"
    if cmd[0] == "npm" and not os.path.isdir(os.path.join(ROOT, "node_modules")):
        return "faltan las dependencias de Node — corré `npm ci`"
    return ""


def correr(lento: bool) -> int:
    fallaron = []
    for nombre, cmd, es_lento in GATES:
        if es_lento and not lento:
            print(f"  ⏭  {nombre} (salteado por --rapido)")
            continue
        problema = _falta(cmd)
        if problema:
            print(f"  ✗  {nombre}: {problema}")
            fallaron.append(nombre)
            continue
        print(f"  ▶  {nombre}…", flush=True)
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT)
        seg = time.time() - t0
        if r.returncode == 0:
            print(f"  ✓  {nombre}  ({seg:.0f}s)")
        else:
            print(f"  ✗  {nombre}  (código {r.returncode})")
            fallaron.append(nombre)

    print()
    if fallaron:
        print(f"  {len(fallaron)} verificación(es) en rojo: {', '.join(fallaron)}")
        print("  Arreglalas antes de pushear — CI va a fallar igual.")
        return 1
    print("  Todo verde. Esto es lo mismo que va a correr CI en el pull request.")
    return 0


HOOK = """#!/bin/sh
# Generado por `python3 verificar.py --instalar-hook`.
# Corre las mismas verificaciones que CI antes de dejar pushear.
# Para saltearlo una vez: git push --no-verify
exec python3 "$(git rev-parse --show-toplevel)/verificar.py"
"""


def instalar_hook() -> int:
    hooks = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
    destino = os.path.join(ROOT, hooks, "pre-push")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="ascii", newline="\n") as f:
        f.write(HOOK)
    os.chmod(destino, 0o755)
    print(f"  Hook instalado en {destino}")
    print("  Desde ahora `git push` corre las verificaciones primero.")
    print("  Para saltearlo una vez: git push --no-verify")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rapido", action="store_true",
                    help="sin la suite de Python (~10 s en vez de ~3 min)")
    ap.add_argument("--instalar-hook", action="store_true",
                    help="correr esto solo, antes de cada git push")
    args = ap.parse_args()
    if args.instalar_hook:
        return instalar_hook()
    print("\n  Verificando lo mismo que corre CI\n")
    return correr(lento=not args.rapido)


if __name__ == "__main__":
    sys.exit(main())
