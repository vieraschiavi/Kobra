#!/usr/bin/env bash
# © 2026 Martín Viera. Todos los derechos reservados.
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
# El sello firmado, no el viejo KOBRA_OWNER=1: ese "1" dejó de desbloquear
# nada cuando la edición del dueño pasó a exigir un token firmado con la
# privada, y este script quedó prometiendo "entra directo" y entregando la
# pantalla de acceso.
if [ -z "${KOBRA_OWNER_TOKEN:-}" ]; then
  if [ -n "${KOBRA_OWNER_SELLO:-}" ]; then
    export KOBRA_OWNER_TOKEN="$KOBRA_OWNER_SELLO"
  elif [ -n "${KOBRA_OWNER_SELLO_ARCHIVO:-}" ] && [ -r "$KOBRA_OWNER_SELLO_ARCHIVO" ]; then
    # tr -d: un token guardado desde un mail llega con saltos de línea, y un
    # JWT no lleva espacios, así que juntarlo es seguro.
    export KOBRA_OWNER_TOKEN="$(tr -d '[:space:]' < "$KOBRA_OWNER_SELLO_ARCHIVO")"
  else
    echo "  (i) Sin sello del dueño: el programa va a pedirte crear una clave."
    echo "      Para entrar directo, dejá el token una sola vez:"
    echo "        export KOBRA_OWNER_SELLO_ARCHIVO=~/.kobra_sello_owner.txt"
  fi
fi
export KOBRA_UI_DIST="$(pwd)/owner/ui_dist"
export KOBRA_APP_WINDOW=1
exec .kobra_venv/bin/python packaging/kobra_launcher.py
