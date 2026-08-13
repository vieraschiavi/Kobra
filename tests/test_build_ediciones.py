# © 2026 Martín Viera. Todos los derechos reservados.
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


def test_cada_edicion_de_plan_lleva_su_cupo_firmado(tmpdist):
    """El paquete que se descarga después de pagar tiene que traer, dentro del
    token firmado, el cupo del plan que se compró — no el de otro y no ninguno.
    Antes daba lo mismo (la app instalada ignoraba `cupo_mensual`); desde que
    `kobra/plan.py` lo aplica, este número ES el producto que se entrega."""
    from backend_venta import licencias as klic
    for edicion, plan in (("Basico", "basico"), ("Pro", "pro"),
                          ("Starter", "starter"), ("Enterprise", "enterprise")):
        z = br.build_edicion(tmpdist, edicion)
        _n, ed, _l = _leer_zip(z)
        claims = klic.validar_licencia(ed["token"], secreto=ed["secreto"])
        assert claims["plan"] == plan, edicion
        assert claims["cupo_mensual"] == klic.PLANES[plan]["cupo_mensual"], edicion
        # Y el mismo valor tiene que quedar visible en edicion.json, que es lo
        # que mira quien audita el paquete sin decodificar el JWT.
        assert ed["cupo_mensual"] == klic.PLANES[plan]["cupo_mensual"], edicion


def test_el_paquete_basico_no_es_el_mismo_que_el_pro(tmpdist):
    """La comprobación de punta a punta de lo que se vende: dos compras
    distintas producen dos paquetes con distinto producto adentro."""
    from backend_venta import licencias as klic
    _n, ed_b, _l = _leer_zip(br.build_edicion(tmpdist, "Basico"))
    _n, ed_p, _l = _leer_zip(br.build_edicion(tmpdist, "Pro"))
    cb = klic.validar_licencia(ed_b["token"], secreto=ed_b["secreto"])
    cp = klic.validar_licencia(ed_p["token"], secreto=ed_p["secreto"])
    assert cb["cupo_mensual"] < cp["cupo_mensual"]
    assert "excedente" not in cb["features"] and "excedente" in cp["features"]


def test_el_zip_lleva_la_interfaz_recien_compilada(tmpdist):
    """El instalador .exe compila el frontend en cada corrida; estos ZIP se
    servían del build commiteado en `owner/ui_dist`. Si alguien tocaba la
    interfaz y no se acordaba de recopiarlo a mano, el cliente que baja el ZIP
    veía una app distinta de la del instalador — el mismo producto con dos
    caras. Cuando hay build fresco de Vite, ese es el que viaja."""
    fresco = os.path.join(ROOT, "webapp", "frontend", "dist", "index.html")
    if not os.path.exists(fresco):
        pytest.skip("no hay build de Vite en esta máquina (falta `npm run build`)")
    z = br.build_edicion(tmpdist, "Demo")
    with zipfile.ZipFile(z) as zf:
        empaquetado = zf.read("kobra_software/owner/ui_dist/index.html").decode("utf-8")
    with open(fresco, encoding="utf-8") as f:
        assert empaquetado == f.read(), "el ZIP viaja con una interfaz vieja"
