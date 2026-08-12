"""Tests del backend FastAPI del SaaS web (webapp/backend/api.py)."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """TestClient con config aislada y contraseñas admin/gestor propias."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    kauth.establecer_password("gestor", "GestorTest123!")

    from fastapi.testclient import TestClient

    from webapp.backend import api
    return TestClient(api.app)


def _token(cliente, password="AdminTest123!", empresa="principal"):
    r = cliente.post("/api/auth/login", json={"password": password, "empresa": empresa})
    assert r.status_code == 200, r.text
    return r.json()


def _h(tok):
    return {"Authorization": f"Bearer {tok['token']}"}


def test_api_health_sin_token(cliente):
    assert cliente.get("/api/health").json()["ok"] is True


def test_api_login_roles_y_rechazo(cliente):
    assert _token(cliente)["rol"] == "admin"
    assert _token(cliente, "GestorTest123!")["rol"] == "gestor"
    assert cliente.post("/api/auth/login", json={"password": "mala"}).status_code == 401
    assert cliente.get("/api/kpis").status_code == 401   # sin token


def test_primer_arranque_crea_admin_desde_la_webapp(tmp_path, monkeypatch):
    """Sin dashboard Streamlit (hosting): el primer arranque debe poder crear la
    contraseña de admin desde la propia webapp. Bug real: el login quedaba
    bloqueado con 409 y sin forma de crearla."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config-fresca"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    importlib.reload(kauth)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    c = TestClient(api.app)

    assert c.get("/api/auth/estado").json()["configurado"] is False
    # Login imposible antes del setup.
    assert c.post("/api/auth/login", json={"password": "loquesea"}).status_code == 409
    # Contraseña muy corta → 422.
    assert c.post("/api/auth/setup", json={"password": "123"}).status_code == 422
    # Alta OK: deja sesión iniciada.
    r = c.post("/api/auth/setup", json={"password": "MiClaveSegura1"})
    assert r.status_code == 200 and r.json()["rol"] == "admin" and "token" in r.json()
    assert c.get("/api/auth/estado").json()["configurado"] is True
    # No se puede re-configurar sin auth (evita reset del admin).
    assert c.post("/api/auth/setup", json={"password": "Otra123"}).status_code == 409
    # Y ahora el login normal funciona.
    assert c.post("/api/auth/login", json={"password": "MiClaveSegura1"}).status_code == 200


def test_standalone_no_permite_saltear_la_licencia_con_password(tmp_path, monkeypatch):
    """Regresión de un agujero que rompía el modelo de venta: en la copia
    instalada de un CLIENTE, cuando la demo vencía se podía crear una
    contraseña de admin desde el primer arranque y entrar igual, para siempre
    — el límite de días quedaba en nada. En standalone la única puerta debe
    ser la LICENCIA."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg-cliente"))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    importlib.reload(kauth)
    from fastapi.testclient import TestClient

    from backend_venta import licencias as klic
    from webapp.backend import api
    importlib.reload(api)
    c = TestClient(api.app)

    # Demo cuya licencia ya venció.
    secreto = klic.secreto_firma()
    kconfig.guardar_extra("LICENCIA_TOKEN",
                          klic.emitir_licencia("demo", "trial", dias=-1, secreto=secreto))
    assert c.get("/api/licencia/estado").json()["activa"] is False
    # La puerta por contraseña no existe en la copia del cliente.
    assert c.post("/api/auth/setup", json={"password": "CualquieraSirve1"}).status_code == 404
    assert c.post("/api/auth/login", json={"password": "CualquieraSirve1"}).status_code == 404
    # Y el front sabe que acá se entra por licencia.
    assert c.get("/api/auth/estado").json()["por_licencia"] is True


