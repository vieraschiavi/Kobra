"""
MV Kobra AI · Carpeta de datos escribibles
=========================================
El programa instalado en Windows vive en una carpeta de solo lectura para
un usuario sin privilegios de administrador (típicamente Program Files) —
cualquier escritura relativa a esa carpeta (subidas de audio, cartera y
outputs generados, logs de auditoría, backups, datos por tenant) fallaba
con PermissionError: [WinError 5] Acceso denegado.

`DIR_DATOS` resuelve SIEMPRE a un lugar escribible por el usuario actual:

  - Corriendo empaquetado (PyInstaller, `sys.frozen`): `%LOCALAPPDATA%\\MV
    Kobra AI` en Windows, `~/.mv_kobra_ai` en Linux/Mac — independiente de
    dónde esté instalado el programa.
  - Corriendo desde el código fuente (dev, tests, CI): la raíz del propio
    repo, exactamente como siempre — cero cambios en el flujo de desarrollo
    ni en los tests existentes.
  - `KOBRA_DATA_DIR` fuerza cualquier ubicación explícita (mismo criterio
    que `KOBRA_CONFIG_DIR` en `kobra/config.py`).

`sembrar_si_hace_falta()` copia una sola vez, en el primer arranque
empaquetado, los datos de demo bundleados (`data/`, `outputs/`) desde la
carpeta de instalación hacia `DIR_DATOS` — así la demo sigue funcionando
"out of the box" sin que el usuario tenga que cargar nada.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _instalado() -> bool:
    return bool(getattr(sys, "frozen", False))


def _default_dir_datos() -> str:
    if not _instalado():
        return ROOT_REPO
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "MV Kobra AI")
    return os.path.expanduser("~/.mv_kobra_ai")


DIR_DATOS = os.environ.get("KOBRA_DATA_DIR") or _default_dir_datos()

# Carpeta de recursos bundleados de SOLO LECTURA (el propio bundle de
# PyInstaller, vía sys._MEIPASS) — separada de DIR_DATOS a propósito: nunca
# hay que escribir ahí, solo leer lo que trae la instalación (demo, docs).
DIR_BUNDLE = getattr(sys, "_MEIPASS", ROOT_REPO)


def sembrar_si_hace_falta() -> None:
    """Primera vez que corre empaquetado: copia data/ y outputs/ bundleados
    (demo sintética) a DIR_DATOS, si todavía no existen ahí. Nunca pisa datos
    reales que el usuario ya haya cargado."""
    if not _instalado() or DIR_DATOS == ROOT_REPO:
        return
    for carpeta in ("data", "outputs"):
        origen = os.path.join(DIR_BUNDLE, carpeta)
        destino = os.path.join(DIR_DATOS, carpeta)
        if os.path.isdir(origen) and not os.path.isdir(destino):
            shutil.copytree(origen, destino)
