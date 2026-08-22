# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Quién puede hablarle al servicio de tiempo real
=============================================================
`realtime/server.py` no pedía credenciales a nadie. Tenía freno por IP y
candado de plan —que son otra cosa— pero cualquiera que llegara al puerto
tenía el producto entero:

  * `GET /brief/{id_deudor}` devuelve monto de la deuda, probabilidad de pago
    y **el descuento autorizado**, y los identificadores son correlativos
    (`KB-100000`, `KB-100001`, …): con un `for` se baja la cartera completa
    del cliente. Eso es la base de datos de deudores de una financiera,
    saliendo por HTTP sin una sola credencial.
  * `POST /voz/llamar` marca un teléfono de verdad y le habla un bot.
  * `/transcribe`, `/analizar_audio`, `/copiloto_audio` procesan audio (y
    gastan la API del proveedor de IA del cliente).

Y este servicio tiene que ser alcanzable desde afuera para que Twilio pueda
postear los webhooks de la llamada, así que "está en la red interna" no es una
respuesta: el mismo túnel que deja entrar a Twilio deja entrar a cualquiera.

Cómo se cierra
--------------
Dos mecanismos distintos, porque son dos clientes distintos:

1. **Operación** (el gestor, el CTI, el dashboard): un token compartido. Se
   genera solo en el primer arranque y se guarda con el resto de la
   configuración; se manda como `Authorization: Bearer …`, cabecera
   `X-Kobra-Token`, `?t=` en la URL o cookie. Nadie tiene que inventar nada
   ni "acordarse de configurar" — si no está, se crea.

2. **Twilio** (los webhooks de voz): la firma `X-Twilio-Signature`, que es el
   mecanismo que Twilio ya provee. Un token nuestro no sirve acá: la URL del
   webhook la ve cualquiera que mire la configuración de la llamada.

Lo que queda abierto es solo lo que no expone datos ni gasta plata: el
health-check, la métrica de capacidad, el ícono y las páginas HTML estáticas
(que sin token no pueden pedir nada). **Todo lo demás requiere token por
defecto**, incluso un endpoint que se agregue mañana y del que nadie se
acuerde: la lista es de lo abierto, no de lo cerrado.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

CLAVE_CONFIG = "realtime_token"
VAR_ENTORNO = "KOBRA_REALTIME_TOKEN"   # nombre de la variable, no un secreto

# Sin token: no devuelven datos del cliente ni disparan nada. Las páginas HTML
# están acá porque son estáticas — sin token no pueden pedir nada útil, y
# dejarlas abiertas evita el 401 en blanco que no le dice nada a nadie.
ABIERTAS = frozenset({
    "/", "/health", "/capacidad", "/mv_icon.png", "/llamar", "/favicon.ico",
})

# Las postea Twilio, que no puede mandar nuestro token. Se validan con la
# firma de Twilio (`verificar_twilio`), no con el token.
DE_TWILIO = frozenset({"/voz/entrante", "/voz/turno"})

# El audio de un turno ya lleva su propio token de un solo uso en la ruta
# (`/voz/audio/<token>.mp3`), que es lo que Twilio va a buscar con un GET
# simple, sin firmar. Ese token ES la credencial.
PREFIJOS_ABIERTOS = ("/voz/audio/",)

# `/twilio` es el WebSocket de Twilio Media Streams. Twilio abre ese socket
# desde su infraestructura y NO firma el handshake ni puede mandar cabeceras
# nuestras, así que no hay credencial que pedirle. Queda cubierto por el freno
# por IP (`LimitadorGeneral`) y por el tope de sesiones simultáneas; lo que
# NO expone es la cartera —solo transporta el audio de una llamada en curso—,
# que es la razón por la que se acepta dejarlo abierto y no una omisión.
WS_ABIERTOS = frozenset({"/twilio"})


# ---------------------------------------------------------------------------
# El token de operación
# ---------------------------------------------------------------------------
def token(crear: bool = True) -> str:
    """El token de este equipo. Lo genera y lo guarda si todavía no existe.

    `KOBRA_REALTIME_TOKEN` pisa todo: es la forma de fijarlo desde el
    orquestador (Docker, systemd, un servicio de Windows) sin depender del
    archivo de configuración.
    """
    del_entorno = (os.getenv(VAR_ENTORNO) or "").strip()
    if del_entorno:
        return del_entorno
    from kobra import config as kconfig
    guardado = (kconfig.leer_extra(CLAVE_CONFIG) or "").strip()
    if guardado or not crear:
        return guardado
    nuevo = secrets.token_urlsafe(32)
    kconfig.guardar_extra(CLAVE_CONFIG, nuevo)
    return nuevo


def _presentado(headers, query, cookies) -> str:
    """El token que trae el pedido, mire donde mire.

    Cuatro lugares porque hay cuatro clientes: `Authorization: Bearer` para el
    CTI, `X-Kobra-Token` para integraciones que no quieren tocar Authorization,
    `?t=` para abrir una página desde un link, y la cookie para que esa página
    después pueda hacer sus `fetch` sin repetir el token en cada URL.
    """
    auth = headers.get("authorization") or ""
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (headers.get("x-kobra-token") or query.get("t")
            or cookies.get("kobra_rt") or "").strip()


