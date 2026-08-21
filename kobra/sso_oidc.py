# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Single Sign-On corporativo (OpenID Connect)
=====================================================
Login federado **genérico**, compatible con cualquier proveedor de identidad
que hable OIDC estándar — Microsoft Entra ID / Azure AD, Okta, Google
Workspace, Auth0, Keycloak, etc. No asume un proveedor específico: el cliente
carga su propio `issuer`/`client_id`/`client_secret` en la pestaña
Configuración (solo admin), igual que carga cualquier otra API key.

Flujo (Authorization Code, el estándar para apps que no son SPA):

  1. El botón "Iniciar sesión con SSO" arma la URL de autorización del
     proveedor (con un `state` aleatorio guardado en la sesión, para evitar
     CSRF) y redirige al navegador ahí.
  2. El usuario se autentica en SU proveedor de identidad (MV Kobra AI nunca ve
     su contraseña corporativa).
  3. El proveedor redirige de vuelta a la propia URL del dashboard con
     `?code=...&state=...` — Streamlit lo recibe como query params.
  4. `procesar_callback()` valida el `state`, cambia el `code` por tokens en
     el `token_endpoint`, y **verifica la firma del ID token contra las
     claves públicas (JWKS) del proveedor** — nunca confía en el token sin
     verificar la firma y el emisor/audiencia.

Rol asignado: si el email autenticado está en `OIDC_ADMINS` (lista separada
por comas, configurable), entra como `admin`; si no, como `gestor`. Esto es
SSO real para autenticación — no reemplaza el login local (que sigue
funcionando igual), es una alternativa que se activa sola cuando el cliente
carga sus credenciales de proveedor.
"""
from __future__ import annotations

import secrets
import time
import urllib.parse

import jwt
import requests

from kobra import config as kconfig

_CLAVES = ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI")
_STATE_KEY = "kobra_oidc_state"
_DISCOVERY_TTL = 3600  # 1 hora — no golpear el discovery endpoint en cada rerun
_discovery_cache: dict = {}


def configurado() -> bool:
    """¿Hay SSO activo? Requiere las cuatro claves Y el plan que lo incluye.

    `sso` se vende solo en Enterprise, pero no lo gateaba nadie: un cliente de
    Básico (US$99) abría Configuración, cargaba Issuer / Client ID / Secret /
    Redirect y tenía login corporativo por OIDC, que es una capacidad de otro
    plan. No es un agujero de seguridad —es su propio proveedor de identidad—
    pero sí producto regalado.

    Se chequea acá y no en cada llamador porque esta función es la única
    puerta: si devuelve False no aparece el botón, no se arma la URL de
    autorización y no se procesa el callback.
    """
    if not all(kconfig.leer_extra(c) for c in _CLAVES):
        return False
    try:
        from kobra import plan as kplan
        return kplan.permite("sso")
    except Exception:
        # Sin el módulo de planes (copia suelta, tests de otra cosa) no se
        # inventa un bloqueo: la configuración manda.
        return True


def _cfg() -> dict:
    return {c: kconfig.leer_extra(c) for c in _CLAVES}


def _admins() -> set[str]:
    raw = kconfig.leer_extra("OIDC_ADMINS") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def rol_para(email: str) -> str:
    return "admin" if email.strip().lower() in _admins() else "gestor"


def _discovery(issuer: str) -> dict:
    cached = _discovery_cache.get(issuer)
    if cached and cached["exp"] > time.time():
        return cached["data"]
    r = requests.get(issuer.rstrip("/") + "/.well-known/openid-configuration", timeout=10)
    r.raise_for_status()
    data = r.json()
    _discovery_cache[issuer] = {"data": data, "exp": time.time() + _DISCOVERY_TTL}
    return data


def url_autorizacion(session_state: dict) -> str | None:
    """Arma la URL de login del proveedor. Guarda un `state` anti-CSRF en
    `session_state` (pasale `st.session_state`)."""
    if not configurado():
        return None
    cfg = _cfg()
    disco = _discovery(cfg["OIDC_ISSUER"])
    state = secrets.token_urlsafe(24)
    session_state[_STATE_KEY] = state
    params = {
        "response_type": "code",
        "client_id": cfg["OIDC_CLIENT_ID"],
        "redirect_uri": cfg["OIDC_REDIRECT_URI"],
        "scope": "openid email profile",
        "state": state,
    }
    return disco["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)


class CallbackError(Exception):
    pass


def procesar_callback(code: str, state: str, session_state: dict) -> dict:
    """
    Cambia el `code` por tokens y verifica el ID token. Devuelve
    {"email": str, "nombre": str, "rol": "admin"|"gestor"}.
    Lanza CallbackError con un mensaje seguro para mostrar si algo falla
    (state inválido, token mal firmado, emisor/audiencia incorrectos, etc.).
    """
    if not configurado():
        raise CallbackError("SSO no está configurado en este servidor.")

    esperado = session_state.pop(_STATE_KEY, None)
    if not esperado or not secrets.compare_digest(state or "", esperado):
        raise CallbackError("El login no se pudo validar (state inválido o expirado). Probá de nuevo.")

    cfg = _cfg()
    disco = _discovery(cfg["OIDC_ISSUER"])

    try:
        r = requests.post(disco["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": cfg["OIDC_REDIRECT_URI"],
            "client_id": cfg["OIDC_CLIENT_ID"], "client_secret": cfg["OIDC_CLIENT_SECRET"],
        }, timeout=15)
        r.raise_for_status()
        tokens = r.json()
    except Exception as e:
        raise CallbackError(f"No se pudo confirmar el login con el proveedor: {e}") from e

    id_token = tokens.get("id_token")
    if not id_token:
        raise CallbackError("El proveedor no devolvió un id_token.")

    try:
        jwks_client = jwt.PyJWKClient(disco["jwks_uri"])
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token, signing_key.key, algorithms=["RS256"],
            audience=cfg["OIDC_CLIENT_ID"], issuer=cfg["OIDC_ISSUER"],
        )
    except jwt.PyJWTError as e:
        raise CallbackError(f"El token del proveedor no se pudo verificar: {e}") from e

    email = claims.get("email") or claims.get("preferred_username") or claims.get("sub")
    if not email:
        raise CallbackError("El proveedor no informó un email/identificador de usuario.")

    return {"email": email, "nombre": claims.get("name", email), "rol": rol_para(email)}