def test_owner_conserva_su_entrada_directa(tmp_path, monkeypatch):
    """La copia del dueño (owner) no se ve afectada por el cierre de arriba."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg-owner"))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.setenv("KOBRA_OWNER", "1")
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    importlib.reload(kauth)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    c = TestClient(api.app)

    assert c.post("/api/licencia/owner-login").status_code == 200
    # Y sigue pudiendo usar contraseña si quiere.
    assert c.post("/api/auth/setup", json={"password": "OwnerClave1"}).status_code == 200


def test_api_kpis_y_graficos(cliente):
    h = _h(_token(cliente))
    k = cliente.get("/api/kpis", headers=h).json()
    assert k["deudores"] > 0 and k["cartera_uyu"] > 0
    assert 0 < k["probpago_promedio"] < 1
    g = cliente.get("/api/graficos/resumen", headers=h).json()
    assert {"por_tramo", "propension", "por_segmento", "top_departamentos"} <= set(g)
    assert g["por_tramo"] and "cartera" in g["por_tramo"][0]


def test_api_cartera_filtros_paginado_y_export(cliente):
    h = _h(_token(cliente))
    r = cliente.get("/api/cartera?tamano=5&tramo=31-60", headers=h).json()
    assert r["total"] > 0 and len(r["filas"]) == 5
    assert all(f["tramo_mora"] == "31-60" for f in r["filas"])
    # orden por prioridad ascendente
    prioridades = [f["prioridad"] for f in r["filas"]]
    assert prioridades == sorted(prioridades)
    # página 2 no repite la 1
    r2 = cliente.get("/api/cartera?tamano=5&pagina=2&tramo=31-60", headers=h).json()
    assert {f["id_deudor"] for f in r["filas"]}.isdisjoint(
        {f["id_deudor"] for f in r2["filas"]})
    # export CSV respeta el filtro
    csv = cliente.get("/api/cartera/export.csv?tramo=31-60", headers=h)
    assert csv.status_code == 200 and csv.text.count("\n") - 1 == r["total"]


def test_api_cartera_busqueda_con_parentesis_no_revienta(cliente):
    """`str.contains` trata el argumento como regex por default: un usuario
    que busca algo con paréntesis desbalanceados (copiar/pegar un id raro,
    tipear sin querer) no puede tirar un 500 — es una caja de texto libre."""
    h = _h(_token(cliente))
    r = cliente.get("/api/cartera", params={"busqueda": "ID(005"}, headers=h)
    assert r.status_code == 200
    assert r.json()["total"] == 0     # ningún id_deudor real contiene ese texto


def test_api_cartera_busqueda_encuentra_el_texto_literal(cliente):
    h = _h(_token(cliente))
    primero = cliente.get("/api/cartera?tamano=1", headers=h).json()["filas"][0]["id_deudor"]
    r = cliente.get(f"/api/cartera?busqueda={primero}", headers=h).json()
    assert r["total"] >= 1
    assert any(f["id_deudor"] == primero for f in r["filas"])


def test_api_deudor_brief_y_404(cliente):
    h = _h(_token(cliente))
    primero = cliente.get("/api/cartera?tamano=1", headers=h).json()["filas"][0]["id_deudor"]
    d = cliente.get(f"/api/deudor/{primero}", headers=h).json()
    assert d["id_deudor"] == primero and "estrategia" in d
    assert cliente.get("/api/deudor/NO-EXISTE", headers=h).status_code == 404


def test_api_agenda_y_gestores(cliente):
    h = _h(_token(cliente))
    a = cliente.get("/api/agenda", headers=h).json()
    assert "total" in a and isinstance(a["vencidas"], list)
    # Limite de urgencia: nunca vuelven miles de filas (renderizarlas congela
    # la pagina); el total real se informa aparte y se ordena por monto.
    assert len(a["vencidas"]) <= 200
    assert a["mostrando"] == len(a["vencidas"])
    if a["mostrando"] >= 2:
        montos = [v.get("monto_acordado") or 0 for v in a["vencidas"][:10]]
        assert montos == sorted(montos, reverse=True)
    a5 = cliente.get("/api/agenda?limite=5", headers=h).json()
    assert len(a5["vencidas"]) <= 5 and a5["total"] == a["total"]
    g = cliente.get("/api/gestores/resumen", headers=h).json()
    assert "ranking" in g


def test_api_ayuda_ia(cliente, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    h = _h(_token(cliente))
    r = cliente.post("/api/ayuda", json={"pregunta": "¿cómo llamo por teléfono?"},
                     headers=h).json()
    assert r["modo"] == "docs" and r["fuentes"]


def test_api_config_solo_admin(cliente):
    h_gestor = _h(_token(cliente, "GestorTest123!"))
    assert cliente.get("/api/config/estado", headers=h_gestor).status_code == 403
    h_admin = _h(_token(cliente))
    estado = cliente.get("/api/config/estado", headers=h_admin).json()
    assert "ANTHROPIC_API_KEY" in estado
    r = cliente.post("/api/config", json={"claves": {"SMTP_HOST": "smtp.test.com",
                                                     "CLAVE_INVENTADA": "x"}},
                     headers=h_admin).json()
    assert r["guardadas"] == ["SMTP_HOST"]


def test_api_integracion_cartera_entrante(cliente, tmp_path):
    h = _h(_token(cliente))
    r = cliente.post("/api/integracion/cartera", json={"contactos": [
        {"nombre": "Ana", "telefono": "099111222", "deuda": 12000, "dias_mora": 40},
        {"nombre": "Sin Monto", "telefono": "099333444"},
    ]}, headers=h)
    assert r.status_code == 200
    datos = r.json()
    assert datos["recibidos"] == 2 and datos["validos"] == 1
    destino = os.path.join(ROOT, datos["archivo"])
    assert os.path.exists(destino)
    os.remove(destino)   # no ensuciar el repo
    assert cliente.post("/api/integracion/cartera", json={"contactos": []},
                        headers=h).status_code == 400


def test_api_multitenant_aislamiento(cliente):
    """Una empresa distinta a 'principal' no ve los datos del repo."""
    tok = _token(cliente, empresa="acme")
    assert tok["empresa"] == "acme"
    r = cliente.get("/api/kpis", headers=_h(tok))
    assert r.status_code == 404 and "acme" in r.json()["detail"]
