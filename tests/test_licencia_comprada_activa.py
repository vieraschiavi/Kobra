# © 2026 Martín Viera. Todos los derechos reservados.

"""El cliente que paga tiene que poder entrar. Antes no podía.

El bug, reproducido antes de arreglarlo:

    servidor de ventas emite la licencia  -> OK
    cliente la pega en su instalación     -> licencia_invalida:
                                             Signature verification failed

Las licencias se firmaban HS256, con un secreto COMPARTIDO. El servidor tiene
el suyo en Vercel; la copia instalada lo busca en `KOBRA_LICENSE_SECRET`,
después en su configuración, y si no encuentra ninguno **se genera uno al
azar**. El instalador de clientes se arma sin `edicion.json` —a propósito, es
la demo de 3 días—, así que nunca recibía el del servidor: cada máquina
inventaba el suyo y la licencia comprada no validaba nunca. El mensaje que
veía el cliente era "Licencia inválida — revisá que la copiaste completa",
culpándolo a él por un token perfectamente válido.

Se arregló con firma asimétrica (RS256): la privada vive solo en el servidor
de ventas, la pública viaja en el programa (`backend_venta/licencia_clave.py`)
y publicarla no habilita nada. La alternativa —meter el secreto HS256 en el
.exe— funcionaba y abría otro agujero: con HS256 la clave que verifica es la
misma que firma, así que quien la extrajera del binario se emitía las
licencias que quisiera.

Estos tests cubren las dos mitades y el cruce entre lenguajes, que es donde
vivía el bug: Node firma en producción, Python valida en la máquina del
cliente, y nadie los había hecho hablar sin secreto compartido.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend_venta import licencia_clave as kclave  # noqa: E402
from backend_venta import licencias as klic  # noqa: E402


@pytest.fixture(scope="module")
def par_de_claves():
    """Un par nuevo, y la pública parcheada como si fuera la del release."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = k.private_bytes(serialization.Encoding.PEM,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


@pytest.fixture()
def instalacion_limpia(tmp_path, monkeypatch):
    """Una copia recién instalada: sin secreto, sin variables, sin nada.

    Es la situación exacta del cliente que acaba de correr el .exe — y la que
    hacía fallar la activación."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("KOBRA_LICENSE_SECRET", raising=False)
    monkeypatch.delenv("KOBRA_LICENSE_PRIVATE_KEY", raising=False)
    import importlib

    from kobra import config as kconfig
    importlib.reload(kconfig)
    importlib.reload(klic)
    yield
    monkeypatch.undo()
    importlib.reload(kconfig)
    importlib.reload(klic)


def test_la_licencia_comprada_activa_en_una_instalacion_limpia(
        par_de_claves, instalacion_limpia, monkeypatch):
    """El caso que estaba roto, de punta a punta."""
    priv, pub = par_de_claves
    monkeypatch.setattr(kclave, "PUBLICA", pub)

    # El servidor de ventas firma con la privada.
    monkeypatch.setenv("KOBRA_LICENSE_PRIVATE_KEY", priv)
    token = klic.emitir_licencia("cliente-001", "pro", dias=365)
    monkeypatch.delenv("KOBRA_LICENSE_PRIVATE_KEY")

    # La máquina del cliente valida sin tener absolutamente nada configurado.
    r = klic.licencia_activa(token)
    assert r["ok"], r["error"]
    assert r["claims"]["plan"] == "pro"
    assert r["claims"]["cupo_mensual"] == 1000


def test_una_licencia_firmada_con_otra_clave_no_entra(
        par_de_claves, instalacion_limpia, monkeypatch):
    """Si esto no cortara, cualquiera se emite un enterprise perpetuo."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    _, pub = par_de_claves
    monkeypatch.setattr(kclave, "PUBLICA", pub)

    otra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    falsa = otra.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption()).decode()
    monkeypatch.setenv("KOBRA_LICENSE_PRIVATE_KEY", falsa)
    token = klic.emitir_licencia("pirata", "enterprise", dias=3650)
    monkeypatch.delenv("KOBRA_LICENSE_PRIVATE_KEY")

    assert not klic.licencia_activa(token)["ok"]


def test_el_camino_hosted_con_secreto_compartido_sigue_andando(
        instalacion_limpia, monkeypatch):
    """En hosted el mismo proceso emite y valida, así que HS256 alcanza y no
    hay que desplegar ninguna clave. Ese camino no se rompe."""
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", "secreto-compartido-de-prueba")
    import importlib
    importlib.reload(klic)
    token = klic.emitir_licencia("hosted-001", "basico")
    assert klic.licencia_activa(token)["ok"]


