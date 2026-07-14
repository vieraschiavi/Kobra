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

Los modelos por default de Gemini/OpenAI son una referencia (verificar
contra la documentación vigente del proveedor antes de vender — igual
criterio que `kobra.voz_tts.COSTO_POR_1000_CHARS_USD`); Claude usa
"claude-sonnet-5", el mismo ya usado en el resto del producto. Todos son
ajustables sin tocar código vía `establecer_modelo()`.
"""
from __future__ import annotations

import os

import requests

from kobra import config as kconfig

_CLAVE_PROVEEDOR = "LLM_PROVEEDOR"
PROVEEDORES = ("anthropic", "gemini", "openai")
_DEFAULT = "anthropic"

_MODELOS_DEFAULT = {
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o",
}

_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
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
    return api_key or os.getenv(_KEY_ENV[proveedor], "")


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
                "openai": _generar_openai}[proveedor]
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
