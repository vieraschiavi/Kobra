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

# 2) Espacio en disco (best-effort, no bloquea si no puede leerlo)
FREEGB=$(df -Pk . 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')
if [ -n "$FREEGB" ]; then
  echo "Espacio libre en disco: ~${FREEGB} GB"
  if [ "$FREEGB" -lt 3 ]; then
    echo "(!) Muy poco espacio libre (~${FREEGB} GB). Las dependencias necesitan"
    echo "unos 3 GB libres para descargarse e instalarse bien. Liberá espacio"
    echo "y volvé a ejecutar este script."
    exit 1
  fi
fi

# 3) venv propio + dependencias (idempotente)
if [ ! -x ".kobra_venv/bin/python" ]; then
  echo "[1/2] Creando entorno virtual..."
  python3 -m venv .kobra_venv
fi
echo "[2/2] Instalando/verificando dependencias (puede tardar la 1a vez)..."
.kobra_venv/bin/python -m pip install --no-cache-dir --upgrade pip >/dev/null
.kobra_venv/bin/python -m pip install --no-cache-dir -r requirements.txt

# 3) Arranque en modo owner, usando la UI ya compilada (sin necesitar Node)
export KOBRA_OWNER=1
export KOBRA_UI_DIST="$(pwd)/owner/ui_dist"
export KOBRA_APP_WINDOW=1
exec .kobra_venv/bin/python packaging/kobra_launcher.py
