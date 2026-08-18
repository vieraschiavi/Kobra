# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Licencias firmadas (JWT) — Edición Venta
=================================================
Implementación real de la sección 2 de `docs/BACKEND_VENTA.md` (que hasta
ahora era solo un esbozo de diseño). Emite y valida tokens JWT (HS256)
atados a plan, cupo mensual y features habilitadas.

El secreto de firma se persiste con el mismo backend seguro que las demás
claves de MV Kobra AI (`kobra/config.py`: keyring del SO > archivo cifrado > texto
plano) — se genera solo la primera vez que hace falta, y no se hardcodea
en ningún lado. También se puede fijar explícitamente con la variable de
entorno `KOBRA_LICENSE_SECRET` (recomendado en producción, para poder
rotarlo sin depender del archivo local).
"""
from __future__ import annotations

import os
import secrets
import time

import jwt

from backend_venta import licencia_clave as kclave
from kobra import config as kconfig

_CLAVE_SECRETO = "LICENSE_SECRET"

# Nota sobre "voz_premium" (ElevenLabs, ver backend_venta/app.py::gateway_tts):
# a propósito NO está en ningún plan de acá abajo. A diferencia de "voz"
# (Twilio/Polly, costo marginal ~nulo), voz_premium cobra por carácter — si
# se pusiera por default en un plan de precio fijo, cada uso real le resta
# margen al plan sin que se haya cotizado. Se habilita explícitamente por
# cliente: emitir_licencia(cliente_id, plan, features=[*PLANES[plan]["features"], "voz_premium"]).
PLANES = {
    "trial":      {"cupo_mensual": 50,   "precio": 0.0,   "dias": 3,
                   "features": ["voz", "whatsapp", "copiloto", "erp"]},
    "basico":     {"cupo_mensual": 300,  "precio": 99.0,  "dias": 30,
                   "features": ["voz", "whatsapp", "copiloto", "erp"]},
    # Starter no lleva tope de gestiones A PROPÓSITO. Es el plan "traé tus
    # propias APIs" (US$690 de licencia + soporte): el consumo lo paga el
    # cliente en su propia cuenta de OpenAI/Twilio, así que un cupo nuestro no
    # cubre ningún costo — solo le sacaría producto sin razón. Tenía 200, un
    # número que nunca se aplicó porque hasta ahora la app instalada ignoraba
    # el cupo; el día que se empezó a aplicar (kobra/plan.py) ese 200 dejaba a
    # un cliente de US$690 con MENOS gestiones que uno de US$99. La landing
    # nunca vendió un tope para este plan.
    "starter":    {"cupo_mensual": None, "precio": 690.0, "dias": 365,
                   "features": ["voz", "whatsapp", "copiloto", "erp"]},
    "pro":        {"cupo_mensual": 1000, "precio": 349.0, "dias": 30,
                   "features": ["voz", "whatsapp", "copiloto", "erp", "excedente"]},
    "enterprise": {"cupo_mensual": None, "precio": None,  "dias": 30,
                   "features": ["voz", "whatsapp", "copiloto", "erp", "excedente", "white_label", "sso"]},
}


def secreto_firma() -> str:
    """Secreto HS256 activo: env var > guardado > generado una sola vez."""
    s = os.environ.get("KOBRA_LICENSE_SECRET")
    if s:
        return s
    s = kconfig.leer_extra(_CLAVE_SECRETO)
    if s:
        return s
    s = secrets.token_hex(32)
    kconfig.guardar_extra(_CLAVE_SECRETO, s)
    return s


def plan_permite_excedente(plan: str) -> bool:
    return "excedente" in PLANES.get(plan, {}).get("features", [])


def emitir_licencia(cliente_id: str, plan: str, edicion: str = "venta",
                    cupo_mensual: int | None = None, features: list[str] | None = None,
                    dias: int | None = None, secreto: str | None = None) -> str:
    """
    Emite un JWT de licencia. Si `cupo_mensual`/`features`/`dias` no se pasan,
    se toman del plan (`PLANES`). `plan="enterprise"` sin cupo explícito
    significa "sin tope" — lo valida el gateway, no la librería.
    """
    if plan not in PLANES:
        raise ValueError(f"plan desconocido: {plan!r} (válidos: {list(PLANES)})")
    cfg = PLANES[plan]
    cupo = cupo_mensual if cupo_mensual is not None else cfg["cupo_mensual"]
    feats = features if features is not None else cfg["features"]
    dias_val = dias if dias is not None else cfg["dias"]
    ahora = int(time.time())
    payload = {
        "sub": cliente_id, "plan": plan, "edition": edicion,
        "cupo_mensual": cupo, "features": feats,
        "iat": ahora, "exp": ahora + dias_val * 24 * 3600,
    }
    privada = os.environ.get("KOBRA_LICENSE_PRIVATE_KEY")
    if privada and secreto is None:
        # Camino de venta: firma asimétrica, verificable por cualquier copia
        # instalada sin repartir ningún secreto. Ver licencia_clave.py.
        return jwt.encode(payload, privada, algorithm=kclave.ALGORITMO)
    return jwt.encode(payload, secreto or secreto_firma(), algorithm="HS256")


def validar_licencia(token: str, secreto: str | None = None) -> dict:
    """Decodifica y valida la licencia. Lanza jwt.PyJWTError si es inválida/expirada.

    Acepta las dos firmas, y el orden importa:

    * **RS256** — las licencias compradas. Se verifican con la clave pública
      que viaja en el propio programa (`licencia_clave.PUBLICA`), así que
      funcionan en cualquier instalación sin configurar nada. Este era el
      agujero: el instalador de clientes no recibía el secreto HS256 del
      servidor, cada máquina generaba el suyo al azar, y una licencia
      perfectamente válida moría con `Signature verification failed`.
    * **HS256** — el camino hosted (mismo proceso emite y valida) y los tests.

    Se prueba primero la asimétrica salvo que el llamador pase un secreto
    explícito, que es la forma de decir "quiero el camino simétrico".
    """
    if secreto is None:
        try:
            return jwt.decode(token, kclave.PUBLICA, algorithms=[kclave.ALGORITMO])
        except jwt.ExpiredSignatureError:
            raise                      # firmada por nosotros, pero vencida
        except jwt.PyJWTError:
            pass                       # no es RS256 nuestra: probar HS256
    return jwt.decode(token, secreto or secreto_firma(), algorithms=["HS256"])


def licencia_activa(token: str, secreto: str | None = None) -> dict:
    """Igual que validar_licencia, pero devuelve un dict con {ok, error, claims}
    en vez de lanzar — más cómodo para endpoints HTTP."""
    try:
        claims = validar_licencia(token, secreto)
        return {"ok": True, "claims": claims, "error": None}
    except jwt.ExpiredSignatureError:
        return {"ok": False, "claims": None, "error": "licencia_expirada"}
    except jwt.PyJWTError as e:
        return {"ok": False, "claims": None, "error": f"licencia_invalida: {e}"}
