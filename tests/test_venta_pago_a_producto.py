# © 2026 Martín Viera. Todos los derechos reservados.

"""Del pago a la app: lo que recibe quien COMPRA, y en qué se diferencia del demo.

El recorrido comercial completo tiene cuatro tramos y cada uno tenía sus tests,
pero ninguno los cruzaba de punta a punta:

    checkout (api/checkout.js)  →  MercadoPago aprueba el pago
      →  api/verify-payment.js emite la licencia
      →  el cliente la pega en la app instalada (POST /api/licencia/activar)

`tests/test_licencia_puente.py` cubre el tramo Node→PyJWT y
`tests/test_licencia_standalone.py` cubre la activación por HTTP con una
licencia *trial* emitida desde Python. Lo que no cubría nadie es justo lo que
importa para vender: que la licencia que sale de un pago REAL de un plan pago
entre en la app y quede **distinta del demo**.

Estos tests corren los handlers de verdad —el de checkout y el de
verify-payment, con la API de MercadoPago mockeada— y activan el resultado
contra la app real.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-compartido-de-prueba-del-flujo-de-venta"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="requiere Node para correr los handlers reales del checkout",
)


def _pagar(plan: str, email: str = "cliente@empresa.com",
           payment_id: str = "987654321") -> dict:
    """Simula un pago APROBADO en MercadoPago y devuelve la respuesta real de
    `api/verify-payment.js` — el handler que corre en Vercel. Solo se mockea
    `fetch` (la API de MP); el resto es el código de producción.

    Incluye `ref`/`external_reference` a propósito: son la referencia que
    `checkout.js` genera por checkout y que `verify-payment.js` exige que
    coincida antes de dar un pago por aprobado — sin eso, cualquiera que
    tanteara un `payment_id` ajeno podía reclamar la licencia de otro
    comprador (ver `api/verify-payment.test.js`, que cubre ese caso puntual).
    Acá alcanza con que el mock las haga coincidir entre sí.
    """
    script = """
    process.env.MP_ACCESS_TOKEN = "TEST-token";
    const [plan, email, pid] = process.argv.slice(1);
    const ref = "c".repeat(32);
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ status: "approved", metadata: { plan },
                           external_reference: ref, payer: { email } }),
    });
    const vp = require("./api/verify-payment.js");
    const res = { statusCode: null, body: null,
      status(c){this.statusCode=c;return this;},
      json(b){this.body=b;return this;}, setHeader(){} };
    vp({ query: { payment_id: pid, ref }, headers: {} }, res)
      .then(() => process.stdout.write(JSON.stringify(res.body)));
    """
    r = subprocess.run(["node", "-e", script, plan, email, payment_id],
                       cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "KOBRA_LICENSE_SECRET": SECRETO})
    assert r.returncode == 0, f"verify-payment falló: {r.stderr}"
    return json.loads(r.stdout)


def _app_instalada(tmp_path, monkeypatch):
    """La app tal como queda en la máquina del cliente: modo standalone, sin
    sello de edición (el .exe de clientes no trae `edicion.json`), o sea
    pidiendo licencia."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    return TestClient(api.app)


# --- El camino del que paga -------------------------------------------------
@pytest.mark.parametrize("plan,dias", [("basico", 30), ("pro", 30),
                                       ("starter", 365)])
