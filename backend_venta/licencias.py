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

# --------------------------------------------------------------------------
# Módulos de la suite: lo que hace que el precio sea escalable
# --------------------------------------------------------------------------
# Kobra deja de ser un producto único y pasa a ser una suite. Sobre el núcleo
# de cobranzas se enchufan tres módulos que se venden por separado, y de cuáles
# incluye cada plan sale la escalera de precios.
#
#   gobernanza — catálogo, linaje, calidad, PII y RBAC sobre los datos.
#   dax        — medidas calculadas: el cliente define sus propios KPIs.
#   automl     — el cliente entrena un modelo con su propio dataset.
#   logistica  — stock, reposición, ofertas y precios (motor de Plania).
#   proyectos  — salud de portafolio y backlog priorizado (motor de MV PM).
#
# Los dos últimos NO son de cobranzas, y por eso se venden sueltos y no entran
# en ningún plan: un distribuidor que quiere planificar reparto no tiene por
# qué pagar el motor de cobranzas para llegar a ellos. Kobra pasa a ser la
# plataforma; el rubro lo elige el cliente comprando el módulo que le sirve.
#
# Se listan acá y no sueltos en cada plan para que agregar un módulo nuevo sea
# un solo lugar, y para que se pueda distinguir un módulo de la suite de una
# capacidad del núcleo (`voz`, `whatsapp`) al armar el mensaje de "tu plan no
# incluye esto". Lo cuida tests/test_modulos_suite.py.
MODULOS = ("gobernanza", "dax", "automl", "logistica", "proyectos")

# Módulos que se venden SOLO sueltos: no entran en ningún plan por más caro
# que sea, porque resuelven otro rubro. Lo cuida tests/test_modulos_suite.py.
MODULOS_SUELTOS = ("logistica", "proyectos")

# Catálogo de venta de esos módulos. Es una línea de producto APARTE de
# `PLANES`, no una fila más de la misma tabla, y la diferencia importa:
#
#   * Los planes forman una escalera donde pagar más nunca puede dar menos
#     (lo verifica tests/test_plan_diferenciado.py). Logística cuesta US$79 y
#     Básico US$99: si estuvieran en la misma tabla, esa regla diría que
#     Básico tiene que incluir todo lo de Logística, y no tiene sentido —
#     resuelven problemas distintos, no son dos escalones del mismo.
#   * Un comprador de Logística no está comprando "menos Kobra": está
#     comprando otro producto que corre en la misma plataforma.
#
# `cupo_mensual: 0` porque estas licencias no habilitan gestiones de cobranza.
# No es un castigo: es que no compraron eso.
MODULOS_VENTA = {
    "logistica": {"precio": 79.0, "dias": 30, "feature": "logistica",
                  "nombre": "Logística y reposición"},
    "proyectos": {"precio": 69.0, "dias": 30, "feature": "proyectos",
                  "nombre": "Proyectos"},
}

# Capacidades del núcleo de cobranzas: van en todos los planes, incluido el
# trial. Son lo que Kobra ya hacía antes de la suite.
_NUCLEO = ["voz", "whatsapp", "copiloto", "erp"]

PLANES = {
    "trial":      {"cupo_mensual": 50,   "precio": 0.0,   "dias": 7,
                   "features": [*_NUCLEO]},
    "basico":     {"cupo_mensual": 300,  "precio": 99.0,  "dias": 30,
                   "features": [*_NUCLEO]},
    # Starter no lleva tope de gestiones A PROPÓSITO. Es el plan "traé tus
    # propias APIs" (US$690 de licencia + soporte): el consumo lo paga el
    # cliente en su propia cuenta de OpenAI/Twilio, así que un cupo nuestro no
    # cubre ningún costo — solo le sacaría producto sin razón. Tenía 200, un
    # número que nunca se aplicó porque hasta ahora la app instalada ignoraba
    # el cupo; el día que se empezó a aplicar (kobra/plan.py) ese 200 dejaba a
    # un cliente de US$690 con MENOS gestiones que uno de US$99. La landing
    # nunca vendió un tope para este plan.
    "starter":    {"cupo_mensual": None, "precio": 690.0, "dias": 365,
                   "features": [*_NUCLEO, "gobernanza", "dax"]},
    "pro":        {"cupo_mensual": 1000, "precio": 349.0, "dias": 30,
                   "features": [*_NUCLEO, "excedente", "gobernanza"]},
    "enterprise": {"cupo_mensual": None, "precio": None,  "dias": 30,
                   "features": [*_NUCLEO, "excedente", "white_label", "sso",
                                "gobernanza", "dax", "automl"]},
}

