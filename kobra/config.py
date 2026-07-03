"""
Kobra · Configuración persistente (API keys)
============================================
Guarda las API keys una sola vez y las reutiliza en cada arranque, sin tener
que reingresarlas. Se persisten en un archivo JSON fuera del repo:

    $KOBRA_CONFIG_DIR/config.json   (por defecto ~/.kobra/config.json)

Precedencia: una variable de entorno real (inyectada en producción) tiene
prioridad sobre el archivo. `aplicar()` carga las keys guardadas al entorno
para que Whisper (OpenAI) y Claude (Anthropic) funcionen automáticamente.

Nota de seguridad: para una demo se guarda en texto plano con permisos 600.
En producción usar un secreto gestionado (Docker/K8s secrets, Vault, etc.).
"""
import json
import os

CONFIG_DIR = os.environ.get("KOBRA_CONFIG_DIR", os.path.expanduser("~/.kobra"))
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

CLAVES = {
    "OPENAI_API_KEY": "OpenAI · transcripción Whisper (voz → texto)",
    "ANTHROPIC_API_KEY": "Anthropic · evaluación con Claude",
    "TWILIO_ACCOUNT_SID": "Twilio · Account SID (llamadas reales)",
    "TWILIO_AUTH_TOKEN": "Twilio · Auth Token (llamadas reales)",
    "TWILIO_FROM": "Twilio · número emisor (ej. +1…) para llamar",
}


def cargar() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def guardar(nuevos: dict) -> dict:
    """Guarda solo las keys con valor; no pisa las existentes con vacíos."""
    cfg = cargar()
    for k, v in nuevos.items():
        if k in CLAVES and v and v.strip():
            cfg[k] = v.strip()
            os.environ[k] = v.strip()
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    return cfg


def limpiar():
    """Borra la configuración guardada y las keys del entorno."""
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    for k in CLAVES:
        os.environ.pop(k, None)


def aplicar():
    """Carga las keys guardadas al entorno (sin pisar variables ya presentes)."""
    for k, v in cargar().items():
        if v and not os.environ.get(k):
            os.environ[k] = v


def estado() -> dict:
    """Devuelve qué keys están activas (por entorno o archivo)."""
    aplicar()
    return {k: bool(os.environ.get(k)) for k in CLAVES}


def enmascarar(valor: str) -> str:
    if not valor:
        return ""
    return f"{valor[:3]}…{valor[-4:]}" if len(valor) > 8 else "•••"
