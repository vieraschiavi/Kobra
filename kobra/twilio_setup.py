"""
MV Kobra AI · Auto-configuración de Twilio (buscar/comprar número + webhook)
=============================================================================
Automatiza, vía la API de Twilio, los pasos que hoy el comprador hace a mano
en la Console (ver `docs/GUIA_LLAMADA_REAL_TWILIO.md`): buscar un número
disponible, comprarlo, y apuntar su webhook de voz a `/voz/entrante` — con
las credenciales que el propio cliente ya cargó en Configuración, sin que
tenga que volver a entrar a la Console de Twilio para nada de esto.

Lo que esto NO automatiza (por ser procesos externos a la API de Twilio, no
un paso de configuración): la aprobación de la plantilla de WhatsApp por
Meta, y la creación de la contraseña de aplicación del email corporativo
del cliente — esos siguen requiriendo una acción suya fuera de MV Kobra AI.
"""
from __future__ import annotations

import os

import requests

_BASE = "https://api.twilio.com/2010-04-01/Accounts/{sid}"


def _credenciales(sid: str | None, token: str | None) -> tuple[str | None, str | None]:
    return sid or os.getenv("TWILIO_ACCOUNT_SID"), token or os.getenv("TWILIO_AUTH_TOKEN")


def buscar_numeros_disponibles(pais: str = "UY", sid: str | None = None,
                               token: str | None = None, limite: int = 10,
                               timeout: int = 20) -> dict:
    """
    Busca números de Twilio disponibles para comprar, habilitados para voz,
    en el país indicado (código ISO de 2 letras — ej. "UY", "AR", "US").
    Devuelve {"ok": bool, "numeros": [{"numero", "region", "localidad"}, ...],
    "detalle": str|None}.
    """
    sid, token = _credenciales(sid, token)
    if not (sid and token):
        return {"ok": False, "numeros": [],
                "detalle": "Faltan credenciales de Twilio (Account SID / Auth Token)."}

    url = _BASE.format(sid=sid) + f"/AvailablePhoneNumbers/{pais}/Local.json"
    try:
        resp = requests.get(url, params={"VoiceEnabled": "true", "PageSize": limite},
                           auth=(sid, token), timeout=timeout)
        if resp.status_code != 200:
            return {"ok": False, "numeros": [], "detalle": resp.text[:400]}
        datos = resp.json().get("available_phone_numbers", [])
        numeros = [{"numero": d.get("phone_number"), "region": d.get("region"),
                   "localidad": d.get("locality")} for d in datos]
        return {"ok": True, "numeros": numeros, "detalle": None}
    except Exception as e:
        return {"ok": False, "numeros": [], "detalle": str(e)[:300]}


def comprar_numero(numero: str, voice_url: str, sid: str | None = None,
                   token: str | None = None, timeout: int = 20) -> dict:
    """
    Compra el número indicado (formato E.164, ej. +59890000000) y configura
    su webhook de voz entrante en el mismo paso. Tiene costo real — verificá
    la tarifa vigente antes de confirmar (el llamador es responsable de
    mostrar esa advertencia antes de invocar esto).
    """
    sid, token = _credenciales(sid, token)
    if not (sid and token):
        return {"ok": False, "detalle": "Faltan credenciales de Twilio (Account SID / Auth Token)."}
    if not numero:
        return {"ok": False, "detalle": "Falta el número a comprar."}

    url = _BASE.format(sid=sid) + "/IncomingPhoneNumbers.json"
    try:
        resp = requests.post(url, data={"PhoneNumber": numero, "VoiceUrl": voice_url,
                                        "VoiceMethod": "POST"},
                           auth=(sid, token), timeout=timeout)
        ok = resp.status_code in (200, 201)
        cuerpo = resp.json() if ok else {}
        return {"ok": ok, "sid": cuerpo.get("sid"), "numero": cuerpo.get("phone_number"),
                "detalle": None if ok else resp.text[:400]}
    except Exception as e:
        return {"ok": False, "detalle": str(e)[:300]}


def configurar_webhook_numero(numero: str, voice_url: str, sid: str | None = None,
                              token: str | None = None, timeout: int = 20) -> dict:
    """
    Para un número que el cliente YA tenía (comprado antes, a mano o desde
    otro sistema): lo busca por su número E.164 dentro de la cuenta y le
    apunta el webhook de voz a `voice_url`, sin tocar la Console de Twilio.
    """
    sid, token = _credenciales(sid, token)
    if not (sid and token):
        return {"ok": False, "detalle": "Faltan credenciales de Twilio (Account SID / Auth Token)."}

    base = _BASE.format(sid=sid)
    try:
        resp = requests.get(base + "/IncomingPhoneNumbers.json", params={"PhoneNumber": numero},
                           auth=(sid, token), timeout=timeout)
        if resp.status_code != 200:
            return {"ok": False, "detalle": resp.text[:400]}
        encontrados = resp.json().get("incoming_phone_numbers", [])
        if not encontrados:
            return {"ok": False, "detalle": f"No se encontró el número {numero} en esta cuenta de Twilio."}
        numero_sid = encontrados[0]["sid"]

        resp2 = requests.post(base + f"/IncomingPhoneNumbers/{numero_sid}.json",
                             data={"VoiceUrl": voice_url, "VoiceMethod": "POST"},
                             auth=(sid, token), timeout=timeout)
        ok = resp2.status_code in (200, 201)
        return {"ok": ok, "detalle": None if ok else resp2.text[:400]}
    except Exception as e:
        return {"ok": False, "detalle": str(e)[:300]}