# La escalera de módulos sigue el orden de precio que ya existía
# (Básico 99 < Pro 349 < Starter 690 < Enterprise a medida), que es el mismo
# que verifica tests/test_plan_diferenciado.py: ninguno más caro puede incluir
# menos que uno más barato.
#
#   Básico      —                          (solo el núcleo de cobranzas)
#   Pro         gobernanza
#   Starter     gobernanza + dax
#   Enterprise  gobernanza + dax + automl
#
# Es una PROPUESTA, no una restricción técnica: qué módulo entra en qué plan es
# una decisión comercial del dueño y se cambia editando estas listas. Y como ya
# pasa con "voz_premium", cualquier módulo se puede vender suelto a un cliente
# puntual sin tocar el catálogo:
#     emitir_licencia(cliente, "basico",
#                     features=[*PLANES["basico"]["features"], "automl"])


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


def emitir_sello_owner(dias: int = 3650) -> str:
    """Token que habilita la edición Owner. Solo el dueño puede emitirlo.

    Va dentro de `edicion.json` como `token_owner`, y `kobra/edicion.py` lo
    verifica contra la pública embebida en el programa antes de honrar
    `owner: true`. Antes ese `owner: true` se creía sin más: escribir 63 bytes
    convertía cualquier instalación en la edición sin límites.

    Se firma con `KOBRA_LICENSE_PRIVATE_KEY` — la misma privada que firma las
    licencias vendidas, que vive solo en el servidor del dueño. Sin esa
    variable esto no puede emitir nada, que es exactamente lo que se busca:
    nadie que tenga el código puede fabricarse un sello.
    """
    privada = os.environ.get("KOBRA_LICENSE_PRIVATE_KEY")
    if not privada:
        raise RuntimeError(
            "falta KOBRA_LICENSE_PRIVATE_KEY: el sello Owner solo lo puede "
            "emitir quien tiene la privada del dueño")
    ahora = int(time.time())
    return jwt.encode({"sub": "owner", "plan": "owner", "edition": "Owner",
                       "iat": ahora, "exp": ahora + dias * 24 * 3600},
                      privada, algorithm=kclave.ALGORITMO)


def emitir_modulo(cliente_id: str, modulo: str, edicion: str = "venta",
                  dias: int | None = None, secreto: str | None = None) -> str:
    """Licencia de un módulo suelto, sin plan de cobranzas.

    Es lo que recibe una distribuidora que compra solo Logística: entra al
    programa, usa su módulo, y no tiene cupo de gestiones porque no compró
    cobranzas. El `plan` del token lleva el nombre del módulo — sirve para
    mostrarlo y para soporte; lo que habilita son las `features`.
    """
    if modulo not in MODULOS_VENTA:
        raise ValueError(f"módulo desconocido: {modulo!r} "
                         f"(válidos: {list(MODULOS_VENTA)})")
    cfg = MODULOS_VENTA[modulo]
    return emitir_licencia(cliente_id, "basico", edicion=edicion,
                           cupo_mensual=0, features=[cfg["feature"]],
                           dias=dias if dias is not None else cfg["dias"],
                           secreto=secreto)


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
