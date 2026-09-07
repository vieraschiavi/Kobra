# © 2026 Martín Viera. Todos los derechos reservados.

"""Cuando la copia del dueño pide licencia, tiene que decir POR QUÉ.

El pedido que originó esto fue literal: «me sigue pidiendo número de licencia
cuando abro en Owner». Hasta ese momento había CINCO causas posibles —no es un
paquete Owner, es el de clientes, el sello no se inyectó, el sello no valida,
el sello venció— y las cinco daban exactamente la misma pantalla, sin una
palabra de explicación. La única forma de averiguarlo era leer el código.

Estos tests fijan que cada causa se distinga de las otras, y que el mensaje no
se filtre a la copia de un cliente.
"""
import importlib
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import edicion as ked  # noqa: E402


def _escribir(carpeta, datos):
    with open(os.path.join(carpeta, ked.ARCHIVO), "w", encoding="utf-8") as f:
        json.dump(datos, f)
    return str(carpeta)


@pytest.fixture(autouse=True)
def _sin_credencial(monkeypatch, tmp_path):
    """Sin credencial de dueño guardada: si no, tapa el diagnóstico del sello."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv(ked.ENV_SELLO_OWNER, raising=False)
    from kobra import config as kconfig
    importlib.reload(kconfig)
    yield


def _firmar(claims):
    """Un token firmado con una privada de juguete: sirve para probar el
    camino «no valida», que es lo que ve alguien que firmó con otra clave."""
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return jwt.encode(claims, privada, algorithm="RS256")


# ---------------------------------------------------------------------------
# Las cinco causas, cada una con su nombre
# ---------------------------------------------------------------------------

def test_sin_edicion_json_dice_que_no_es_un_paquete_owner(tmp_path):
    """El caso más probable en la práctica: están instaladas las dos copias y
    se abrió la de clientes."""
    d = ked.diagnostico_sello(str(tmp_path))
    assert d["estado"] == ked.SELLO_SIN_EDICION
    assert "clientes" in d["detalle"]


def test_un_paquete_de_cliente_se_nombra_como_lo_que_es(tmp_path):
    base = _escribir(tmp_path, {"edition": "Demo", "plan": "trial", "dias": 7})
    d = ked.diagnostico_sello(base)
    assert d["estado"] == ked.SELLO_NO_OWNER
    assert "Demo" in d["detalle"]


def test_owner_sin_sello_dice_que_se_construyo_sin_el(tmp_path):
    """El build corrió pero nadie exportó KOBRA_OWNER_SELLO."""
    base = _escribir(tmp_path, {"edition": "Owner", "owner": True})
    d = ked.diagnostico_sello(base)
    assert d["estado"] == ked.SELLO_AUSENTE
    assert "KOBRA_OWNER_SELLO" in d["detalle"]


def test_un_sello_firmado_con_otra_clave_no_se_confunde_con_uno_vencido(tmp_path):
    base = _escribir(tmp_path, {"edition": "Owner", "owner": True,
                                "token_owner": _firmar({"plan": "owner"})})
    d = ked.diagnostico_sello(base)
    assert d["estado"] == ked.SELLO_INVALIDO
    assert "no valida" in d["detalle"]


def test_un_sello_ilegible_tampoco_rompe_el_diagnostico(tmp_path):
    base = _escribir(tmp_path, {"edition": "Owner", "owner": True,
                                "token_owner": "esto-no-es-un-jwt"})
    assert ked.diagnostico_sello(base)["estado"] == ked.SELLO_INVALIDO


def test_un_sello_vencido_se_nombra_vencido(tmp_path, monkeypatch):
    """Distinguirlo importa: uno se arregla re-emitiendo el sello y el otro
    revisando con qué clave se firmó."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    publica = privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    ayer = int(time.time()) - 86400
    token = jwt.encode({"plan": "owner", "exp": ayer}, privada, algorithm="RS256")

    from backend_venta import licencia_clave
    monkeypatch.setattr(licencia_clave, "PUBLICA", publica)
    base = _escribir(tmp_path, {"edition": "Owner", "owner": True,
                                "token_owner": token})
    d = ked.diagnostico_sello(base)
    assert d["estado"] == ked.SELLO_VENCIDO
    assert "venció" in d["detalle"]


def test_una_licencia_comun_no_pasa_por_sello_owner(tmp_path, monkeypatch):
    """Una licencia comprada valida con la MISMA pública. Sin mirar el claim
    `plan`, cualquier cliente con su licencia se haría owner."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    publica = privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    token = jwt.encode({"plan": "pro", "exp": int(time.time()) + 86400},
                       privada, algorithm="RS256")

    from backend_venta import licencia_clave
    monkeypatch.setattr(licencia_clave, "PUBLICA", publica)
    base = _escribir(tmp_path, {"edition": "Owner", "owner": True,
                                "token_owner": token})
    d = ked.diagnostico_sello(base)
    assert d["estado"] == ked.SELLO_INVALIDO
    assert "licencia común" in d["detalle"]


def test_un_sello_valido_se_reporta_ok(tmp_path, monkeypatch):
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    publica = privada.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    token = jwt.encode({"plan": "owner", "exp": int(time.time()) + 9999},
                       privada, algorithm="RS256")

    from backend_venta import licencia_clave
    monkeypatch.setattr(licencia_clave, "PUBLICA", publica)
    base = _escribir(tmp_path, {"edition": "Owner", "owner": True,
                                "token_owner": token})
    assert ked.diagnostico_sello(base)["estado"] == ked.SELLO_OK


# ---------------------------------------------------------------------------
# Que llegue a donde se ve
# ---------------------------------------------------------------------------

def test_el_informe_de_diagnostico_incluye_la_edicion():
    """`MVKobraAI.exe --diagnostico` es lo que se corre con doble clic cuando
    el programa «no abre como debería»."""
    from kobra import entorno
    informe = entorno.informe_texto()
    assert "Edicion de esta copia" in informe
    # Sin acentos: se copia de una consola de Windows en cp850 y se pega en un
    # mail (misma razón que el resto del informe).
    assert all(ord(c) < 128 for c in informe), "el informe tiene que ser ASCII"


def test_la_pantalla_de_licencia_muestra_el_motivo_cuando_el_paquete_dice_owner():
    app = open(os.path.join(ROOT, "webapp", "frontend", "src", "App.jsx"),
               encoding="utf-8").read()
    pagina = open(os.path.join(ROOT, "webapp", "frontend", "src", "pages",
                               "Activacion.jsx"), encoding="utf-8").read()
    assert "sello={licEstado.sello}" in app
    assert "sello.detalle" in pagina


def test_a_un_cliente_no_se_le_cuenta_que_existe_la_edicion_owner(tmp_path,
                                                                  monkeypatch):
    """El campo `sello` solo puede aparecer en un paquete que se declara
    Owner. En la copia de un comprador la respuesta tiene que ser la de
    siempre: ni una palabra sobre otra edición ni sobre cómo desbloquearla."""
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    base = _escribir(tmp_path, {"edition": "Demo", "plan": "trial", "dias": 7})
    monkeypatch.setattr(ked, "_ULTIMA_BASE", base)

    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    monkeypatch.setattr(api.kedicion, "_ULTIMA_BASE", base)
    cuerpo = TestClient(api.app).get("/api/licencia/estado").json()
    assert "sello" not in cuerpo, cuerpo
