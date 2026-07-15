#!/usr/bin/env bash
# MV Kobra AI · modo OWNER desde el código fuente (Linux/Mac).
# Sin licencia ni trial — entra directo como Administrador.
set -e
cd "$(dirname "$0")/.."
export KOBRA_OWNER=1
exec python3 packaging/kobra_launcher.py
