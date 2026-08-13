# © 2026 Martín Viera. Todos los derechos reservados.

"""Desbloqueo de la copia del dueño con `mail|codigo` (kobra/owner.py).

Hasta acá ser "owner" era una decisión de BUILD: el ZIP de la edición Owner
traía `edicion.json` con `owner: true` y el launcher exportaba `KOBRA_OWNER=1`.
Desde el instalador público (`MVKobraAI_Setup.exe`) no había forma de llegar a
ese modo.

Pedido: «una versión owner 100% operativa solo poniendo el mail». El problema
es que el instalador del dueño y el del cliente son el MISMO binario: si
alcanzara con el mail —que además está en los commits de este repo y es un
Gmail real— cualquiera que lo baje se queda con el producto completo gratis y
los planes pagos dejan de tener sentido. Por eso el mail identifica y el código
autentica.

Lo que se blinda acá:
  * que la credencial correcta desbloquee de verdad, y quede persistida;
  * que ninguna variante cercana (mail solo, código mal, mail mal) pase;
  * que el código en claro NO esté en el repositorio;
  * que tantear el código cueste lo mismo que tantear una licencia (freno por IP).
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import owner as kowner  # noqa: E402

# El código de verdad no puede vivir en el repo. Para los tests se usa uno
# propio, derivado igual, inyectado sobre el módulo.
CODIGO_PRUEBA = "TEST1-TEST2-TEST3-TEST4-TEST5"


@pytest.fixture()
def credencial(monkeypatch):
    """Reemplaza sal+hash por los de un código de prueba conocido."""
    import hashlib
    import secrets
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(CODIGO_PRUEBA.encode(), salt=sal, n=kowner._N,
                       r=kowner._R, p=kowner._P, dklen=kowner._DKLEN,
                       maxmem=kowner._MAXMEM)
    monkeypatch.setattr(kowner, "_SAL", sal)
    monkeypatch.setattr(kowner, "_HASH", h)
    return f"{kowner.EMAIL}|{CODIGO_PRUEBA}"


# --- La credencial ----------------------------------------------------------
def test_la_credencial_correcta_verifica(credencial):
    assert kowner.verificar(credencial) is True


def test_tolera_mayusculas_y_espacios(credencial):
    """Un mail copiado de un mail o del gestor de contraseñas viene con
    espacios y a veces capitalizado. Rechazarlo por eso sería un bug de UX
    disfrazado de seguridad."""
    assert kowner.verificar(f"  {kowner.EMAIL.upper()} | {CODIGO_PRUEBA} ") is True


@pytest.mark.parametrize("texto,caso", [
    ("vieraschiavi@gmail.com", "solo el mail, sin código"),
    ("vieraschiavi@gmail.com|", "código vacío"),
    ("|TEST1-TEST2-TEST3-TEST4-TEST5", "mail vacío"),
    ("otro@gmail.com|TEST1-TEST2-TEST3-TEST4-TEST5", "código bien, mail ajeno"),
    ("vieraschiavi@gmail.com|TEST1-TEST2-TEST3-TEST4-TEST6", "un carácter mal"),
    ("", "vacío"),
    ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def", "token de licencia normal"),
])
def test_lo_que_no_es_la_credencial_no_pasa(credencial, texto, caso):
    """El primero es el caso del pedido original: si «solo el mail» alcanzara,
    el producto sería gratis para quien lo conozca."""
    assert kowner.verificar(texto) is False, caso


def test_un_token_de_licencia_no_se_confunde_con_la_credencial():
    """`partir()` devuelve None en vez de lanzar, para que el llamador siga
    tratándolo como lo que es: una licencia."""
    assert kowner.partir("eyJhbGciOiJIUzI1NiJ9.payload.firma") is None


# --- Lo que NO puede estar en el repositorio --------------------------------
def test_el_codigo_en_claro_no_esta_en_el_repositorio():
    """El hash y la sal son publicables; el código no. Si alguien lo pega en
    un comentario, un README o un test, la barrera desaparece."""
    r = subprocess.run(
        ["git", "grep", "-I", "-l", "-E", "[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}"],
        cwd=ROOT, capture_output=True, text=True)
    archivos = [f for f in r.stdout.splitlines() if f and f != "tests/test_owner_desbloqueo.py"]
    assert not archivos, f"hay algo con forma de codigo owner en: {archivos}"


def test_el_hash_no_es_el_codigo_ni_el_mail():
    """Guardar el código «hasheado» con algo reversible (o el mail) no
    protegería nada."""
    import hashlib
    assert kowner._HASH != hashlib.sha256(kowner.EMAIL.encode()).digest()
    assert len(kowner._HASH) == 32 and len(kowner._SAL) == 16


def test_usa_una_derivacion_lenta_y_no_un_hash_rapido():
    """Con sha256 pelado, probar candidatos contra el hash publicado es
    barato. scrypt lo hace caro en tiempo Y memoria."""
    import inspect
    fuente = inspect.getsource(kowner._derivar)
    assert "scrypt" in fuente
    assert kowner._N >= 2 ** 14, "el costo de scrypt quedó demasiado bajo"


def test_compara_en_tiempo_constante():
    """Con `==`, el tiempo de respuesta filtra cuántos bytes coincidieron y
    permite reconstruir el hash byte a byte."""
    import inspect
    fuente = inspect.getsource(kowner.verificar)
    assert "compare_digest" in fuente
    assert "_derivar(codigo) == _HASH" not in fuente


# --- Integración con la app -------------------------------------------------
def _app(tmp_path, monkeypatch, owner_env=False):
    """Recarga la app standalone con datos Y CONFIG limpios.

    `KOBRA_CONFIG_DIR` además de `KOBRA_DATA_DIR`: el flag de owner se
    persiste con `kconfig.guardar_extra`, que escribe en `~/.kobra` y no bajo
    la carpeta de datos. Sin aislarlo, un test que desbloquea owner deja el
    flag puesto en la config REAL de quien corre la suite — pasó — y el
    siguiente test lo ve activado y pasa por el motivo equivocado.
    """
    for k in list(sys.modules):
        if k.startswith(("webapp", "kobra")):
            del sys.modules[k]
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    if owner_env:
        monkeypatch.setenv("KOBRA_OWNER", "1")
    else:
        monkeypatch.delenv("KOBRA_OWNER", raising=False)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    return api, TestClient(api.app)


def test_sin_desbloquear_la_app_pide_licencia(tmp_path, monkeypatch):
    api, cli = _app(tmp_path, monkeypatch)
    e = cli.get("/api/licencia/estado").json()
    assert e["standalone"] is True
    assert not e.get("owner")


def test_la_credencial_desbloquea_desde_el_campo_de_licencia(tmp_path, monkeypatch):
    """El mismo campo donde un cliente pega su licencia: así el desbloqueo
    funciona en el instalador público sin agregar una pantalla que un cliente
    no debería ver."""
    api, cli = _app(tmp_path, monkeypatch)
    import hashlib
    import secrets
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(CODIGO_PRUEBA.encode(), salt=sal, n=api.kowner._N,
                       r=api.kowner._R, p=api.kowner._P,
                       dklen=api.kowner._DKLEN, maxmem=api.kowner._MAXMEM)
    monkeypatch.setattr(api.kowner, "_SAL", sal)
    monkeypatch.setattr(api.kowner, "_HASH", h)

    r = cli.post("/api/licencia/activar",
                 json={"token": f"{api.kowner.EMAIL}|{CODIGO_PRUEBA}"})
    assert r.status_code == 200, r.text
    assert r.json()["owner"] is True and r.json()["rol"] == "admin"

    # Y queda persistido: el estado ya reporta owner sin volver a activar.
    assert cli.get("/api/licencia/estado").json()["owner"] is True


def test_una_credencial_equivocada_no_desbloquea(tmp_path, monkeypatch):
    api, cli = _app(tmp_path, monkeypatch)
    r = cli.post("/api/licencia/activar",
                 json={"token": f"{api.kowner.EMAIL}|NO-ES-EL-CODIGO"})
    assert r.status_code == 400
    assert cli.get("/api/licencia/estado").json().get("owner") is not True


def test_tantear_el_codigo_esta_frenado_por_ip(tmp_path, monkeypatch):
    """El código es la única barrera entre un cliente y el producto completo:
    probarlo tiene que costar lo mismo que probar una licencia."""
    api, cli = _app(tmp_path, monkeypatch)
    codigos = [429]
    for i in range(40):
        r = cli.post("/api/licencia/activar", json={"token": f"x@y.com|INTENTO-{i}"})
        codigos.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codigos, "se puede tantear el codigo sin freno"


def test_el_env_del_launcher_sigue_funcionando(tmp_path, monkeypatch):
    """La edición Owner que se arma por build no cambia: sigue entrando sola."""
    api, cli = _app(tmp_path, monkeypatch, owner_env=True)
    assert cli.get("/api/licencia/estado").json()["owner"] is True
    assert cli.post("/api/licencia/owner-login").status_code == 200