def test_la_clave_publica_del_repositorio_es_una_clave_valida():
    """Un PEM cortado o mal pegado deja el programa sin poder validar NADA, y
    el síntoma es idéntico al bug original."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    clave = load_pem_public_key(kclave.PUBLICA.encode())
    assert clave.key_size >= 2048, "clave demasiado corta para firmar licencias"


def test_la_privada_no_esta_en_el_repositorio():
    """La pública se publica a propósito; la privada emite licencias.

    El patrón se arma partido —`"BEGIN " + "PRIVATE" + " KEY"`— y no escrito de
    una: si estuviera entero, este archivo lo contendría y `git grep` se
    encontraría a sí mismo. Ya pasó dos veces en este repo (el test de datos
    personales y el de CORS), las dos con CI en rojo por un test que buscaba lo
    que él mismo decía. Acá lo agarró el hook de pre-push antes de subirlo.
    """
    patron = "BEGIN " + "PRIVATE" + " KEY"
    salida = subprocess.run(["git", "grep", "-l", patron], cwd=ROOT,
                            capture_output=True, text=True)
    hallazgos = [ln for ln in salida.stdout.split() if ln != "tests/" + os.path.basename(__file__)]
    assert not hallazgos, f"hay una clave privada versionada: {hallazgos}"


# ---------------------------------------------------------------------------
# El cruce entre lenguajes, que es donde vivía el bug
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node")
def test_lo_que_firma_node_lo_valida_python(par_de_claves, instalacion_limpia,
                                            monkeypatch, tmp_path):
    """En producción firma `api/_license.js` y valida PyJWT. Que cada mitad
    ande por su cuenta no dice nada: el bug era justamente que no se entendían.
    """
    priv, pub = par_de_claves
    monkeypatch.setattr(kclave, "PUBLICA", pub)

    guion = tmp_path / "firmar.mjs"
    guion.write_text(
        "import { createRequire } from 'module';\n"
        f"const require = createRequire('{ROOT}/');\n"
        "const { sign } = require('./api/_license.js');\n"
        "process.stdout.write(sign({ plan: 'starter', email: 'cliente@ejemplo.invalid',"
        " pid: '12345' }, null));\n", encoding="utf-8")

    r = subprocess.run(["node", str(guion)], cwd=ROOT, capture_output=True,
                       text=True, env={**os.environ,
                                       "KOBRA_LICENSE_PRIVATE_KEY": priv})
    assert r.returncode == 0, f"Node no pudo firmar:\n{r.stderr}"
    token = r.stdout.strip()

    import jwt
    assert jwt.get_unverified_header(token)["alg"] == "RS256", \
        "Node no está firmando con la clave asimétrica"

    validada = klic.licencia_activa(token)
    assert validada["ok"], (
        f"Python no valida lo que firma Node: {validada['error']}. Ese es "
        "exactamente el bug que dejaba afuera a todo el que pagaba.")
    assert validada["claims"]["plan"] == "starter"
    assert validada["claims"]["sub"] == "cliente@ejemplo.invalid"


@pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node")
def test_node_sin_clave_privada_sigue_firmando_hs256(tmp_path):
    """Hasta que la privada esté cargada en Vercel, el deploy actual tiene que
    seguir emitiendo. Un arreglo que deja de emitir licencias mientras se
    configura es peor que el bug."""
    guion = tmp_path / "firmar_hs.mjs"
    guion.write_text(
        "import { createRequire } from 'module';\n"
        f"const require = createRequire('{ROOT}/');\n"
        "const { sign, verify } = require('./api/_license.js');\n"
        "const t = sign({ plan: 'basico', pid: '1' }, 'secreto-de-prueba');\n"
        "process.stdout.write(JSON.stringify({ alg: JSON.parse("
        "Buffer.from(t.split('.')[0], 'base64').toString()).alg,"
        " ok: !!verify(t, 'secreto-de-prueba') }));\n", encoding="utf-8")
    entorno = {k: v for k, v in os.environ.items()
               if k != "KOBRA_LICENSE_PRIVATE_KEY"}
    r = subprocess.run(["node", str(guion)], cwd=ROOT, capture_output=True,
                       text=True, env=entorno)
    assert r.returncode == 0, r.stderr
    datos = json.loads(r.stdout)
    assert datos["alg"] == "HS256" and datos["ok"], datos
