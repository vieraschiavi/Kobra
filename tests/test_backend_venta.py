"""
Tests del backend de venta (licencias JWT + gateway medido + descargas +
webhook de pago). Ver backend_venta/app.py.
"""
import importlib

import jwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Aísla config (licencia/secretos) y base de uso en un tmp_path por test."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_USO_DB", str(tmp_path / "uso.db"))
    monkeypatch.delenv("KOBRA_LICENSE_SECRET", raising=False)
    monkeypatch.delenv("KOBRA_BACKEND_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MP_ACCESS_TOKEN", raising=False)

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from backend_venta import descargas, licencias, uso
    importlib.reload(licencias)
    importlib.reload(uso)
    importlib.reload(descargas)
    from backend_venta import app as app_mod
    importlib.reload(app_mod)
    return app_mod, licencias, uso, descargas


def test_licencia_roundtrip(entorno):
    app_mod, licencias, uso, descargas = entorno
    tok = licencias.emitir_licencia("cliente@mail.com", "pro")
    claims = licencias.validar_licencia(tok)
    assert claims["sub"] == "cliente@mail.com"
    assert claims["plan"] == "pro"
    assert claims["cupo_mensual"] == licencias.PLANES["pro"]["cupo_mensual"]
    assert "copiloto" in claims["features"]


def test_plan_basico_entrada_mensual(entorno):
    # Plan de entrada: US$99/mes, 300 gestiones, mensual (30 días). El precio se
    # realineó al ancla del mercado LATAM (Moonflow: US$79 el plan de entrada,
    # US$399/499 los superiores, con tokens de IA facturados aparte).
    app_mod, licencias, uso, descargas = entorno
    cfg = licencias.PLANES["basico"]
    assert cfg["precio"] == 99.0 and cfg["cupo_mensual"] == 300 and cfg["dias"] == 30
    tok = licencias.emitir_licencia("pyme@mail.com", "basico")
    claims = licencias.validar_licencia(tok)
    assert claims["plan"] == "basico" and claims["cupo_mensual"] == 300
    # sin "excedente" (ese beneficio queda para Pro en adelante)
    assert "excedente" not in claims["features"]


def test_licencia_invalida_no_valida(entorno):
    app_mod, licencias, uso, descargas = entorno
    with pytest.raises(jwt.PyJWTError):
        licencias.validar_licencia("esto.no.es_un_jwt_valido")
    r = licencias.licencia_activa("token-basura")
    assert r["ok"] is False and "licencia_invalida" in r["error"]


