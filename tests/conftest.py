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
    # Mismo motivo, otra variable: `activar()` recuerda la carpeta del paquete
    # para poder DIAGNOSTICAR después por qué una copia no entró como owner. Un
    # test que la activa sobre un tmp_path dejaba esa carpeta apuntada, y el
    # test siguiente diagnosticaba el paquete del anterior —que además ya no
    # existe— dando un motivo inventado.
    from kobra import edicion as kedicion
    base_previa = kedicion._ULTIMA_BASE
    kedicion._ULTIMA_BASE = None
    yield
    kedicion._ULTIMA_BASE = base_previa
    for k, v in previo.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


_PAR_LICENCIAS: tuple[str, str] | None = None


def _par_licencias() -> tuple[str, str]:
    """Par RSA de prueba, generado una sola vez por corrida."""
    global _PAR_LICENCIAS
    if _PAR_LICENCIAS is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _PAR_LICENCIAS = (
            k.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode(),
            k.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    return _PAR_LICENCIAS


def pytest_runtest_setup(item):
    """Reponer la privada de prueba ANTES de cada test, fixtures incluidos.

    No alcanza con ponerla una vez al arrancar la sesión, y el motivo es una
    conducta CORRECTA del producto: `packaging/generar_sello_owner.py` borra
    `KOBRA_LICENSE_PRIVATE_KEY` de `os.environ` apenas termina de firmar, para
    no dejar la clave del dueño dando vueltas en el proceso —hay un test que
    lo exige, `test_no_deja_la_clave_en_el_entorno`—. Esa limpieza se lleva
    puesta la variable del fixture, y a partir de ahí toda la suite vuelve a
    emitir HS256: 70 tests en rojo, ninguno reproducible corriendo el archivo
    solo.

    Este hook corre antes que los fixtures del test —también los de scope
    módulo, que es donde `test_e2e_escenarios.py` emite su licencia—, así que
    es el único lugar desde el que se puede reponer a tiempo. Un test que
    quiera correr SIN privada la saca con `monkeypatch.delenv`, que se aplica
    después y se deshace al terminar.
    """
    import os
    privada, publica = _par_licencias()
    os.environ["KOBRA_LICENSE_PRIVATE_KEY"] = privada
    from backend_venta import licencia_clave
    licencia_clave.PUBLICA = publica


@pytest.fixture(scope="session", autouse=True)
def _licencias_firmadas_como_en_produccion():
    """La suite emite y valida licencias por el MISMO camino que un cliente.

    Antes no: sin `KOBRA_LICENSE_PRIVATE_KEY`, `emitir_licencia` caía a HS256
    con un secreto de entorno, y `validar_licencia` tenía un fallback que lo
    aceptaba. O sea que decenas de tests ejercitaban un camino que en una
    instalación real es un agujero —el cliente pone la variable y se firma su
    propia licencia enterprise— y NINGUNO ejercitaba el camino asimétrico, que
    es el único que de verdad corre en la máquina de un comprador.

    Con este fixture, `emitir_licencia` firma RS256 (hay privada) y la
    validación verifica contra esta pública. Un test que quiera el otro camino
    lo pide explícito, que es como quedó la interfaz: pasando `secreto=`.

    **Es de sesión y no de función a propósito.** Pytest instancia primero los
    fixtures de scope más ancho, así que uno de función llega TARDE para un
    `_montar()` que vive en un fixture de módulo (`test_e2e_escenarios.py`):
    ese módulo emitía su licencia antes de que existiera la privada y se
    quedaba sin plan. Costó diez tests en rojo encontrarlo.

    Generar una clave de 2048 bits cuesta decenas de milisegundos; una sola vez
    por corrida no se nota, una por test sí.

    La reposición por test la hace `pytest_runtest_setup` (arriba): el producto
    borra la privada del entorno después de firmar un sello, y sin reponerla la
    suite entera se cae detrás de ese test.
    """
    privada, publica = _par_licencias()
    from backend_venta import licencia_clave
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("KOBRA_LICENSE_PRIVATE_KEY", privada)
        mp.setattr(licencia_clave, "PUBLICA", publica)
        yield


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
