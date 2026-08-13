# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Cliente unificado de LLM (multi-proveedor)
=====================================================
Punto único donde el producto le habla a un modelo de lenguaje para razonar o
redactar (evaluación del Copiloto, respuestas del Asistente de ayuda,
redacción del Gestor IA, generación de SQL en consulta_bd.py). Antes esto
llamaba a la API de Anthropic hardcodeada por separado en cada uno de esos
cuatro archivos — ahora el cliente elige, en Configuración, con qué cuenta
corporativa propia quiere razonar (Claude, Gemini o ChatGPT/OpenAI), y cada
módulo sigue llamando a `generar()` sin saber cuál proveedor hay atrás.

Sobre "Copilot": GitHub Copilot no expone una API de completions para
integrar en un producto de terceros (es una herramienta embebida en editores
de código, no un servicio de chat que un banco pueda consumir). Si un
cliente dice tener "Copilot corporativo" para esto, probablemente se refiere
a Azure OpenAI o a ChatGPT Enterprise — ambos entran por la opción "openai"
de acá con su propia API key.

Además del proveedor, el cliente elige el **modelo** dentro de su cuenta —
así regula el consumo de tokens (un modelo chico para el volumen diario, uno
grande para lo que lo amerite). `actualizar_modelos()` consulta la API del
proveedor por su catálogo vigente (todos exponen un endpoint de listado) y
lo cachea, para que la lista para elegir tenga siempre las últimas versiones
sin tocar código.

Los modelos por default de Gemini/OpenAI/xAI son una referencia (verificar
contra la documentación vigente del proveedor antes de vender — igual
criterio que `kobra.voz_tts.COSTO_POR_1000_CHARS_USD`); Claude usa
"claude-sonnet-5", el mismo ya usado en el resto del producto. Todos son
ajustables sin tocar código vía `establecer_modelo()`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

from kobra import config as kconfig

_CLAVE_PROVEEDOR = "LLM_PROVEEDOR"
PROVEEDORES = ("anthropic", "gemini", "openai", "xai")
_DEFAULT = "anthropic"

_MODELOS_DEFAULT = {
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o",
    "xai": "grok-4",
}

KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
}

# Nombre comercial con el que el cliente conoce a cada proveedor (para UIs).
NOMBRES = {
    "anthropic": "Claude (Anthropic)",
    "gemini": "Gemini (Google)",
    "openai": "ChatGPT (OpenAI / Azure / Copilot corporativo)",
    "xai": "Grok (xAI)",
}


def proveedor_activo() -> str:
    p = kconfig.leer_extra(_CLAVE_PROVEEDOR, _DEFAULT)
    return p if p in PROVEEDORES else _DEFAULT


def establecer_proveedor(proveedor: str) -> None:
    if proveedor not in PROVEEDORES:
        raise ValueError(f"proveedor desconocido: {proveedor!r} (válidos: {PROVEEDORES})")
    kconfig.guardar_extra(_CLAVE_PROVEEDOR, proveedor)


def modelo_de(proveedor: str) -> str:
    return kconfig.leer_extra(f"LLM_MODELO_{proveedor.upper()}") or _MODELOS_DEFAULT[proveedor]


def establecer_modelo(proveedor: str, modelo: str) -> None:
    if proveedor not in PROVEEDORES:
        raise ValueError(f"proveedor desconocido: {proveedor!r} (válidos: {PROVEEDORES})")
    kconfig.guardar_extra(f"LLM_MODELO_{proveedor.upper()}", modelo)


def _clave(proveedor: str, api_key: str | None) -> str:
    return api_key or os.getenv(KEY_ENV[proveedor], "")


# ---------------------------------------------------------------------------
# Catálogo de modelos por proveedor — la lista para elegir en Configuración.
# El botón "Actualizar" llama a `actualizar_modelos()`, que consulta el
# endpoint de listado del proveedor (con la key del cliente) y cachea el
# resultado; `modelos_disponibles()` devuelve ese caché o el default.
# ---------------------------------------------------------------------------
def _clave_cache_modelos(proveedor: str) -> str:
    return f"LLM_MODELOS_{proveedor.upper()}"


