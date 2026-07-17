#!/usr/bin/env bash
# SessionStart hook — MV Kobra AI. Deja el entorno listo al abrir sesión de Claude Code.
# Idempotente. Generado por la skill automatizador-proyecto.
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

log() { printf '\033[0;36m[automator]\033[0m %s\n' "$1"; }

if [ -f requirements.txt ]; then
  log "Instalando dependencias Python"
  pip3 install -q -r requirements.txt || log "aviso: falló pip install (revisar red/venv)"
fi

log "Verificando import del núcleo (kobra)"
python3 -c "import importlib.util as u; print('kobra OK' if u.find_spec('kobra') else 'kobra no importable aún')" || true

log "Entorno listo ✔  (tests: python3 -m pytest -q tests/ · app: streamlit run app/app.py)"
