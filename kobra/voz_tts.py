# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Síntesis de voz premium (ElevenLabs) — opcional
================================================================
Por defecto, la voz de las llamadas usa `<Say>` de Twilio (voces Amazon
Polly, ya incluidas en la cuenta de Twilio del cliente — sin costo extra
más allá de lo que Twilio ya cobra por minuto). Este módulo agrega
**ElevenLabs** como motor alternativo, opcional: más voces, acentos
regionales reales y clonación de voz — a cambio de un costo real por
carácter sintetizado que Polly no tiene.

Se activa configurando `ELEVENLABS_API_KEY` (pestaña Configuración o
variable de entorno) — sin esa key, el sistema sigue usando Polly/Twilio
normalmente, no rompe nada.

Costeo: ElevenLabs cobra por carácter (1 carácter = 1 crédito en los
modelos estándar). `COSTO_POR_1000_CHARS_USD` es una referencia de mercado
(~US$0.17–0.20/1000 caracteres según el plan, julio 2026) — **verificar
contra el plan real contratado**, no es un precio garantizado ni cambia
solo. Sirve para que quien arma el precio del plan "Pro" sepa cuánto le
cuesta cada llamada con voz premium y no termine subsidiando al cliente.
"""
from __future__ import annotations

import os

COSTO_POR_1000_CHARS_USD = 0.18  # referencia de mercado, ver docstring — ajustar a tu plan real
MODELO_DEFAULT = "eleven_multilingual_v2"   # soporta español/inglés/portugués y más
# Para LLAMADAS en vivo usar el modelo flash: ~75 ms de inferencia (el
# multilingual v2 tarda cientos de ms por frase = "lag" audible en la
# conversación) y cuesta la mitad de créditos por carácter. Calidad apenas
# menor, imperceptible por teléfono (el audio va en 8 kHz igual).
MODELO_LLAMADAS = "eleven_flash_v2_5"
_BASE_URL = "https://api.elevenlabs.io/v1"


def costo_estimado_usd(texto: str, costo_por_1000: float = COSTO_POR_1000_CHARS_USD) -> float:
    """Costo aproximado en USD de sintetizar `texto` (por longitud, no por audio real)."""
    return round(len(texto or "") / 1000 * costo_por_1000, 6)


def api_key_configurada(api_key: str | None = None) -> str:
    key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
    return key if len(key) > 10 else ""


def voces_disponibles(api_key: str | None = None, timeout: int = 20) -> list[dict]:
    """Lista de voces habilitadas en la cuenta (id, nombre, idioma/etiquetas)."""
    import requests

    key = api_key_configurada(api_key)
    if not key:
        return []
    try:
        r = requests.get(f"{_BASE_URL}/voices", headers={"xi-api-key": key}, timeout=timeout)
        r.raise_for_status()
        return [{"voice_id": v.get("voice_id"), "nombre": v.get("name"),
                "etiquetas": v.get("labels", {})} for v in r.json().get("voices", [])]
    except Exception:
        return []


def sintetizar(texto: str, voice_id: str, api_key: str | None = None,
              modelo: str = MODELO_DEFAULT, estabilidad: float = 0.5,
              similaridad: float = 0.75, timeout: int = 30) -> dict:
    """
    Sintetiza `texto` con la voz `voice_id`. Devuelve
    {"ok": bool, "audio": bytes|None, "caracteres": int, "costo_est_usd": float,
     "error": str|None} — nunca levanta excepción (para no cortar una llamada
    en curso si ElevenLabs falla).
    """
    import requests

    caracteres = len(texto or "")
    costo = costo_estimado_usd(texto)
    key = api_key_configurada(api_key)
    if not key:
        return {"ok": False, "audio": None, "caracteres": caracteres,
                "costo_est_usd": 0.0, "error": "Falta ELEVENLABS_API_KEY."}
    if not texto or not voice_id:
        return {"ok": False, "audio": None, "caracteres": caracteres,
                "costo_est_usd": 0.0, "error": "Falta texto o voice_id."}
    try:
        r = requests.post(
            f"{_BASE_URL}/text-to-speech/{voice_id}",
            headers={"xi-api-key": key, "content-type": "application/json",
                     "accept": "audio/mpeg"},
            json={"text": texto, "model_id": modelo,
                  "voice_settings": {"stability": estabilidad, "similarity_boost": similaridad}},
            timeout=timeout,
        )
        r.raise_for_status()
        return {"ok": True, "audio": r.content, "caracteres": caracteres,
                "costo_est_usd": costo, "error": None}
    except Exception as e:
        return {"ok": False, "audio": None, "caracteres": caracteres,
                "costo_est_usd": 0.0, "error": str(e)[:300]}
