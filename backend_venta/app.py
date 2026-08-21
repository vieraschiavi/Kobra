# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Backend de venta — FastAPI (Edición Venta)
=====================================================
Implementación real de `docs/BACKEND_VENTA.md` (que hasta ahora era solo
diseño/esbozo): licencias JWT, gateway de APIs medido y webhook de pago +
descarga. Corre local para desarrollo/pruebas:

    uvicorn backend_venta.app:app --reload --port 8100

Lo que **falta para producción** (a propósito, no es código que se pueda
inventar):
  - Desplegarlo en un servidor real (Render/Fly/EC2/lo que uses).
  - Conectar el webhook de MercadoPago a la URL pública de este servicio.
  - Cargar `ANTHROPIC_API_KEY` / `MP_ACCESS_TOKEN` reales como secretos del
    servidor (nunca en el repo).
  - Publicar el instalador real en `KOBRA_INSTALADOR_PATH` (o adaptar
    `/descargar/{token}` a S3/Blob storage si se prefiere).
  - `/gateway/tts`, `/gateway/twilio` y `/gateway/whatsapp` quedan como
    endpoints con el circuito de licencia+cupo+medición ya armado, pero SIN
    proveedor real conectado todavía (devuelven 501) — conectar Twilio/TTS/
    WhatsApp reales es trabajo de integración específico, no algo que
    convenga fabricar sin poder probarlo contra la cuenta real del cliente.
