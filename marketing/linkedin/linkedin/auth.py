"""OAuth 2.0 de LinkedIn: autorización, token y guardado seguro.

Flujo: se abre el navegador en la pantalla de LinkedIn, la persona autoriza,
LinkedIn redirige a un servidor local de un solo uso que captura el código, y
ese código se cambia por un access token.
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import stat
import threading
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import BASE_API, BASE_AUTH, RUTA_TOKEN, SCOPES, Credenciales


class ErrorAutenticacion(RuntimeError):
    pass


@dataclass
class Token:
    access_token: str
    expira_en: str          # ISO 8601 UTC
    sub: str                # id del miembro; el URN de autor sale de acá
    nombre: str = ""

    @property
    def vencido(self) -> bool:
        # Se considera vencido 5 minutos antes del vencimiento real: publicar
        # con un token que expira a mitad del request da un 401 confuso.
        limite = datetime.fromisoformat(self.expira_en) - timedelta(minutes=5)
        return datetime.now(timezone.utc) >= limite

    @property
    def urn_autor(self) -> str:
        return f"urn:li:person:{self.sub}"


def guardar_token(token: Token, ruta: Path = RUTA_TOKEN) -> None:
    """Escribe el token con permisos 600.

    Se crea el archivo vacío y se le fijan los permisos ANTES de escribir el
    contenido. Al revés habría una ventana —chica pero real— en la que el
    token está en disco y legible por cualquier usuario de la máquina.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.touch(mode=0o600, exist_ok=True)
    os.chmod(ruta, stat.S_IRUSR | stat.S_IWUSR)
    ruta.write_text(json.dumps(asdict(token), indent=2), encoding="utf-8")


def cargar_token(ruta: Path = RUTA_TOKEN) -> Token | None:
    if not ruta.is_file():
        return None
    try:
        return Token(**json.loads(ruta.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        # Un token corrupto se trata como ausente: es preferible re-autorizar
        # a explotar con un stacktrace que no le dice nada a nadie.
        return None


class _Captura(http.server.BaseHTTPRequestHandler):
    """Servidor de un solo uso que recibe el redirect de LinkedIn."""
    codigo: str | None = None
    estado: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Captura.codigo = (q.get("code") or [None])[0]
        _Captura.estado = (q.get("state") or [None])[0]
        _Captura.error = (q.get("error_description") or q.get("error") or [None])[0]
        ok = _Captura.codigo is not None
        cuerpo = (
            "<h2>Listo. Ya podés cerrar esta pestaña y volver a la terminal.</h2>"
            if ok else
            f"<h2>No se pudo autorizar</h2><p>{_Captura.error or 'sin detalle'}</p>"
        )
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body style='font-family:sans-serif;padding:3rem'>{cuerpo}</body></html>".encode())

    def log_message(self, *_args) -> None:
        pass  # sin ruido en la terminal


def autorizar(cred: Credenciales, abrir_navegador: bool = True) -> Token:
    """Corre el flujo completo y devuelve un token válido."""
    # El state es obligatorio y de un solo uso: sin él, cualquiera puede
    # inducir un callback y hacer que el cliente canjee un código ajeno (CSRF).
    estado = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": cred.client_id,
        "redirect_uri": cred.redirect_uri,
        "state": estado,
        "scope": " ".join(SCOPES),
    }
    url = f"{BASE_AUTH}/authorization?{urllib.parse.urlencode(params)}"

    parsed = urllib.parse.urlparse(cred.redirect_uri)
    servidor = http.server.HTTPServer((parsed.hostname or "localhost", parsed.port or 80), _Captura)
    hilo = threading.Thread(target=servidor.handle_request, daemon=True)
    hilo.start()

    print("Abriendo LinkedIn para autorizar...")
    print(f"Si no se abre solo, entrá a:\n  {url}\n")
    if abrir_navegador:
        webbrowser.open(url)
    hilo.join(timeout=300)
    servidor.server_close()

    if _Captura.error:
        raise ErrorAutenticacion(f"LinkedIn rechazó la autorización: {_Captura.error}")
    if not _Captura.codigo:
        raise ErrorAutenticacion("No llegó el código de autorización (pasaron 5 minutos).")
    if _Captura.estado != estado:
        # No se canjea nunca un código que vino con un state que no emitimos.
        raise ErrorAutenticacion("El state no coincide: se descarta el código por seguridad.")

    return _canjear(cred, _Captura.codigo)


def _canjear(cred: Credenciales, codigo: str) -> Token:
    datos = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": codigo,
        "client_id": cred.client_id,
        "client_secret": cred.client_secret,
        "redirect_uri": cred.redirect_uri,
    }).encode()
    req = urllib.request.Request(
        f"{BASE_AUTH}/accessToken", data=datos,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:400]
        raise ErrorAutenticacion(
            f"LinkedIn devolvió {e.code} al canjear el código.\n{detalle}\n"
            "Causa más común: el redirect_uri no coincide EXACTO con el "
            "autorizado en la app (revisá la barra final)."
        ) from e

    access = payload["access_token"]
    vence = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 5184000)))
    perfil = _userinfo(access)
    return Token(
        access_token=access,
        expira_en=vence.isoformat(),
        sub=perfil["sub"],
        nombre=perfil.get("name", ""),
    )


def _userinfo(access_token: str) -> dict:
    """GET /v2/userinfo — de acá sale el `sub` que arma el URN de autor."""
    req = urllib.request.Request(
        f"{BASE_API}/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ErrorAutenticacion(
            f"No se pudo leer el perfil ({e.code}). Verificá que la app tenga "
            "habilitado el producto 'Sign In with LinkedIn using OpenID Connect'."
        ) from e


def token_valido(cred: Credenciales) -> Token:
    """Devuelve un token usable: el guardado si sirve, o uno nuevo."""
    token = cargar_token()
    if token and not token.vencido:
        return token
    if token:
        print("El token guardado venció. Hay que autorizar de nuevo.")
    token = autorizar(cred)
    guardar_token(token)
    print(f"Token guardado en {RUTA_TOKEN} (permisos 600).")
    return token
