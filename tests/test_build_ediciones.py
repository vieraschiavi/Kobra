"""Tests del empaquetado por edición (packaging/build_release.py::build_edicion):
Demo con límite de días, Owner sin límites y una edición por plan — cada una con
su licencia embebida (o flag owner), launcher en la raíz y SIN precios en la
documentación. También el hook del launcher que activa la edición al arrancar."""
import importlib.util
import json
import os
import sys
import tempfile
import time
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _load(nombre, rel):
    """Carga un módulo de packaging/ por ruta (el nombre 'packaging' choca con
    el paquete pip homónimo, así que no se puede importar por dotted-path)."""
    spec = importlib.util.spec_from_file_location(nombre, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


br = _load("br_build_release", "packaging/build_release.py")
kl = _load("kl_launcher", "packaging/kobra_launcher.py")


@pytest.fixture()
def tmpdist():
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _leer_zip(z):
    with zipfile.ZipFile(z) as zf:
        n = zf.namelist()
        ed = json.loads(zf.read("kobra_software/edicion.json"))
        leeme = zf.read(next(x for x in n if x.endswith("LEEME.txt"))).decode("utf-8-sig")
    return n, ed, leeme


def test_demo_tiene_limite_de_dias_y_sin_precio(tmpdist):
    from backend_venta import licencias as klic
    z = br.build_edicion(tmpdist, "Demo")
    nombres, ed, leeme = _leer_zip(z)
    assert ed["plan"] == "trial" and ed["dias"] == br.DEMO_DIAS and ed["owner"] is False
    # Launcher en la raíz + UI compilada incluida (corre sin Node).
    assert "kobra_software/kobra_launcher.py" in nombres
    assert "kobra_software/owner/ui_dist/index.html" in nombres
    # La licencia embebida valida y vence en DEMO_DIAS días.
    claims = klic.validar_licencia(ed["token"], secreto=ed["secreto"])
    assert claims["plan"] == "trial"
    assert round((claims["exp"] - time.time()) / 86400) == br.DEMO_DIAS
    # Sin precios en la documentación.
    assert "US$" not in leeme and "precio" not in leeme.lower()


def test_owner_sin_limites_ni_token(tmpdist):
    z = br.build_edicion(tmpdist, "Owner")
    _n, ed, leeme = _leer_zip(z)
    assert ed["owner"] is True and ed.get("token") is None
    assert "sin límite" in leeme.lower()


def test_cada_plan_lleva_sus_features(tmpdist):
    from backend_venta import licencias as klic
    z = br.build_edicion(tmpdist, "Enterprise")
    _n, ed, _l = _leer_zip(z)
    claims = klic.validar_licencia(ed["token"], secreto=ed["secreto"])
    assert claims["plan"] == "enterprise"
    # Enterprise habilita white_label y sso; la demo/básico no.
    assert "white_label" in claims["features"] and "sso" in claims["features"]


def test_launcher_activa_owner(tmp_path):
    (tmp_path / "edicion.json").write_text(json.dumps({"edition": "Owner", "owner": True}))
    os.environ.pop("KOBRA_OWNER", None)
    kl._activar_edicion(str(tmp_path))
    assert os.environ.get("KOBRA_OWNER") == "1"
    os.environ.pop("KOBRA_OWNER", None)


def test_launcher_siembra_licencia_demo_idempotente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    import secrets

    from backend_venta import licencias as klic
    secreto = secrets.token_hex(32)
    token = klic.emitir_licencia("edicion-demo", "trial", dias=14, secreto=secreto)
    (tmp_path / "edicion.json").write_text(json.dumps(
        {"edition": "Demo", "plan": "trial", "dias": 14, "owner": False,
         "secreto": secreto, "token": token}))
    monkeypatch.delenv("KOBRA_LICENSE_SECRET", raising=False)

    kl._activar_edicion(str(tmp_path))
    assert os.environ.get("KOBRA_LICENSE_SECRET") == secreto
    assert kconfig.leer_extra("LICENCIA_TOKEN") == token
    # No pisa un token ya activado por el usuario.
    kconfig.guardar_extra("LICENCIA_TOKEN", "ACTIVADO_POR_USUARIO")
    kl._activar_edicion(str(tmp_path))
    assert kconfig.leer_extra("LICENCIA_TOKEN") == "ACTIVADO_POR_USUARIO"
    monkeypatch.delenv("KOBRA_LICENSE_SECRET", raising=False)
