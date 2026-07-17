#!/usr/bin/env bash
# SessionStart hook — se ejecuta al abrir una sesión de Claude Code.
# Objetivo: dejar el entorno listo (deps instaladas) y verificar que el proyecto arranca.
# ADAPTAR los bloques al stack real. Idempotente: correrlo dos veces no debe romper nada.
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

log() { printf '\033[0;36m[automator]\033[0m %s\n' "$1"; }

# --- Node / TS ---
if [ -f package.json ]; then
  log "Node detectado — instalando deps"
  if [ -f package-lock.json ]; then npm ci --silent || npm install --silent; else npm install --silent; fi
fi

# --- Python ---
if [ -f requirements.txt ]; then
  log "Python detectado — instalando requirements"
  pip install -q -r requirements.txt || true
elif [ -f pyproject.toml ]; then
  log "Python (pyproject) detectado"
  pip install -q -e . 2>/dev/null || true
fi

# --- Go ---
if [ -f go.mod ]; then log "Go detectado — descargando módulos"; go mod download || true; fi

# --- Rust ---
if [ -f Cargo.toml ]; then log "Rust detectado"; cargo fetch || true; fi

log "Entorno listo ✔"
