# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Edición del paquete y su vigencia
===============================================
Cada paquete descargable lleva un `edicion.json` en su raíz que dice qué es:

    {"edition": "Demo", "plan": "trial", "dias": 14, "owner": false,
     "secreto": "...", "token": "..."}       ← demo/plan
    {"edition": "Owner", "plan": null, "dias": null, "owner": true}   ← owner

Este módulo es el ÚNICO lugar donde se interpreta ese archivo, y existe
porque el mismo paquete se puede abrir por dos caminos distintos:

  * `kobra_launcher.py`  → app de escritorio (React + FastAPI)
  * `kobra_streamlit.py` → dashboard Streamlit (la vía sin .exe)

Antes la lógica vivía dentro del primero. Cuando se agregó el dashboard como
segunda vía, esa asimetría se volvía un agujero comercial: la Demo abierta por
Streamlit no leía su propio `edicion.json` y por lo tanto **no aplicaba el
límite de días** — evaluación gratis para siempre con solo elegir el otro
acceso directo. Centralizarlo acá hace que las dos vías apliquen la misma
edición por construcción, y `tests/test_doble_modo.py` lo fija.
"""
from __future__ import annotations

import json
import os

ARCHIVO = "edicion.json"
CLAVE_TOKEN = "LICENCIA_TOKEN"
# El traspaso launcher → backend va por el entorno (son procesos distintos),
# pero lleva el token firmado y no un booleano: ver `es_owner()`.
ENV_SELLO_OWNER = "KOBRA_OWNER_TOKEN"
# La credencial del dueño, guardada para revalidarla en cada arranque.
CLAVE_OWNER_CREDENCIAL = "KOBRA_OWNER_CREDENCIAL"


# La última base que se le pasó a `activar()`. El backend corre en el mismo
# proceso que el launcher pero no recibe la ruta del bundle, y sin ella no
# puede decir POR QUÉ una copia no entró como owner.
_ULTIMA_BASE: str | None = None

# Los estados que puede tener el sello. Existen para que la copia del dueño
# que abre la pantalla de licencia diga cuál de las cinco causas la trajo
# hasta acá, en vez de fallar igual para todas.
SELLO_OK = "ok"
SELLO_SIN_EDICION = "sin_edicion"     # no hay edicion.json: no es paquete Owner
SELLO_NO_OWNER = "no_owner"           # es un paquete de cliente o demo
SELLO_AUSENTE = "ausente"             # dice owner pero no trae token
SELLO_INVALIDO = "invalido"           # el token no valida con la pública
SELLO_VENCIDO = "vencido"             # validaba, pero se pasó de fecha


def leer(base: str) -> dict | None:
    """El `edicion.json` del paquete, o None si es una copia del repo."""
    ruta = os.path.join(base, ARCHIVO)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


def sello_owner_valido(ed: dict) -> bool:
    """¿El sello Owner trae una firma que solo el dueño pudo poner?

    El token va firmado con RS256 y se verifica contra la pública embebida en
    el programa. Publicar esa pública no habilita nada — para eso existe. Lo
    que no se puede falsificar sin la privada es el token.

    Se exige `plan == "owner"` dentro de los claims: una licencia comprada
    cualquiera (que también valida con esta pública) no sirve para activar la
    edición del dueño.
    """
    token = ed.get("token_owner")
    if not isinstance(token, str):
        return False
    # `.strip()`: el token llega de un archivo o de una variable de entorno
    # (los lanzadores owner lo resuelven así), y un salto de línea o un espacio
    # al final lo hacía fallar la verificación. El síntoma era el peor posible
    # —la copia del dueño abriendo la pantalla de licencia sin decir por qué—
    # y un JWT no lleva espacios, así que recortarlos no afloja nada.
    token = token.strip()
    if not token:
        return False
    try:
        import jwt

        from backend_venta import licencia_clave
        claims = jwt.decode(token, licencia_clave.PUBLICA,
                            algorithms=[licencia_clave.ALGORITMO])
    except Exception:
        return False
    return claims.get("plan") == "owner"


def activar(base: str) -> dict | None:
    """Aplica la edición antes de levantar el programa.

      - owner     → `KOBRA_OWNER=1` (sin licencia ni vencimiento).
      - demo/plan → siembra el secreto de firma y el token embebidos, así la
        app valida sola y aplica días/cupo/features sin que el usuario active
        nada.

    Idempotente: solo siembra el token la primera vez, para no pisar uno que
    el usuario haya activado después (por ejemplo, al comprar un plan).
    """
    global _ULTIMA_BASE
    _ULTIMA_BASE = base
    ed = leer(base)
    if ed is None:
        return None
    if ed.get("owner"):
        # `owner: true` NO alcanza por sí solo. Este archivo vive del lado del
        # cliente y hasta acá se leía con `json.load` y se le creía: escribir
        # 63 bytes convertía cualquier demo instalada en la edición sin
        # límites, sin licencia y sin vencimiento. `packaging/Owner.bat` es
        # exactamente esa herramienta, así que el formato tampoco había que
        # adivinarlo.
        #
        # Ahora el sello tiene que traer un token firmado con la privada del
        # dueño, que se verifica con la pública que ya viaja dentro del
        # programa (`backend_venta/licencia_clave.py`). No hay criptografía
        # nueva: es la misma que valida las licencias compradas.
        if sello_owner_valido(ed):
            # Se exporta el TOKEN, no un "1". El launcher y el backend son
            # procesos distintos y el traspaso tiene que ir por el entorno,
            # pero un `KOBRA_OWNER=1` puesto a mano por el usuario antes de
            # abrir el programa valía tanto como el sello verificado. El token
            # no se puede inventar sin la privada del dueño.
            os.environ[ENV_SELLO_OWNER] = ed["token_owner"]
            return ed
        # Sello inválido o ausente: se ignora el `owner` y se sigue el camino
        # normal. No se rompe el arranque — una instalación manipulada abre
        # como lo que realmente es, no como la del dueño.
        ed = {k: v for k, v in ed.items() if k != "owner"}
    secreto, token = ed.get("secreto"), ed.get("token")
    if secreto:
        # Asignación y no `setdefault`, por el MISMO motivo que está escrito
        # doce líneas más arriba para el sello Owner.
        #
        # `setdefault` respeta lo que el usuario ya haya puesto en el entorno.
        # Y ese secreto es con el que se valida la licencia (`secreto_firma()`
        # en backend_venta/licencias.py), así que quien abría el programa con
        #
        #     export KOBRA_LICENSE_SECRET=me-lo-invento-yo
        #
        # elegía la llave contra la que se iba a verificar su propia licencia,
        # y a partir de ahí se firmaba un `enterprise` a 99 años. La validación
        # es 100% offline: no hay ningún lugar donde eso se note.
        #
        # El secreto de la edición viene adentro del paquete y es el que
        # corresponde a las licencias que emite el checkout. Manda ese.
        os.environ["KOBRA_LICENSE_SECRET"] = secreto
    if token:
        try:
            from kobra import config as kconfig
            if not kconfig.leer_extra(CLAVE_TOKEN):
                kconfig.guardar_extra(CLAVE_TOKEN, token)
        except Exception:
            # Sin config escribible el programa igual tiene que abrir: la
            # licencia se revalida en cada arranque desde `edicion.json`.
            pass
    return ed


def es_owner() -> bool:
    """¿Es la copia del dueño? Pública: la consultan otros módulos (p. ej.
    `kobra/plan.py`, para eximir al owner del cupo de cualquier plan).

    Las dos vías que quedan exigen algo que el usuario no puede fabricar:

      * el token firmado que `activar()` exporta tras validar el sello;
      * la credencial `mail|codigo` del dueño, que se revalida acá.

    Antes alcanzaba con `set KOBRA_OWNER=1` antes de lanzar el programa, o con
    escribir un booleano en la config del propio usuario. Las dos cosas las
    hacía cualquiera en diez segundos.
    """
    token = os.environ.get(ENV_SELLO_OWNER, "")
    if token and sello_owner_valido({"token_owner": token}):
        return True
    try:
        from kobra import config as kconfig
        from kobra import owner as kowner
        # Se guarda la credencial y se revalida, en vez de un "ya es owner":
        # un booleano en la config del usuario lo escribe el usuario.
        guardada = kconfig.leer_extra(CLAVE_OWNER_CREDENCIAL)
        return bool(guardada) and kowner.verificar(guardada)
    except Exception:
        return False


# Alias retrocompatible: el resto de este archivo y los tests existentes usan
# el nombre viejo con guion bajo.
_es_owner = es_owner


def base_probable() -> str:
    """Dónde buscar el `edicion.json` cuando nadie pasó la ruta.

    En el .exe empaquetado el bundle es `sys._MEIPASS`; corriendo desde el
    repo, la raíz del proyecto. Se usa solo para diagnosticar: `activar()`
    sigue recibiendo la base explícita del launcher.
    """
    import sys
    # El bundle real manda sobre cualquier otra pista: es la única fuente que
    # no se puede desactualizar. `_ULTIMA_BASE` la escribe `activar()` y sirve
    # para el layout ZIP, donde no hay `_MEIPASS`.
    empaquetado = getattr(sys, "_MEIPASS", None)
    if empaquetado:
        return empaquetado
    if _ULTIMA_BASE:
        return _ULTIMA_BASE
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def diagnostico_sello(base: str | None = None) -> dict:
    """Por qué esta copia entra —o no— como la del dueño.

    Existe por un pedido concreto y repetido: «me sigue pidiendo licencia
    cuando abro el Owner». Hasta acá las CINCO causas posibles —no es un
    paquete Owner, es el de clientes, el sello no se inyectó, el sello no
    valida, el sello venció— daban exactamente la misma pantalla y ningún
    mensaje. Con eso, la única forma de averiguarlo era leer el código.

    Devuelve `{estado, detalle, ruta, credencial}`. `credencial` dice si hay
    una credencial del dueño guardada y válida, que desbloquea igual aunque
    el sello del paquete no sirva.
    """
    base = base or base_probable()
    ruta = os.path.join(base, ARCHIVO)
    credencial = False
    try:
        from kobra import config as kconfig
        from kobra import owner as kowner
        guardada = kconfig.leer_extra(CLAVE_OWNER_CREDENCIAL)
        credencial = bool(guardada) and kowner.verificar(guardada)
    except Exception:
        credencial = False

    ed = leer(base)
    if ed is None:
        return {"estado": SELLO_SIN_EDICION, "ruta": ruta,
                "credencial": credencial,
                "detalle": ("Este paquete no trae edicion.json: no es la "
                            "edición Owner. Si instalaste las dos copias, "
                            "puede que estés abriendo la de clientes.")}
    if not ed.get("owner"):
        return {"estado": SELLO_NO_OWNER, "ruta": ruta,
                "credencial": credencial,
                "detalle": (f"Este paquete es la edición "
                            f"«{ed.get('edition') or 'de clientes'}», no la "
                            f"del dueño.")}

    token = (ed.get("token_owner") or "").strip()
    if not token:
        return {"estado": SELLO_AUSENTE, "ruta": ruta,
                "credencial": credencial,
                "detalle": ("El paquete dice ser Owner pero no trae el sello "
                            "firmado. Se construyó sin KOBRA_OWNER_SELLO.")}
    try:
        import jwt

        from backend_venta import licencia_clave
        claims = jwt.decode(token, licencia_clave.PUBLICA,
                            algorithms=[licencia_clave.ALGORITMO])
    except Exception as e:
        vencido = type(e).__name__ == "ExpiredSignatureError"
        return {"estado": SELLO_VENCIDO if vencido else SELLO_INVALIDO,
                "ruta": ruta, "credencial": credencial,
                "detalle": ("El sello Owner venció: emitilo de nuevo con "
                            "packaging/generar_sello_owner.bat y volvé a "
                            "construir." if vencido else
                            "El sello Owner no valida contra la clave pública "
                            "del programa: se firmó con otra privada o el "
                            "archivo quedó cortado.")}
    if claims.get("plan") != "owner":
        return {"estado": SELLO_INVALIDO, "ruta": ruta,
                "credencial": credencial,
                "detalle": ("El token del paquete es una licencia común, no "
                            "un sello Owner.")}
    return {"estado": SELLO_OK, "ruta": ruta, "credencial": credencial,
            "detalle": "El sello Owner es válido: la copia entra sin licencia."}


def vigencia() -> dict:
    """¿Se puede usar el programa ahora mismo?

    Devuelve `{ok, motivo, dias_restantes, owner, plan}`. `ok=True` cuando es
    la edición del dueño, cuando no hay edición (correr desde el repo) o
    cuando la licencia embebida sigue vigente.
    """
    if _es_owner():
        return {"ok": True, "motivo": None, "dias_restantes": None,
                "owner": True, "plan": "owner"}
    try:
        from backend_venta import licencias as klic
        from kobra import config as kconfig
    except Exception:
        return {"ok": True, "motivo": None, "dias_restantes": None,
                "owner": False, "plan": None}

    token = kconfig.leer_extra(CLAVE_TOKEN)
    if not token:
        # Sin token no hay edición que aplicar: es una copia del repo o una
        # instalación libre. No inventamos un bloqueo que nadie configuró.
        return {"ok": True, "motivo": None, "dias_restantes": None,
                "owner": False, "plan": None}

    r = klic.licencia_activa(token)
    if not r["ok"]:
        return {"ok": False, "motivo": r["error"], "dias_restantes": 0,
                "owner": False, "plan": None}
    import time
    claims = r["claims"]
    dias = max(0, int((claims.get("exp", 0) - time.time()) // 86400))
    return {"ok": True, "motivo": None, "dias_restantes": dias,
            "owner": False, "plan": claims.get("plan")}