def test_emitir_requiere_admin_token(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    r = client.post("/licencias/emitir", json={"cliente_id": "x", "plan": "pro"},
                    headers={"Authorization": "Bearer incorrecto"})
    assert r.status_code == 403

    admin_tok = app_mod._admin_token()
    r = client.post("/licencias/emitir", json={"cliente_id": "x", "plan": "pro"},
                    headers={"Authorization": f"Bearer {admin_tok}"})
    assert r.status_code == 200
    assert "licencia" in r.json()


def test_gateway_rechaza_licencia_invalida(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    r = client.get("/licencias/estado", headers={"Authorization": "Bearer no-existe"})
    assert r.status_code == 401


def test_gateway_claude_sin_key_da_503(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("cliente@mail.com", "pro")
    r = client.post("/gateway/claude", json={"texto": "hola"},
                    headers={"Authorization": f"Bearer {lic}"})
    assert r.status_code == 503


def test_gateway_tts_requiere_feature_voz_premium(entorno):
    """"voz_premium" (ElevenLabs) no viene en ningún plan por default — a
    diferencia de "voz" (Twilio/Polly), tiene costo real por uso."""
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("cliente@mail.com", "enterprise")
    r = client.post("/gateway/tts", json={"texto": "hola", "voice_id": "v1"},
                    headers={"Authorization": f"Bearer {lic}"})
    assert r.status_code == 403


def test_gateway_tts_sin_key_da_503(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("cliente@mail.com", "pro",
                                    features=[*licencias.PLANES["pro"]["features"], "voz_premium"])
    r = client.post("/gateway/tts", json={"texto": "hola", "voice_id": "v1"},
                    headers={"Authorization": f"Bearer {lic}"})
    assert r.status_code == 503


def test_gateway_tts_ok_registra_uso_y_costo(entorno, monkeypatch):
    app_mod, licencias, uso, descargas = entorno
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-fake-000111")

    from kobra import voz_tts
    monkeypatch.setattr(voz_tts, "sintetizar", lambda texto, voice_id, api_key=None:
                        {"ok": True, "audio": b"\x00\x01audio-falso", "caracteres": len(texto),
                         "costo_est_usd": voz_tts.costo_estimado_usd(texto), "error": None})

    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("cliente@mail.com", "pro",
                                    features=[*licencias.PLANES["pro"]["features"], "voz_premium"])
    r = client.post("/gateway/tts", json={"texto": "Hola, ¿cómo está?", "voice_id": "v1"},
                    headers={"Authorization": f"Bearer {lic}"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and data["caracteres"] == len("Hola, ¿cómo está?")
    assert data["costo_est_usd"] > 0

    resumen = uso.uso_mes("cliente@mail.com")
    assert resumen["unidades"] == len("Hola, ¿cómo está?")
    assert resumen["costo_est"] > 0


def test_gateway_no_implementado_da_501(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("cliente@mail.com", "pro")
    for ruta in ("/gateway/twilio", "/gateway/whatsapp"):
        r = client.post(ruta, json={}, headers={"Authorization": f"Bearer {lic}"})
        assert r.status_code == 501


def test_cupo_agotado_bloquea_antes_que_el_501(entorno):
    """El chequeo de cupo corre antes que la lógica del endpoint: un plan sin
    cupo restante debe dar 402, incluso en un gateway todavía no implementado."""
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("cliente@mail.com", "trial")
    cupo = licencias.validar_licencia(lic)["cupo_mensual"]
    for _ in range(cupo):
        uso.registrar_uso("cliente@mail.com", canal="claude", unidades=1)
    r = client.post("/gateway/twilio", json={}, headers={"Authorization": f"Bearer {lic}"})
    assert r.status_code == 402


def test_plan_enterprise_sin_tope_no_bloquea_por_cupo(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    lic = licencias.emitir_licencia("banco@mail.com", "enterprise", cupo_mensual=None)
    for _ in range(500):
        uso.registrar_uso("banco@mail.com", canal="claude", unidades=1)
    r = client.post("/gateway/twilio", json={}, headers={"Authorization": f"Bearer {lic}"})
    assert r.status_code == 501  # no da 402: pasó el chequeo de cupo


def test_uso_mes_agrega_correctamente(entorno):
    app_mod, licencias, uso, descargas = entorno
    uso.registrar_uso("c1", canal="claude", tok_in=100, tok_out=50, costo_est=0.01)
    uso.registrar_uso("c1", canal="claude", tok_in=200, tok_out=80, costo_est=0.02)
    resumen = uso.uso_mes("c1")
    assert resumen["gestiones"] == 2
    assert resumen["tok_in"] == 300
    assert resumen["tok_out"] == 130
    assert round(resumen["costo_est"], 2) == 0.03


def test_token_descarga_un_solo_uso(entorno):
    app_mod, licencias, uso, descargas = entorno
    tok = descargas.crear_token_descarga("cliente@mail.com")
    r1 = descargas.validar_token_descarga(tok)
    assert r1["ok"] is True and r1["cliente_id"] == "cliente@mail.com"
    r2 = descargas.validar_token_descarga(tok)
    assert r2["ok"] is False and r2["error"] == "token_ya_usado"


def test_token_descarga_inexistente(entorno):
    app_mod, licencias, uso, descargas = entorno
    r = descargas.validar_token_descarga("no-existe")
    assert r["ok"] is False and r["error"] == "token_no_existe"


def test_descargar_sin_token_valido_da_403(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    r = client.get("/descargar/token-que-no-existe")
    assert r.status_code == 403


def test_webhook_ignora_eventos_no_payment(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    r = client.post("/webhooks/mercadopago", json={"type": "merchant_order"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "ignorado": True}


def test_webhook_sin_mp_token_falla_controlado(entorno):
    app_mod, licencias, uso, descargas = entorno
    client = TestClient(app_mod.app)
    r = client.post("/webhooks/mercadopago", json={"type": "payment", "data": {"id": "123"}})
    assert r.status_code == 503


def test_salud():
    from backend_venta.app import app
    r = TestClient(app).get("/salud")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_cupo_concurrente_no_deja_pasar_de_mas(entorno):
    """Regresión: chequear cupo y registrar uso en pasos separados dejaba que
    pedidos concurrentes del mismo cliente pasaran el chequeo antes de que
    ninguno registrara uso — un cupo de 10 dejaba pasar 22 de 30 pedidos
    simultáneos. uso.lock_cliente() serializa check+registro por cliente."""
    import concurrent.futures
    app_mod, licencias, uso, descargas = entorno

    cliente = "cliente-cupo@mail.com"
    cupo = 10

    def intentar(i):
        with uso.lock_cliente(cliente):
            if uso.gestiones_mes(cliente) >= cupo:
                return "bloqueado"
            uso.registrar_uso(cliente, canal="claude", unidades=1)
            return "permitido"

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        resultados = list(ex.map(intentar, range(30)))

    assert resultados.count("permitido") == cupo
    assert uso.gestiones_mes(cliente) == cupo
