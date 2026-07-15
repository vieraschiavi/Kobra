#!/usr/bin/env bash
# MV Kobra AI · modo OWNER desde el código fuente (Linux/Mac).
# Prepara todo solo: venv, dependencias e interfaz ya compilada.
# Entra directo como Administrador — sin licencia ni trial.
set -e
cd "$(dirname "$0")/.."

echo "== MV Kobra AI · OWNER =="

# 1) Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3.11+. Instalalo (brew install python@3.11 / apt install python3)."
  exit 1
fi

# 2) venv propio + dependencias (idempotente)
if [ ! -x ".kobra_venv/bin/python" ]; then
  echo "[1/2] Creando entorno virtual..."
  python3 -m venv .kobra_venv
fi
echo "[2/2] Instalando/verificando dependencias (puede tardar la 1a vez)..."
.kobra_venv/bin/python -m pip install --upgrade pip >/dev/null
.kobra_venv/bin/python -m pip install -r requirements.txt

# 3) Arranque en modo owner, usando la UI ya compilada (sin necesitar Node)
export KOBRA_OWNER=1
export KOBRA_UI_DIST="$(pwd)/owner/ui_dist"
exec .kobra_venv/bin/python packaging/kobra_launcher.py
