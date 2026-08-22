# © 2026 Martín Viera. Todos los derechos reservados.

"""Utilidades compartidas por la suite.

Dos cosas:

1. Armar un sello Owner legítimo. Desde que `edicion.json` dejó de creerle a
   un `owner: true` pelado, cualquier test que necesite correr como el dueño
   tiene que traer un token firmado — y la privada real no está (ni tiene que
   estar) en el repo. Estos fixtures generan un par de prueba y le enseñan al
   programa a verificar contra ESA pública, que es lo mismo que hace en
   producción contra la del dueño.

2. Hablarle al servicio de tiempo real, que desde `realtime/acceso.py` pide
   credenciales. Antes no pedía nada y cualquier test podía pegarle de una;
   ahora el token de prueba es fijo y conocido, y hay un helper para firmar
   como Twilio los webhooks de voz.
"""
import time

import pytest

# Token de prueba del servicio en vivo. Fijo y conocido: no es un secreto,
# es lo que hace que los tests puedan entrar (y que uno que quiera probar el
# 401 solo tenga que borrar la variable).
TOKEN_REALTIME = "token-de-prueba-del-servicio-en-vivo-de-kobra"
CABECERA_REALTIME = {"X-Kobra-Token": TOKEN_REALTIME}


@pytest.fixture(autouse=True)
def _token_realtime_conocido(monkeypatch):
    monkeypatch.setenv("KOBRA_REALTIME_TOKEN", TOKEN_REALTIME)


def firma_twilio(url: str, form: dict, auth_token: str) -> dict:
    """Cabecera `X-Twilio-Signature` válida para ese webhook.

    Los webhooks de voz (`/voz/entrante`, `/voz/turno`) son públicos por
    necesidad —Twilio tiene que poder postearlos— así que su credencial es la
    firma. Un test que los llame tiene que firmar igual que Twilio.
    """
    from realtime import acceso
    return {"X-Twilio-Signature": acceso.firma_esperada(url, form, auth_token)}


@pytest.fixture(autouse=True)
def _sin_owner_heredado():
    """Ningún test empieza siendo el dueño por culpa del anterior.

    `edicion.activar()` escribe en `os.environ` directamente (tiene que hacerlo:
    el traspaso al proceso del backend va por ahí), así que sin esto un test
    que activa Owner deja la variable puesta y el siguiente pasa por el motivo
    equivocado — o falla sin razón aparente al correr la suite entera pero no
    aislado.
    """
    import os
    previo = {k: os.environ.get(k) for k in ("KOBRA_OWNER", "KOBRA_OWNER_TOKEN")}
    for k in previo:
        os.environ.pop(k, None)
    yield
    for k, v in previo.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture()
def par_owner(monkeypatch):
    """Par RSA de prueba, ya instalado como la pública que valida el programa.

    Devuelve la privada en PEM. Cualquier sello firmado con ella vale para
    esta sesión de test y para ninguna otra cosa.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = k.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
    publica = k.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    from backend_venta import licencia_clave
    monkeypatch.setattr(licencia_clave, "PUBLICA", publica)
    return privada


@pytest.fixture()
def sello_owner(par_owner):
    """Un `edicion.json` de Owner con su token firmado, listo para escribir.

    Uso: `json.dump(sello_owner, open(ruta, "w"))`.
    """
    import jwt
    ahora = int(time.time())
    token = jwt.encode({"sub": "owner", "plan": "owner", "edition": "Owner",
                        "iat": ahora, "exp": ahora + 3650 * 24 * 3600},
                       par_owner, algorithm="RS256")
    return {"edition": "Owner", "plan": None, "dias": None,
            "owner": True, "token_owner": token}