def test_el_cliente_paga_y_su_licencia_activa_la_app(tmp_path, monkeypatch,
                                                     plan, dias):
    """El recorrido completo: paga → recibe licencia → la pega → entra."""
    respuesta = _pagar(plan)
    assert respuesta["approved"] is True
    assert respuesta["license"], f"el pago aprobado no emitió licencia: {respuesta}"

    cliente = _app_instalada(tmp_path, monkeypatch)
    # Recién instalado, antes de activar: la app pide licencia.
    assert cliente.get("/api/licencia/estado").json()["activa"] is False

    r = cliente.post("/api/licencia/activar", json={"token": respuesta["license"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["activa"] is True
    assert d["plan"] == plan
    assert d["rol"] == "admin", "tras activar tiene que quedar operativo"
    # `dias - 1`: entre emitir y validar pasa un instante y el cálculo trunca.
    assert d["dias_restantes"] in (dias, dias - 1)


@pytest.mark.parametrize("plan", ["basico", "pro", "starter", "enterprise"])
def test_lo_que_se_paga_NO_es_la_version_demo(tmp_path, monkeypatch, plan):
    """La diferencia que el cliente compró: la demo es `trial` y vence en
    días; un plan pago no es trial y dura lo del plan. Si esto se rompiera, el
    que pagó estaría usando la misma versión de evaluación que se descarga
    gratis."""
    lic = _pagar(plan)["license"]
    cliente = _app_instalada(tmp_path, monkeypatch)
    d = cliente.post("/api/licencia/activar", json={"token": lic}).json()

    assert d["trial"] is False, f"el plan {plan} quedó marcado como versión de prueba"
    assert d["plan"] != "trial"
    assert d["dias_restantes"] >= 29, "un plan pago no puede durar menos que la demo"


def test_la_demo_si_es_trial_y_dura_poco(tmp_path, monkeypatch):
    """El control opuesto: la licencia de evaluación sí tiene que verse como
    trial. Sin este contraste, el test de arriba pasaría aunque `trial`
    estuviera siempre en False."""
    lic = _pagar("trial")["license"]
    cliente = _app_instalada(tmp_path, monkeypatch)
    d = cliente.post("/api/licencia/activar", json={"token": lic}).json()
    assert d["trial"] is True
    # Contra el plan y no contra un literal: la duración del trial es una
    # decisión comercial que cambia (empezó en 3 días, hoy son 7). Lo que no
    # puede cambiar es la relación — la evaluación dura menos que lo que se
    # cobra, o no hay motivo para pagar.
    from backend_venta.licencias import PLANES
    assert d["dias_restantes"] < PLANES["basico"]["dias"], \
        "el trial dura tanto como un plan pago"


# --- Lo que NO puede pasar --------------------------------------------------
def test_un_pago_no_aprobado_no_entrega_licencia():
    """Que nadie entre por armar la URL de /descarga a mano."""
    script = """
    process.env.MP_ACCESS_TOKEN = "TEST-token";
    const ref = "c".repeat(32);
    globalThis.fetch = async () => ({ ok: true,
      json: async () => ({ status: "pending", metadata: { plan: "pro" },
                           external_reference: ref }) });
    const vp = require("./api/verify-payment.js");
    const res = { statusCode: null, body: null,
      status(c){this.statusCode=c;return this;},
      json(b){this.body=b;return this;}, setHeader(){} };
    vp({ query: { payment_id: "1", ref }, headers: {} }, res)
      .then(() => process.stdout.write(JSON.stringify(res.body)));
    """
    r = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                       text=True, env={**os.environ, "KOBRA_LICENSE_SECRET": SECRETO})
    assert r.returncode == 0, r.stderr
    cuerpo = json.loads(r.stdout)
    assert cuerpo["approved"] is False
    assert cuerpo["license"] is None


def test_una_licencia_de_otro_vendedor_no_activa_la_app(tmp_path, monkeypatch):
    """Firmada con otro secreto: la app tiene que rechazarla con un mensaje
    que el usuario entienda, no con un 500."""
    script = ('const {sign} = require("./api/_license");'
              'process.stdout.write(sign({plan:"pro",pid:"1"}, "secreto-de-otro-vendedor"));')
    r = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    cliente = _app_instalada(tmp_path, monkeypatch)
    resp = cliente.post("/api/licencia/activar", json={"token": r.stdout.strip()})
    assert resp.status_code == 400
    assert "licencia" in resp.json()["detail"].lower()
    assert cliente.get("/api/licencia/estado").json()["activa"] is False


# --- El checkout arma bien lo que después cobra -----------------------------
@pytest.mark.parametrize("plan", ["basico", "pro", "starter"])
def test_el_checkout_manda_el_plan_que_despues_lee_la_licencia(plan):
    """`metadata.plan` de la preferencia es lo ÚNICO que conecta lo que el
    cliente eligió con el plan que termina en su licencia. Si el checkout no
    lo mandara, todos los pagos emitirían la misma licencia."""
    script = """
    process.env.MP_ACCESS_TOKEN = "TEST-token";
    process.env.SITE_URL = "https://ejemplo.com";
    let enviado = null;
    globalThis.fetch = async (url, opts) => {
      enviado = JSON.parse(opts.body);
      return { ok: true, json: async () => ({ init_point: "https://mp/ok" }) };
    };
    const ch = require("./api/checkout.js");
    const res = { statusCode: null, body: null,
      status(c){this.statusCode=c;return this;},
      json(b){this.body=b;return this;}, setHeader(){} };
    ch({ method: "POST", body: { plan: process.argv[1] }, headers: {}, query: {} }, res)
      .then(() => process.stdout.write(JSON.stringify(
        { status: res.statusCode, body: res.body, enviado })));
    """
    r = subprocess.run(["node", "-e", script, plan], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["status"] == 200, d
    assert d["enviado"]["metadata"]["plan"] == plan
    # La landing hace `window.location.href = d.url`: si la clave cambia de
    # nombre, el botón de comprar deja de llevar a ningún lado.
    assert d["body"].get("url"), "el checkout no devolvió `url`"
