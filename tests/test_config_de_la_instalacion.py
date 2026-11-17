# © 2026 Martín Viera. Todos los derechos reservados.

"""Lo que es UNO por instalación lo toca solo el admin de la instalación.

Revisión de producción, hosted multi-empresa: con `solo_admin` a secas, el
admin de CUALQUIER empresa podía

  * dar de alta una empresa nueva y llevarse 2000 deudores de la cartera REAL
    de la principal (el alta copiaba `_scored(principal)`, que en modo real es
    la cartera importada),
  * pisar las claves de Twilio/LLM y el proveedor de IA de todo el despliegue,
  * cambiar el destino del informe semanal — y el lunes el informe ejecutivo
    de la principal le llegaba a él,
  * mover la carpeta de datos del servidor.

Y el alta dejaba empresas sin puerta: validaba la contraseña DESPUÉS de crear
la carpeta, así que una contraseña corta dejaba la empresa creada sin
credencial y el reintento chocaba con "ya existe".
"""
import os
import sys
import tempfile

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def instalacion(monkeypatch):
    pytest.importorskip("fastapi")
    base = tempfile.mkdtemp()
    monkeypatch.setenv("KOBRA_DATA_DIR", base)
    monkeypatch.setenv("KOBRA_CONFIG_DIR", os.path.join(base, "cfg"))
    monkeypatch.delenv("KOBRA_MODO_STANDALONE", raising=False)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    previos = {k: v for k, v in sys.modules.items() if k.startswith(("kobra", "webapp"))}
    for m in previos:
        del sys.modules[m]

    from fastapi.testclient import TestClient

    from webapp.backend import api

    # Demo sintética de la principal: menos de 2000 filas a propósito (antes,
    # `sample(n=2000)` sobre una cartera chica era un 500).
    demo = pd.DataFrame({"id_deudor": [f"KB-{i:06d}" for i in range(50)],
                         "segmento": "Retail", "monto_deuda": 1000.0, "dias_mora": 30,
                         "cuotas_atrasadas": 1, "probpago": 0.5})
    ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    demo.to_csv(ruta, index=False)

    def token(empresa, rol="admin"):
        return {"Authorization": f"Bearer {api._emitir_token(rol, empresa)}"}

    yield api, TestClient(api.app), token
    for m in [k for k in sys.modules if k.startswith(("kobra", "webapp"))]:
        del sys.modules[m]
    sys.modules.update(previos)


def test_el_alta_nunca_copia_la_cartera_real_de_la_principal(instalacion, monkeypatch):
    api, cli, token = instalacion
    # La principal en modo real: `_scored` devuelve su cartera importada.
    real = pd.DataFrame({"id_deudor": ["REAL-1", "REAL-2"], "monto_deuda": [5e5, 7e5]})
    monkeypatch.setattr(api, "_scored", lambda empresa: real)

    r = cli.post("/api/tenant/alta", json={"empresa": "nueva-sa", "password": "clave-larga-1"},
                 headers=token(api.EMPRESA_DEFAULT))
    assert r.status_code == 200, r.text
    assert r.json()["deudores"] == 50
    copiada = pd.read_csv(os.path.join(api._dir_tenant("nueva-sa"), "kobra_scored.csv"))
    assert copiada["id_deudor"].str.startswith("KB-").all(), "se copiaron deudores reales"


def test_el_admin_de_otra_empresa_no_da_de_alta_empresas(instalacion):
    api, cli, token = instalacion
    r = cli.post("/api/tenant/alta", json={"empresa": "espia", "password": "clave-larga-1"},
                 headers=token("cliente-a"))
    assert r.status_code == 403
    assert not os.path.exists(api._dir_tenant("espia"))


def test_una_contrasena_corta_no_deja_una_empresa_sin_puerta(instalacion):
    api, cli, token = instalacion
    h = token(api.EMPRESA_DEFAULT)
    r = cli.post("/api/tenant/alta", json={"empresa": "acme", "password": "corta"}, headers=h)
    assert r.status_code == 400
    assert not os.path.exists(api._dir_tenant("acme")), "quedó la carpeta sin credencial"
    r = cli.post("/api/tenant/alta", json={"empresa": "acme", "password": "clave-larga-1"},
                 headers=h)
    assert r.status_code == 200, r.text
    login = cli.post("/api/auth/login", json={"password": "clave-larga-1", "empresa": "acme"})
    assert login.status_code == 200


@pytest.mark.parametrize("metodo, ruta, cuerpo", [
    ("get", "/api/config/estado", None),
    ("post", "/api/config", {"claves": {"TWILIO_AUTH_TOKEN": "pisado-por-otro"}}),
    ("get", "/api/config/proveedor_ia", None),
    ("post", "/api/config/proveedor_ia", {"proveedor": "openai"}),
    ("get", "/api/informe/programacion", None),
    ("post", "/api/informe/programacion", {"activo": True, "destino": "x@otra.com"}),
    ("post", "/api/informe/enviar-ahora", None),
    ("get", "/api/almacenamiento", None),
    ("post", "/api/almacenamiento", {"carpeta": "/tmp/otra"}),
    ("post", "/api/marca", {"nombre": "Otra"}),
    ("get", "/api/voz/clonada", None),
])
def test_lo_global_no_lo_toca_el_admin_de_otra_empresa(instalacion, metodo, ruta, cuerpo):
    api, cli, token = instalacion
    kwargs = {"headers": token("cliente-a")}
    if cuerpo is not None:
        kwargs["json"] = cuerpo
    r = getattr(cli, metodo)(ruta, **kwargs)
    assert r.status_code == 403, (ruta, r.status_code, r.text)
    assert "administrador de la instalación" in r.json()["detail"]


def test_el_destino_del_informe_sigue_siendo_el_de_la_principal(instalacion):
    api, cli, token = instalacion
    h = token(api.EMPRESA_DEFAULT)
    assert cli.post("/api/informe/programacion",
                    json={"activo": True, "destino": "gerencia@principal.com"},
                    headers=h).status_code == 200
    cli.post("/api/informe/programacion", json={"activo": True, "destino": "x@otra.com"},
             headers=token("cliente-a"))
    assert cli.get("/api/informe/programacion", headers=h).json()["destino"] == \
        "gerencia@principal.com"