def modelos_disponibles(proveedor: str) -> list[str]:
    """Modelos para ofrecer en el selector: el catálogo cacheado por la última
    actualización, o el default si nunca se actualizó. El modelo elegido
    actualmente se incluye siempre (aunque el proveedor ya no lo liste, para
    que el selector nunca muestre vacío lo que está en uso)."""
    if proveedor not in PROVEEDORES:
        raise ValueError(f"proveedor desconocido: {proveedor!r} (válidos: {PROVEEDORES})")
    crudo = kconfig.leer_extra(_clave_cache_modelos(proveedor))
    try:
        modelos = [m for m in json.loads(crudo) if isinstance(m, str) and m] if crudo else []
    except Exception:
        modelos = []
    if not modelos:
        modelos = [_MODELOS_DEFAULT[proveedor]]
    actual = modelo_de(proveedor)
    if actual not in modelos:
        modelos.insert(0, actual)
    return modelos


def fecha_actualizacion_modelos(proveedor: str) -> str | None:
    """ISO-8601 (UTC) de la última actualización exitosa del catálogo, o None."""
    return kconfig.leer_extra(f"{_clave_cache_modelos(proveedor)}_FECHA")


def actualizar_modelos(proveedor: str, api_key: str | None = None,
                       timeout: int = 30) -> dict:
    """Consulta a la API del proveedor por sus modelos vigentes y cachea la
    lista. Devuelve {"ok", "modelos", "detalle"} — nunca lanza: si falta la
    key o falla la llamada, ok=False con el motivo, y el caché anterior (si
    había) queda intacto."""
    if proveedor not in PROVEEDORES:
        raise ValueError(f"proveedor desconocido: {proveedor!r} (válidos: {PROVEEDORES})")
    key = _clave(proveedor, api_key)
    if len(key) < 10:
        return {"ok": False, "modelos": modelos_disponibles(proveedor),
                "detalle": f"Falta la API key de {proveedor} "
                           f"({KEY_ENV[proveedor]} en Configuración)."}
    listar = {"anthropic": _listar_anthropic, "gemini": _listar_gemini,
              "openai": _listar_openai, "xai": _listar_xai}[proveedor]
    try:
        modelos = listar(key, timeout)
    except Exception as e:
        return {"ok": False, "modelos": modelos_disponibles(proveedor),
                "detalle": f"No se pudo consultar el catálogo de {proveedor}: {e}"}
    if not modelos:
        return {"ok": False, "modelos": modelos_disponibles(proveedor),
                "detalle": f"El catálogo de {proveedor} vino vacío — se conserva la lista anterior."}
    kconfig.guardar_extra(_clave_cache_modelos(proveedor), json.dumps(modelos))
    kconfig.guardar_extra(f"{_clave_cache_modelos(proveedor)}_FECHA",
                          datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {"ok": True, "modelos": modelos_disponibles(proveedor),
            "detalle": f"{len(modelos)} modelos vigentes de {proveedor}."}


def _listar_anthropic(key: str, timeout: int) -> list[str]:
    r = requests.get("https://api.anthropic.com/v1/models?limit=100",
                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                     timeout=timeout)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", []) if m.get("id")]


def _listar_gemini(key: str, timeout: int) -> list[str]:
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                     headers={"x-goog-api-key": key}, timeout=timeout)
    r.raise_for_status()
    modelos = []
    for m in r.json().get("models", []):
        nombre = (m.get("name") or "").removeprefix("models/")
        # Solo los que generan texto (afuera embeddings, imagen, TTS, etc.).
        if nombre.startswith("gemini") and \
                "generateContent" in m.get("supportedGenerationMethods", []):
            modelos.append(nombre)
    return modelos