"""
from __future__ import annotations

import os
import secrets

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from backend_venta import descargas, licencias, uso
from kobra import auditoria as kauditoria
from kobra import config as kconfig
from kobra import limitador as klimite

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="MV Kobra AI · Backend de venta", version="1.0.0")
# Red de seguridad general: `requerir_licencia`/`requerir_admin` no tenían
# ningún freno de intentos —a diferencia del login de webapp/backend/api.py—,
# así que se podía tantear el token Bearer sin límite. Esto cubre eso y todo
# el resto (webhook de MercadoPago, gateways medidos) de una sola vez.
app.add_middleware(klimite.LimitadorGeneral)


# ---------------------------------------------------------------------------
# Autenticación de licencia (clientes finales) y de admin (vos)
# ---------------------------------------------------------------------------
def requerir_licencia(authorization: str = Header(...)) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    r = licencias.licencia_activa(token)
    if not r["ok"]:
        raise HTTPException(401, r["error"])
    return r["claims"]


def _admin_token() -> str:
    t = os.environ.get("KOBRA_BACKEND_ADMIN_TOKEN") or kconfig.leer_extra("BACKEND_ADMIN_TOKEN")
    if not t:
        t = secrets.token_hex(24)
        kconfig.guardar_extra("BACKEND_ADMIN_TOKEN", t)
        print(f"[backend_venta] Token de admin generado (guardalo, no se vuelve a mostrar): {t}")
    return t


def requerir_admin(authorization: str = Header(...)) -> None:
    recibido = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(recibido, _admin_token()):
        raise HTTPException(403, "no autorizado")


def _chequear_cupo(claims: dict) -> None:
    cupo = claims.get("cupo_mensual")
    if cupo is None:
        return  # enterprise / sin tope
    usados = uso.gestiones_mes(claims["sub"])
    if usados >= cupo and not licencias.plan_permite_excedente(claims.get("plan", "")):
        raise HTTPException(402, "Cupo mensual agotado para este plan.")


# ---------------------------------------------------------------------------
# 1) Licencias
# ---------------------------------------------------------------------------
@app.post("/licencias/emitir")
async def emitir(payload: dict, _admin: None = Depends(requerir_admin)):
    """Emisión manual (PoC, venta directa, soporte) — no pasa por MercadoPago."""
    cliente_id = str(payload.get("cliente_id") or "").strip()
    plan = str(payload.get("plan") or "starter")
    if not cliente_id:
        raise HTTPException(400, "falta 'cliente_id'")
    if plan not in licencias.PLANES:
        raise HTTPException(400, f"plan inválido: {plan!r}")
    lic = licencias.emitir_licencia(cliente_id, plan)
    kauditoria.registrar("licencia_emitida_manual", {"cliente": cliente_id, "plan": plan})
    return {"licencia": lic, "plan": plan}


@app.get("/licencias/estado")
async def estado(claims: dict = Depends(requerir_licencia)):
    u = uso.uso_mes(claims["sub"])
    return {
        "cliente": claims["sub"], "plan": claims["plan"], "edicion": claims.get("edition"),
        "cupo_mensual": claims.get("cupo_mensual"), "usado_este_mes": u["gestiones"],
        "features": claims.get("features", []), "expira": claims["exp"],
    }


# ---------------------------------------------------------------------------
# 2) Gateway de APIs (medido)
# ---------------------------------------------------------------------------
_PROMPT_COPILOTO = (
    "Sos un copiloto experto en cobranzas para un gestor humano. Analizá la "
    "siguiente conversación con un deudor y devolvé ÚNICAMENTE un objeto JSON "
    "válido (sin texto alrededor, sin markdown) con estas claves:\n"
    '{"sentimiento":"Positivo|Neutro|Negativo","temperatura":<0-100, disposición '
    'del cliente a pagar>,"tecnicas":[<técnicas de negociación, 2 a 4 strings '
    'cortos>],"proxima_jugada":"<qué debería hacer el gestor ahora, 1 frase>",'
    '"guion":"<exactamente qué decir ahora, 1-2 frases, tono profesional, '
    'español neutro, SIN modismos>"}\n\n'
    "Respetá la ley (no amenazar, no hostigar). Conversación:\n\"\"\"\n{texto}\n\"\"\""
)


@app.post("/gateway/claude")
async def gateway_claude(payload: dict, claims: dict = Depends(requerir_licencia)):
    if "copiloto" not in claims.get("features", []):
        raise HTTPException(403, "el plan no incluye el Copiloto IA")

    texto = str(payload.get("texto", ""))[:4000].strip()
    if not texto:
        raise HTTPException(400, "falta 'texto'")

    key = os.environ.get("ANTHROPIC_API_KEY") or kconfig.leer_extra("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(503, "ANTHROPIC_API_KEY no configurada en el servidor del gateway")

    # Chequear cupo + llamar al proveedor + registrar el uso, bajo un lock
    # por cliente: sin esto, dos pedidos concurrentes del mismo cliente
    # pueden pasar el chequeo de cupo antes de que ninguno registre uso
    # (ver docstring de uso.lock_cliente).
    with uso.lock_cliente(claims["sub"]):
        _chequear_cupo(claims)
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5", "max_tokens": 500,
                      "messages": [{"role": "user", "content": _PROMPT_COPILOTO.format(texto=texto)}]},
                timeout=30,
            )
            data = r.json()
            if not r.ok:
                raise HTTPException(502, (data.get("error") or {}).get("message", "error de Anthropic"))
            usage = data.get("usage", {})
            uso.registrar_uso(claims["sub"], canal="claude", gestion_id=payload.get("gestion_id"),
                              tok_in=usage.get("input_tokens", 0), tok_out=usage.get("output_tokens", 0))
            texto_resp = (data.get("content") or [{}])[0].get("text", "")
            return {"ok": True, "raw": texto_resp}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"error llamando a Claude: {e}") from e


@app.post("/gateway/tts")
async def gateway_tts(payload: dict, claims: dict = Depends(requerir_licencia)):
    """
    Voz premium (ElevenLabs) medida por carácter — a diferencia de la voz
    básica (Twilio/Polly, incluida en "voz"), esta SÍ tiene costo real por
    uso. Por eso exige la feature "voz_premium" aparte: se habilita
    explícitamente por cliente (`emitir_licencia(..., features=[...])`),
    no viene incluida por default en ningún plan — así el precio del plan
    no termina subsidiando un costo variable que no cotizó.
    """
    if "voz_premium" not in claims.get("features", []):
        raise HTTPException(403, "el plan no incluye voz premium (ElevenLabs)")

    texto = str(payload.get("texto", ""))[:2000].strip()
    voice_id = str(payload.get("voice_id", "")).strip()
    if not texto or not voice_id:
        raise HTTPException(400, "faltan 'texto' o 'voice_id'")

    key = os.environ.get("ELEVENLABS_API_KEY") or kconfig.leer_extra("ELEVENLABS_API_KEY")
    if not key:
        raise HTTPException(503, "ELEVENLABS_API_KEY no configurada en el servidor del gateway")

    import base64

    from kobra import voz_tts

    with uso.lock_cliente(claims["sub"]):
        _chequear_cupo(claims)
        r = voz_tts.sintetizar(texto, voice_id, api_key=key)
        if not r["ok"]:
            raise HTTPException(502, f"error llamando a ElevenLabs: {r['error']}")
        uso.registrar_uso(claims["sub"], canal="tts_elevenlabs", gestion_id=payload.get("gestion_id"),
                          unidades=r["caracteres"], costo_est=r["costo_est_usd"])
        return {"ok": True, "audio_b64": base64.b64encode(r["audio"]).decode("ascii"),
                "caracteres": r["caracteres"], "costo_est_usd": r["costo_est_usd"]}


@app.post("/gateway/twilio")
async def gateway_twilio(payload: dict, claims: dict = Depends(requerir_licencia)):
    if "voz" not in claims.get("features", []):
        raise HTTPException(403, "el plan no incluye llamadas de voz")
    _chequear_cupo(claims)
    raise HTTPException(501, "Gateway de Twilio: circuito de licencia/cupo listo, falta conectar "
                             "las credenciales reales del cliente o las tuyas de reventa — ver "
                             "realtime/server.py para la lógica de llamada ya probada.")


@app.post("/gateway/whatsapp")
async def gateway_whatsapp(payload: dict, claims: dict = Depends(requerir_licencia)):
    if "whatsapp" not in claims.get("features", []):
        raise HTTPException(403, "el plan no incluye WhatsApp")
    _chequear_cupo(claims)
    raise HTTPException(501, "Gateway de WhatsApp: circuito de licencia/cupo listo, falta conectar "
                             "la API de WhatsApp Business real — ver docstring del módulo.")


# ---------------------------------------------------------------------------
# 3) Webhook de pago (MercadoPago) + descarga post-pago
# ---------------------------------------------------------------------------
_ESQUEMA_PAGOS = """
CREATE TABLE IF NOT EXISTS pagos_procesados (
    payment_id TEXT PRIMARY KEY,
    procesado  TEXT NOT NULL
)
"""


def _conn_pagos():
    import sqlite3

    from backend_venta.uso import DB_PATH
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_ESQUEMA_PAGOS)
    return conn


def _ya_procesado(payment_id) -> bool:
    conn = _conn_pagos()
    try:
        fila = conn.execute("SELECT 1 FROM pagos_procesados WHERE payment_id = ?",
                            (str(payment_id),)).fetchone()
        return fila is not None
    finally:
        conn.close()


def _marcar_procesado(payment_id) -> None:
    from datetime import datetime, timezone
    conn = _conn_pagos()
    try:
        # `OR IGNORE`: si dos avisos del mismo pago entran a la vez, el segundo
        # no explota con UNIQUE — simplemente no agrega nada.
        conn.execute("INSERT OR IGNORE INTO pagos_procesados (payment_id, procesado) VALUES (?,?)",
                     (str(payment_id), datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def _enviar_licencia(destino: str, plan: str, payment_id, licencia: str,
                     token_descarga: str) -> bool:
    """Manda la licencia por mail. Devuelve si salió.

    El endpoint que llama a esto es público y no lleva firma, así que la
    licencia NO puede volver en el cuerpo de la respuesta: la recibiría quien
    hizo el POST, que no es necesariamente el comprador.
    """
    clave = os.environ.get("RESEND_API_KEY")
    if not clave or "@" not in (destino or ""):
        return False
    cuerpo = (
        "¡Gracias por tu compra!\n\n"
        f"Tu licencia de MV Kobra AI (plan {plan}):\n\n{licencia}\n\n"
        "Cómo activarla: abrí MV Kobra AI y pegala en la pantalla de activación.\n"
        f"Token de descarga: {token_descarga}\n\n"
        f"Nº de operación: {payment_id}\n"
    )
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {clave}",
                     "Content-Type": "application/json"},
            json={"from": os.environ.get("RESEND_FROM", "onboarding@resend.dev"),
                  "to": destino,
                  "subject": f"Tu licencia de MV Kobra AI (plan {plan})",
                  "text": cuerpo},
            timeout=15)
        return r.ok
    except requests.RequestException:
        return False


@app.post("/webhooks/mercadopago")
async def webhook_mercadopago(payload: dict):
    """
    Mismo criterio de seguridad que `api/verify-payment.js`: nunca confiar en
    el cuerpo del webhook a ciegas — se vuelve a consultar el pago contra la
    API real de MercadoPago con el Access Token del servidor.
    """
    if payload.get("type") != "payment":
        return {"ok": True, "ignorado": True}

    payment_id = (payload.get("data") or {}).get("id")
    token = os.environ.get("MP_ACCESS_TOKEN")
    if not payment_id:
        raise HTTPException(400, "falta data.id en el webhook")
    if not token:
        raise HTTPException(503, "MP_ACCESS_TOKEN no configurado en el servidor")

    r = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    if not r.ok:
        raise HTTPException(502, "no se pudo verificar el pago contra MercadoPago")
    pago = r.json()
    if pago.get("status") != "approved":
        return {"ok": True, "estado": pago.get("status")}

    md = pago.get("metadata") or {}
    cliente_id = md.get("email") or md.get("cliente_id") or str(payment_id)

    # El plan sale de la metadata de NUESTRA preferencia. Si no es uno que
    # sepamos emitir, se avisa y se resuelve a mano.
    #
    # Antes esto caía a `starter` por defecto, y eso regalaba producto en dos
    # direcciones a la vez: un pago de Logística (US$79) no está en `PLANES`
    # —vive en `MODULOS_VENTA`— así que terminaba emitiendo Starter (US$690,
    # 365 días, con gobernanza y dax), y un pago sin metadata hacía lo mismo
    # por cualquier monto. El lado Node ya hacía lo correcto
    # (`api/_license.js`: "plan desconocido" y no emite); este era el que
    # regalaba.
    plan = md.get("plan")
    if plan in licencias.PLANES:
        emitir = lambda: licencias.emitir_licencia(cliente_id, plan)  # noqa: E731
    elif plan in licencias.MODULOS_VENTA:
        emitir = lambda: licencias.emitir_modulo(cliente_id, plan)    # noqa: E731
    else:
        kauditoria.registrar("pago_sin_plan_licenciable",
                             {"payment_id": payment_id, "plan": plan,
                              "cliente": cliente_id})
        return {"ok": True, "licencia": False, "motivo": "plan_no_licenciable"}

    # MercadoPago reintenta el aviso: sin esto, un mismo pago emitía una
    # licencia nueva (con otro vencimiento) y otro token de descarga en cada
    # reintento.
    if _ya_procesado(payment_id):
        return {"ok": True, "licencia": True, "repetido": True}

    lic = emitir()
    token_descarga = descargas.crear_token_descarga(cliente_id)
    _marcar_procesado(payment_id)
    kauditoria.registrar("licencia_emitida_pago", {"cliente": cliente_id, "plan": plan,
                                                    "payment_id": payment_id})
    enviada = _enviar_licencia(cliente_id, plan, payment_id, lic, token_descarga)
    if not enviada:
        # La licencia no se pierde: queda en el log del servicio para
        # reenviarla a mano. Lo que NO puede pasar es devolverla en el cuerpo
        # de la respuesta — este endpoint es público y no lleva firma, así que
        # el que recibe la respuesta es quien hizo el POST, no el comprador.
        print(f"[venta] licencia emitida y NO enviada — recuperar de acá. "
              f"payment_id={payment_id} plan={plan} cliente={cliente_id} "
              f"licencia={lic}", flush=True)
    return {"ok": True, "licencia": True, "enviada": enviada}


@app.get("/descargar/{token}")
async def descargar(token: str):
    r = descargas.validar_token_descarga(token)
    if not r["ok"]:
        raise HTTPException(403, r["error"])
    ruta = os.environ.get("KOBRA_INSTALADOR_PATH", os.path.join(ROOT, "dist", "MVKobraAI_Setup.exe"))
    if not os.path.exists(ruta):
        raise HTTPException(503, "El instalador todavía no está publicado en este servidor "
                                 "(configurá KOBRA_INSTALADOR_PATH).")
    return FileResponse(ruta, filename=os.path.basename(ruta))


@app.get("/salud")
async def salud():
    return {"ok": True, "servicio": "backend_venta"}
