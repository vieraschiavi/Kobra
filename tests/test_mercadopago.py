# © 2026 Martín Viera. Todos los derechos reservados.

"""Cobrar una deuda por MercadoPago de verdad, y no dar por cobrado lo que no
se verificó.

Antes de esto, el "link de MercadoPago" del portal era un link estático (monto
fijo, y cada deudor debe algo distinto) o directamente uno simulado, y el pago
quedaba `informado` para siempre. Estos tests cubren las dos puntas nuevas: la
preferencia con el monto exacto —incluido el sandbox, que es donde se paga con
tarjetas ficticias para ensayar— y la verificación contra la API antes de
imputar.

La parte de seguridad es la que más importa: sin comparar referencia y monto,
cualquiera con un `payment_id` de un pago de $1 podría saldar una deuda de
$100.000. Ninguno de estos tests toca la red.
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import mercadopago as kmp  # noqa: E402

TOKEN_TEST = "TEST-1234567890123456-abcdef"
TOKEN_PROD = "APP_USR-1234567890123456-abcdef"


class _Resp:
    def __init__(self, datos, ok=True, status=200):
        self._d, self.ok, self.status_code = datos, ok, status
        self.content = b"x"
        self.text = str(datos)

    def json(self):
        return self._d


# --- Crear la preferencia --------------------------------------------------
def test_sin_token_no_inventa_un_link(monkeypatch):
    r = kmp.crear_preferencia("", "REF-1", 200.0, "Deuda")
    assert r["ok"] is False and "access token" in r["detalle"]


def test_monto_invalido_no_llega_a_la_api(monkeypatch):
    def _no_llamar(*a, **kw):
        pytest.fail("no debería salir a la red con un monto inválido")
    monkeypatch.setattr("requests.post", _no_llamar)
    assert kmp.crear_preferencia(TOKEN_TEST, "REF", 0, "x")["ok"] is False
    assert kmp.crear_preferencia(TOKEN_TEST, "REF", -5, "x")["ok"] is False
    assert kmp.crear_preferencia(TOKEN_TEST, "REF", "hola", "x")["ok"] is False


def test_con_credencial_de_prueba_devuelve_el_sandbox(monkeypatch):
    """Es el único checkout que acepta las tarjetas ficticias: si devolviera el
    de producción, el ensayo pediría una tarjeta real."""
    capturado = {}

    def _post(url, headers=None, json=None, timeout=None):
        capturado["json"] = json
        return _Resp({"id": "123", "init_point": "https://mp/real",
                      "sandbox_init_point": "https://mp/sandbox"})

    monkeypatch.setattr("requests.post", _post)
    r = kmp.crear_preferencia(TOKEN_TEST, "REF-9", 200.0, "Deuda 9",
                              base_url="https://demo.invalid")
    assert r["ok"] is True
    assert r["url"] == "https://mp/sandbox"
    assert r["es_prueba"] is True
    # El monto exacto de ESA deuda, y la referencia que permite verificar.
    assert capturado["json"]["items"][0]["unit_price"] == 200.0
    assert capturado["json"]["external_reference"] == "REF-9"


def test_con_credencial_de_produccion_devuelve_el_checkout_real(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _Resp(
        {"id": "1", "init_point": "https://mp/real", "sandbox_init_point": "https://mp/sandbox"}))
    r = kmp.crear_preferencia(TOKEN_PROD, "REF", 100.0, "d")
    assert r["url"] == "https://mp/real" and r["es_prueba"] is False


def test_el_retorno_automatico_solo_va_si_hay_a_donde_volver(monkeypatch):
    """MercadoPago rechaza la preferencia entera si se pide `auto_return` sin
    `back_urls`."""
    capturado = {}
    monkeypatch.setattr("requests.post", lambda url, headers=None, json=None, timeout=None:
                        (capturado.update(json=json), _Resp({"id": "1", "init_point": "u"}))[1])
    kmp.crear_preferencia(TOKEN_PROD, "R", 10.0, "d", base_url="")
    assert "auto_return" not in capturado["json"]
    kmp.crear_preferencia(TOKEN_PROD, "R", 10.0, "d", base_url="https://x.invalid")
    assert capturado["json"]["auto_return"] == "approved"
    assert "back_urls" in capturado["json"]


def test_si_mercadopago_falla_lo_dice_y_no_revienta(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _Resp(
        {"message": "invalid token"}, ok=False, status=401))
    r = kmp.crear_preferencia(TOKEN_PROD, "R", 10.0, "d")
    assert r["ok"] is False and "invalid token" in r["detalle"]


def test_si_la_red_se_cae_lo_dice_y_no_revienta(monkeypatch):
    import requests

    def _boom(*a, **kw):
        raise requests.exceptions.ConnectionError("sin red")
    monkeypatch.setattr("requests.post", _boom)
    r = kmp.crear_preferencia(TOKEN_PROD, "R", 10.0, "d")
    assert r["ok"] is False and "No se pudo hablar" in r["detalle"]


# --- Verificar el pago (la parte de seguridad) -----------------------------
def _get_pago(estado="approved", ref="REF-9", monto=200.0):
    return lambda *a, **kw: _Resp({"status": estado, "external_reference": ref,
                                   "transaction_amount": monto})


def test_pago_aprobado_que_coincide_se_acredita(monkeypatch):
    monkeypatch.setattr("requests.get", _get_pago())
    v = kmp.verificar_pago(TOKEN_TEST, "111", "REF-9", 200.0)
    assert v["aprobado"] is True and v["estado"] == "approved"


def test_un_pago_de_otra_deuda_no_salda_esta(monkeypatch):
    """Sin comparar la referencia, alcanzaría con pasar el payment_id de
    cualquier pago de $1 para dar por saldada una deuda de $100.000."""
    monkeypatch.setattr("requests.get", _get_pago(ref="REF-OTRA"))
    v = kmp.verificar_pago(TOKEN_TEST, "111", "REF-9", 200.0)
    assert v["aprobado"] is False and "otra referencia" in v["detalle"]


def test_pagar_de_menos_no_salda_el_total(monkeypatch):
    monkeypatch.setattr("requests.get", _get_pago(monto=1.0))
    v = kmp.verificar_pago(TOKEN_TEST, "111", "REF-9", 200.0)
    assert v["aprobado"] is False and "se esperaba" in v["detalle"]


def test_pagar_de_mas_si_se_acredita(monkeypatch):
    """El que paga de más no puede quedar sin acreditar."""
    monkeypatch.setattr("requests.get", _get_pago(monto=250.0))
    assert kmp.verificar_pago(TOKEN_TEST, "111", "REF-9", 200.0)["aprobado"] is True


@pytest.mark.parametrize("estado", ["pending", "in_process", "rejected", "cancelled", ""])
def test_solo_approved_se_acredita(monkeypatch, estado):
    monkeypatch.setattr("requests.get", _get_pago(estado=estado))
    assert kmp.verificar_pago(TOKEN_TEST, "111", "REF-9", 200.0)["aprobado"] is False


def test_payment_id_que_no_es_un_numero_no_sale_a_la_red(monkeypatch):
    def _no_llamar(*a, **kw):
        pytest.fail("no debería consultar la API con un payment_id inválido")
    monkeypatch.setattr("requests.get", _no_llamar)
    for malo in ("", "abc", "1 OR 1=1", "../x"):
        assert kmp.verificar_pago(TOKEN_TEST, malo, "REF")["aprobado"] is False


# --- El link del portal ----------------------------------------------------
@pytest.fixture()
def portal(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    from kobra import portal_pagos
    importlib.reload(portal_pagos)
    return portal_pagos


def test_con_access_token_el_link_es_el_checkout_real(portal, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _Resp(
        {"id": "1", "init_point": "https://mp/real", "sandbox_init_point": "https://mp/sbx"}))
    cfg = {"mercadopago": {"access_token": TOKEN_TEST, "link_base": ""}}
    assert portal.link_mercadopago(cfg, "REF-1", 200.0) == "https://mp/sbx"


def test_si_la_api_falla_cae_al_link_preconfigurado(portal, monkeypatch):
    """Quedarse sin ningún link es peor que quedarse con uno que no cobra: el
    gestor se entera recién cuando el deudor le dice que no le llegó nada."""
    monkeypatch.setattr("requests.post", lambda *a, **kw: _Resp({}, ok=False, status=500))
    cfg = {"mercadopago": {"access_token": TOKEN_TEST, "link_base": "https://mp/fijo"}}
    assert portal.link_mercadopago(cfg, "REF-1", 200.0) == \
        "https://mp/fijo?external_reference=REF-1"


def test_sin_nada_configurado_el_link_dice_que_es_simulado(portal):
    cfg = {"mercadopago": {"access_token": "", "link_base": ""}}
    assert "simulado" in portal.link_mercadopago(cfg, "REF-1", 200.0)


# --- Las tarjetas de prueba ------------------------------------------------
def test_los_datos_de_prueba_traen_lo_necesario_para_pagar():
    p = kmp.datos_de_prueba("UY")
    assert p["tarjetas"] and all(t["numero"] and t["cvv"] for t in p["tarjetas"])
    assert p["titular"]["aprobar"] == "APRO"
    # Y avisan de dónde sale la verdad, porque estos valores cambian por país.
    assert "panel" in p["aviso"].lower() or "integraciones" in p["aviso"].lower()