def autorizado(ruta: str, headers, query, cookies) -> bool:
    """¿Puede pasar este pedido?

    Por defecto NO: una ruta que no está en las listas de arriba —incluida una
    que se agregue mañana— pide token. Cerrar por olvido es un bug molesto;
    abrir por olvido es la cartera de un cliente en la calle.
    """
    if ruta in ABIERTAS or ruta in DE_TWILIO or ruta in WS_ABIERTOS:
        return True
    if any(ruta.startswith(p) for p in PREFIJOS_ABIERTOS):
        return True
    esperado = token(crear=True)
    if not esperado:
        return False
    # compare_digest y no `==`: comparar tokens con `==` corta en el primer
    # byte distinto y filtra el token de a un caracter por vez.
    return hmac.compare_digest(_presentado(headers, query, cookies), esperado)


class Candado:
    """Middleware ASGI puro: el token, en HTTP y en WebSocket por igual.

    Tiene que ser ASGI y no `@app.middleware("http")` por la misma razón que
    `LimitadorGeneral`: el decorador HTTP de Starlette no envuelve el handshake
    de WebSocket, y `/ws` y `/ws_audio` —por donde entra el audio de las
    llamadas y sale la asesoría del copiloto— quedarían afuera del candado
    justo donde más importa.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        from starlette.requests import HTTPConnection
        conexion = HTTPConnection(scope)
        if autorizado(scope.get("path", ""), conexion.headers,
                      conexion.query_params, conexion.cookies):
            await self._pasar(scope, receive, send, conexion)
            return

        if scope["type"] == "websocket":
            # 1008 = "Policy Violation": el código del protocolo para "no
            # tenés permiso", que es lo que un cliente puede diagnosticar.
            await send({"type": "websocket.close", "code": 1008,
                        "reason": "falta el token de acceso"})
            return
        from starlette.responses import JSONResponse
        respuesta = JSONResponse(
            {"error": "Falta el token de acceso del servicio en vivo.",
             "detalle": "Mandalo como 'Authorization: Bearer …', cabecera "
                        "'X-Kobra-Token' o '?t=' en la URL. Lo tenés en la "
                        "pantalla de Configuración del programa y en la "
                        "consola al arrancar el servicio.",
             "motivo": "sin_token"}, status_code=401)
        await respuesta(scope, receive, send)

    async def _pasar(self, scope, receive, send, conexion):
        """Deja pasar, y si el token vino por la URL lo guarda en una cookie.

        Así una página que se abrió con `?t=…` puede seguir haciendo sus
        `fetch` sin arrastrar el token en cada URL —donde queda en el
        historial del navegador y en los logs de cualquier proxy.
        """
        t = conexion.query_params.get("t") if scope["type"] == "http" else None
        if not t or conexion.cookies.get("kobra_rt") == t:
            await self.app(scope, receive, send)
            return

        segura = scope.get("scheme") in ("https", "wss")
        galleta = (f"kobra_rt={t}; Path=/; HttpOnly; SameSite=Lax"
                   + ("; Secure" if segura else ""))

        async def con_cookie(mensaje):
            if mensaje["type"] == "http.response.start":
                mensaje = dict(mensaje)
                mensaje["headers"] = list(mensaje.get("headers", [])) + [
                    (b"set-cookie", galleta.encode("latin-1"))]
            await send(mensaje)

        await self.app(scope, receive, con_cookie)


# ---------------------------------------------------------------------------
# La firma de Twilio
# ---------------------------------------------------------------------------
def firma_esperada(url: str, params: dict, auth_token: str) -> str:
    """La firma que Twilio manda en `X-Twilio-Signature`.

    Algoritmo de Twilio: la URL completa (con query string) seguida de cada
    par clave+valor del cuerpo, ORDENADO POR CLAVE y concatenado sin
    separadores; HMAC-SHA1 con el auth token de la cuenta; base64.
    """
    base = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    mac = hmac.new(auth_token.encode("utf-8"), base.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("ascii")


def verificar_twilio(url: str, params: dict, firma: str | None,
                     auth_token: str | None = None) -> bool:
    """¿Este webhook lo mandó Twilio de verdad?

    Sin `TWILIO_AUTH_TOKEN` configurado devuelve **False**: no se puede
    verificar, y no verificar significa que cualquiera puede postear un turno
    de conversación inventado. Fallar cerrado acá no rompe a nadie —sin ese
    token no se pueden hacer llamadas de todos modos, así que quien tiene el
    canal funcionando lo tiene puesto.
    """
    auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN") or ""
    if not (auth_token and firma):
        return False
    return hmac.compare_digest(firma_esperada(url, params, auth_token), firma)


def url_publica(request) -> str:
    """La URL exacta que Twilio firmó.

    Detrás de un proxy o un túnel (ngrok, Cloudflare) `request.url` trae el
    host interno y la firma no da: hay que reconstruirla con lo que ve
    Twilio. `PUBLIC_BASE_URL` es la fuente autoritativa cuando está puesta —
    es la misma que se usa para armar las URLs de los webhooks.
    """
    ruta = request.url.path
    consulta = request.url.query
    base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    if not base:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        base = f"{proto}://{host}"
    return f"{base}{ruta}" + (f"?{consulta}" if consulta else "")