# El listado de OpenAI mezcla todo (embeddings, Whisper, TTS, DALL·E…) sin un
# campo de capacidad — se filtra por nombre a los modelos de chat.
_OPENAI_PREFIJOS_CHAT = ("gpt-", "o1", "o3", "o4", "chatgpt")
_OPENAI_EXCLUIR = ("embedding", "whisper", "tts", "audio", "realtime", "image",
                   "dall-e", "moderation", "transcribe", "search", "instruct")


def _listar_openai(key: str, timeout: int) -> list[str]:
    r = requests.get("https://api.openai.com/v1/models",
                     headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    r.raise_for_status()
    data = [m for m in r.json().get("data", []) if m.get("id")]
    data.sort(key=lambda m: m.get("created") or 0, reverse=True)
    return [m["id"] for m in data
            if m["id"].startswith(_OPENAI_PREFIJOS_CHAT)
            and not any(p in m["id"] for p in _OPENAI_EXCLUIR)]


def _listar_xai(key: str, timeout: int) -> list[str]:
    r = requests.get("https://api.x.ai/v1/models",
                     headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", []) if m.get("id")]


def disponible(proveedor: str | None = None, api_key: str | None = None) -> bool:
    """True si hay una API key configurada (propia del cliente) para el
    proveedor activo — los llamadores la usan para decidir si degradar a
    plantillas/documentación cruda en vez de llamar a la IA."""
    proveedor = proveedor or proveedor_activo()
    return len(_clave(proveedor, api_key)) >= 10


def generar(prompt: str, system: str | None = None, max_tokens: int = 600,
           proveedor: str | None = None, api_key: str | None = None,
           timeout: int = 60, lanzar: bool = False) -> str | None:
    """
    Genera texto con el proveedor configurado (o el que se pase explícito).
    Por default nunca lanza — devuelve None si falta la key o si la llamada
    falla, y el llamador decide el fallback (plantillas, documentación cruda,
    etc.). `lanzar=True` deja pasar la excepción tal cual (para el caso de
    consulta_bd.py, donde antes no había fallback y se prefiere mantenerlo).
    """
    proveedor = proveedor or proveedor_activo()
    key = _clave(proveedor, api_key)
    if len(key) < 10:
        if lanzar:
            raise RuntimeError(
                f"Falta la API key de {proveedor} (Configuración o variable de entorno).")
        return None
    generador = {"anthropic": _generar_anthropic, "gemini": _generar_gemini,
                "openai": _generar_openai, "xai": _generar_xai}[proveedor]
    if lanzar:
        return generador(prompt, system, max_tokens, key, timeout)
    try:
        return generador(prompt, system, max_tokens, key, timeout)
    except Exception:
        return None


def _generar_anthropic(prompt: str, system: str | None, max_tokens: int,
                       key: str, timeout: int) -> str:
    body = {"model": modelo_de("anthropic"), "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def _generar_gemini(prompt: str, system: str | None, max_tokens: int,
                    key: str, timeout: int) -> str:
    modelo = modelo_de("gemini")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
        headers={"content-type": "application/json", "x-goog-api-key": key},
        json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _generar_openai(prompt: str, system: str | None, max_tokens: int,
                    key: str, timeout: int) -> str:
    mensajes = ([{"role": "system", "content": system}] if system else [])
    mensajes.append({"role": "user", "content": prompt})
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": modelo_de("openai"), "max_tokens": max_tokens,
              "messages": mensajes}, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _generar_xai(prompt: str, system: str | None, max_tokens: int,
                 key: str, timeout: int) -> str:
    # xAI expone una API compatible con el chat/completions de OpenAI.
    mensajes = ([{"role": "system", "content": system}] if system else [])
    mensajes.append({"role": "user", "content": prompt})
    r = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": modelo_de("xai"), "max_tokens": max_tokens,
              "messages": mensajes}, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()
