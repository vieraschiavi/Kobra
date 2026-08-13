# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Edición del paquete y su vigencia
===============================================
Cada paquete descargable lleva un `edicion.json` en su raíz que dice qué es:

    {"edition": "Demo", "plan": "trial", "dias": 14, "owner": false,
     "secreto": "...", "token": "..."}       ← demo/plan
    {"edition": "Owner", "plan": null, "dias": null, "owner": true}   ← owner

Este módulo es el ÚNICO lugar donde se interpreta ese archivo, y existe
porque el mismo paquete se puede abrir por dos caminos distintos:

  * `kobra_launcher.py`  → app de escritorio (React + FastAPI)
  * `kobra_streamlit.py` → dashboard Streamlit (la vía sin .exe)

Antes la lógica vivía dentro del primero. Cuando se agregó el dashboard como
segunda vía, esa asimetría se volvía un agujero comercial: la Demo abierta por
Streamlit no leía su propio `edicion.json` y por lo tanto **no aplicaba el
límite de días** — evaluación gratis para siempre con solo elegir el otro
acceso directo. Centralizarlo acá hace que las dos vías apliquen la misma
edición por construcción, y `tests/test_doble_modo.py` lo fija.
"""
from __future__ import annotations

import json
import os

ARCHIVO = "edicion.json"
CLAVE_TOKEN = "LICENCIA_TOKEN"


def leer(base: str) -> dict | None:
    """El `edicion.json` del paquete, o None si es una copia del repo."""
    ruta = os.path.join(base, ARCHIVO)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


def activar(base: str) -> dict | None:
    """Aplica la edición antes de levantar el programa.

      - owner     → `KOBRA_OWNER=1` (sin licencia ni vencimiento).
      - demo/plan → siembra el secreto de firma y el token embebidos, así la
        app valida sola y aplica días/cupo/features sin que el usuario active
        nada.

    Idempotente: solo siembra el token la primera vez, para no pisar uno que
    el usuario haya activado después (por ejemplo, al comprar un plan).
    """
    ed = leer(base)
    if ed is None:
        return None
    if ed.get("owner"):
        os.environ["KOBRA_OWNER"] = "1"
        return ed
    secreto, token = ed.get("secreto"), ed.get("token")
    if secreto:
        os.environ.setdefault("KOBRA_LICENSE_SECRET", secreto)
    if token:
        try:
            from kobra import config as kconfig
            if not kconfig.leer_extra(CLAVE_TOKEN):
                kconfig.guardar_extra(CLAVE_TOKEN, token)
        except Exception:
            # Sin config escribible el programa igual tiene que abrir: la
            # licencia se revalida en cada arranque desde `edicion.json`.
            pass
    return ed


def es_owner() -> bool:
    """¿Es la copia del dueño? Pública: la consultan otros módulos (p. ej.
    `kobra/plan.py`, para eximir al owner del cupo de cualquier plan)."""
    if os.environ.get("KOBRA_OWNER", "").lower() in ("1", "true", "si", "sí"):
        return True
    try:
        from kobra import config as kconfig
        return bool(kconfig.leer_extra("KOBRA_OWNER_ACTIVADO"))
    except Exception:
        return False


# Alias retrocompatible: el resto de este archivo y los tests existentes usan
# el nombre viejo con guion bajo.
_es_owner = es_owner


def vigencia() -> dict:
    """¿Se puede usar el programa ahora mismo?

    Devuelve `{ok, motivo, dias_restantes, owner, plan}`. `ok=True` cuando es
    la edición del dueño, cuando no hay edición (correr desde el repo) o
    cuando la licencia embebida sigue vigente.
    """
    if _es_owner():
        return {"ok": True, "motivo": None, "dias_restantes": None,
                "owner": True, "plan": "owner"}
    try:
        from backend_venta import licencias as klic
        from kobra import config as kconfig
    except Exception:
        return {"ok": True, "motivo": None, "dias_restantes": None,
                "owner": False, "plan": None}

    token = kconfig.leer_extra(CLAVE_TOKEN)
    if not token:
        # Sin token no hay edición que aplicar: es una copia del repo o una
        # instalación libre. No inventamos un bloqueo que nadie configuró.
        return {"ok": True, "motivo": None, "dias_restantes": None,
                "owner": False, "plan": None}

    r = klic.licencia_activa(token)
    if not r["ok"]:
        return {"ok": False, "motivo": r["error"], "dias_restantes": 0,
                "owner": False, "plan": None}
    import time
    claims = r["claims"]
    dias = max(0, int((claims.get("exp", 0) - time.time()) // 86400))
    return {"ok": True, "motivo": None, "dias_restantes": dias,
            "owner": False, "plan": claims.get("plan")}
