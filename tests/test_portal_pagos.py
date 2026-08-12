"""Portal de cobros centralizado: el deudor paga solo y el pago queda imputado.

Pedido: un menú profesional donde el cliente entre por QR, usuario/contraseña
o link de pago, vea sus facturas pendientes y pague total o parcial por
transferencia bancaria o MercadoPago (si la empresa lo habilita), y que eso
quede imputado directo en el ERP/CRM de la empresa (webhook + API de pull).

Estos tests cubren el dominio (kobra/portal_pagos.py) y el flujo HTTP entero
contra la app real (TestClient), incluyendo los controles que hacen que esto
sea vendible: token firmado, código con freno a fuerza bruta, monto que no
puede superar el saldo, imputación idempotente y API key del ERP.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import portal_pagos as kportal  # noqa: E402

SECRETO = "secreto-de-prueba-para-el-portal"


# --- Dominio: tokens y códigos ----------------------------------------------
def test_token_del_link_va_y_vuelve():
    t = kportal.token_portal(SECRETO, "principal", "KB-100000")
    assert kportal.validar_token(SECRETO, t) == ("principal", "KB-100000")


@pytest.mark.parametrize("roto", [
    "", "x", "a.b", "principal.KB-100000.firmafalsa",
    "otra.KB-100000." + kportal.token_portal(SECRETO, "principal", "KB-100000").split(".")[2],
])
def test_token_adulterado_no_pasa(roto):
    assert kportal.validar_token(SECRETO, roto) is None


def test_el_codigo_de_acceso_es_estable_y_de_6_digitos():
    a = kportal.codigo_acceso(SECRETO, "principal", "KB-1")
    assert a == kportal.codigo_acceso(SECRETO, "principal", "KB-1")
    assert len(a) == 6 and a.isdigit()
    # Otro deudor u otra empresa → otro código.
    assert a != kportal.codigo_acceso(SECRETO, "principal", "KB-2") or \
           a != kportal.codigo_acceso(SECRETO, "otra", "KB-1")


# --- Dominio: facturas ------------------------------------------------------
def test_las_facturas_suman_exactamente_la_deuda():
    fila = {"id_deudor": "KB-100000", "monto_deuda": 231530.0,
            "cuotas_atrasadas": 4, "dias_mora": 90}
    fs = kportal.facturas_de(fila)
    assert len(fs) == 4
    assert round(sum(f["monto"] for f in fs), 2) == 231530.0
    # Determinístico: la misma deuda muestra siempre las mismas facturas.
    assert fs == kportal.facturas_de(fila)
    assert all(f["monto"] > 0 for f in fs)


def test_deuda_cero_no_inventa_facturas():
    assert kportal.facturas_de({"id_deudor": "X", "monto_deuda": 0}) == []


# --- Dominio: pagos e imputación --------------------------------------------
def test_flujo_de_pago_parcial_y_total(tmp_path):
    d = str(tmp_path)
    p1 = kportal.crear_pago(d, "principal", "KB-1", 400.0, "transferencia", 1000.0)
    assert p1["tipo"] == "parcial" and p1["estado"] == "pendiente"
    # Pendiente NO descuenta saldo (todavía no pagó nada).
    assert kportal.saldo_pendiente(d, "KB-1", 1000.0) == 1000.0

    kportal.confirmar_pago(d, p1["referencia"], "informado")
    assert kportal.saldo_pendiente(d, "KB-1", 1000.0) == 600.0

    # El resto exacto es pago "total".
    p2 = kportal.crear_pago(d, "principal", "KB-1", 600.0, "mercadopago", 1000.0)
    assert p2["tipo"] == "total"
    kportal.confirmar_pago(d, p2["referencia"], "aprobado")
    assert kportal.saldo_pendiente(d, "KB-1", 1000.0) == 0.0

    imps = kportal.listar_imputaciones(d)
    assert [i["monto"] for i in imps] == [400.0, 600.0]
    assert imps[1]["pago_total"] is True


def test_no_se_puede_pagar_mas_que_el_saldo(tmp_path):
    d = str(tmp_path)
    p = kportal.crear_pago(d, "principal", "KB-1", 900.0, "transferencia", 1000.0)
    kportal.confirmar_pago(d, p["referencia"], "informado")
    with pytest.raises(ValueError):
        kportal.crear_pago(d, "principal", "KB-1", 200.0, "transferencia", 1000.0)


def test_confirmar_dos_veces_imputa_una_sola_vez(tmp_path):
    """El deudor puede tocar «Ya transferí» dos veces o volver dos veces de
    MercadoPago: el ERP tiene que recibir UNA imputación, no dos."""
    d = str(tmp_path)
    p = kportal.crear_pago(d, "principal", "KB-1", 100.0, "transferencia", 500.0)
    kportal.confirmar_pago(d, p["referencia"], "informado")
    kportal.confirmar_pago(d, p["referencia"], "informado")
    assert len(kportal.listar_imputaciones(d)) == 1


def test_pull_incremental_para_el_erp(tmp_path):
    d = str(tmp_path)
    for monto in (100.0, 200.0):
        p = kportal.crear_pago(d, "principal", "KB-1", monto, "transferencia", 1000.0)
        kportal.confirmar_pago(d, p["referencia"], "informado")
    todas = kportal.listar_imputaciones(d)
    assert len(todas) == 2
    ultimas = kportal.listar_imputaciones(d, desde=todas[0]["imputado_en"])
    # `desde` es exclusivo: sincronización incremental sin duplicados.
    assert len(ultimas) <= 1 or todas[0]["imputado_en"] == todas[1]["imputado_en"]


def test_link_mercadopago_preconfigurado_y_demo():
    con_link = {"mercadopago": {"link_base": "https://mpago.la/abc"}}
    url = kportal.link_mercadopago(con_link, "KP-1", 500.0)
    assert url.startswith("https://mpago.la/abc?") and "external_reference=KP-1" in url
    demo = kportal.link_mercadopago({"mercadopago": {"link_base": ""}}, "KP-1", 500.0)
    assert "simulado" in demo


def test_dos_tenants_sin_clave_propia_no_comparten_la_derivada(tmp_path):
    """El agujero: la clave por defecto se derivaba solo del secreto GLOBAL
    del servidor, igual para cualquier tenant. Un admin de la empresa A (sin
    clave propia configurada, el caso por defecto) podía usar SU clave
    derivada para leer /api/erp/imputaciones de la empresa B — sus montos,
    sus deudores, sus referencias."""
    dir_a = str(tmp_path / "tenant-a")
    dir_b = str(tmp_path / "tenant-b")
    ka = kportal.api_key_erp(dir_a, SECRETO)
    kb = kportal.api_key_erp(dir_b, SECRETO)
    assert ka != kb, "dos tenants distintos terminaron con la misma API key del ERP"
    # Estable: la MISMA empresa, llamada dos veces, tiene que dar la MISMA
    # clave — si no, cualquier integración con el ERP se rompería sola.
    assert ka == kportal.api_key_erp(dir_a, SECRETO)


def test_config_del_portal_persiste_y_completa_defaults(tmp_path):
    d = str(tmp_path)
    kportal.guardar_config(d, {"transferencia": {"banco": "BROU"},
                               "otraseccion": {"x": 1}})
    cfg = kportal.cargar_config(d)
    assert cfg["transferencia"]["banco"] == "BROU"
    assert cfg["transferencia"]["habilitado"] is True     # default conservado
    assert "otraseccion" not in cfg                        # no es un JSON libre
    # La API key del ERP nunca queda vacía: derivada si no hay propia.
    k = kportal.api_key_erp(d, SECRETO)
    assert len(k) >= 20
    kportal.guardar_config(d, {"erp": {"api_key": "mi-clave-erp"}})
    assert kportal.api_key_erp(d, SECRETO) == "mi-clave-erp"


# --- HTTP: el flujo completo contra la app real -----------------------------
def _olvidar_modulos():
    for k in list(sys.modules):
        if k.startswith(("webapp", "kobra")):
            del sys.modules[k]


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """App real apuntada a un directorio de datos temporal con una cartera
    mínima scoreada, y una sesión admin."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    os.makedirs(tmp_path / "outputs", exist_ok=True)
    os.makedirs(tmp_path / "data", exist_ok=True)
    with open(tmp_path / "outputs" / "kobra_scored.csv", "w", encoding="utf-8") as f:
        f.write("id_deudor,segmento,monto_deuda,dias_mora,cuotas_atrasadas,probpago\n"
                "KB-1,Retail,1000.0,60,2,0.7\n")
    _olvidar_modulos()
    from fastapi.testclient import TestClient

    from kobra import autenticacion as kauth
    from webapp.backend import api
    c = TestClient(api.app)
    kauth.establecer_password("admin", "clave-segura-123")
    r = c.post("/api/auth/login", json={"password": "clave-segura-123"})
    assert r.status_code == 200, r.text
    admin = {"Authorization": f"Bearer {r.json()['token']}"}
    yield api, c, admin
    _olvidar_modulos()


def test_http_flujo_entero_del_portal(cliente):
    api, c, admin = cliente

    # 1. La empresa configura el portal (banco + MercadoPago + webhook ERP).
    r = c.post("/api/portal/config", headers=admin, json={
        "transferencia": {"banco": "BROU", "titular": "Empresa SA",
                          "cuenta": "001-123456"},
        "mercadopago": {"habilitado": True},
    })
    assert r.status_code == 200 and r.json()["transferencia"]["banco"] == "BROU"
    api_key = r.json()["erp_api_key_efectiva"]

    # 2. El gestor pide el acceso del deudor (link + QR + usuario/código).
    r = c.get("/api/portal/acceso/KB-1", headers=admin)
    assert r.status_code == 200
    acceso = r.json()
    assert acceso["usuario"] == "KB-1" and len(acceso["codigo"]) == 6
    token = acceso["token"]

    # 3. El deudor entra con usuario+código (misma puerta que el QR/link).
    r = c.post("/api/portal/public/login",
               json={"usuario": "kb-1", "codigo": acceso["codigo"]})
    assert r.status_code == 200 and r.json()["token"] == token

    # 4. Ve sus facturas: suman la deuda, con los métodos habilitados.
    r = c.get("/api/portal/public/estado", params={"t": token})
    assert r.status_code == 200
    estado = r.json()
    assert estado["saldo"] == 1000.0
    assert round(sum(f["monto"] for f in estado["facturas"]), 2) == 1000.0
    assert estado["metodos"]["transferencia"]["banco"] == "BROU"
    assert estado["metodos"]["mercadopago"] is True

    # 5. Paga una parte por transferencia: recibe referencia + datos bancarios.
    r = c.post("/api/portal/public/pagar",
               json={"t": token, "monto": 400.0, "metodo": "transferencia"})
    assert r.status_code == 200
    pago = r.json()
    assert pago["tipo"] == "parcial" and pago["transferencia"]["cuenta"] == "001-123456"

    # 6. Declara la transferencia → imputado (informado, a conciliar).
    r = c.post("/api/portal/public/confirmar",
               json={"t": token, "referencia": pago["referencia"]})
    assert r.status_code == 200 and r.json()["estado"] == "informado"

    # 7. Paga el resto por MercadoPago: link preconfigurado (demo simulado).
    r = c.post("/api/portal/public/pagar",
               json={"t": token, "monto": 600.0, "metodo": "mercadopago"})
    assert r.status_code == 200 and "url_pago" in r.json()
    ref_mp = r.json()["referencia"]
    # "informado" y no "aprobado": este endpoint nunca vuelve a consultar la
    # API de MercadoPago (a diferencia de api/verify-payment.js), así que no
    # puede afirmar una verificación que no hizo. Ver
    # test_mercadopago_nunca_se_auto_aprueba_sin_verificar.
    r = c.post("/api/portal/public/confirmar",
               json={"t": token, "referencia": ref_mp})
    assert r.json()["estado"] == "informado"

    # 8. Saldo en cero y los pagos visibles para la empresa.
    assert c.get("/api/portal/public/estado", params={"t": token}).json()["saldo"] == 0.0
    r = c.get("/api/portal/pagos", headers=admin)
    assert r.status_code == 200 and r.json()["total"] == 2

    # 9. El ERP tira del pull con la API key y recibe las 2 imputaciones.
    r = c.get("/api/erp/imputaciones", headers={"X-API-Key": api_key})
    assert r.status_code == 200 and r.json()["total"] == 2
    montos = sorted(i["monto"] for i in r.json()["imputaciones"])
    assert montos == [400.0, 600.0]


def test_http_sin_api_key_el_erp_no_ve_nada(cliente):
    _, c, _ = cliente
    assert c.get("/api/erp/imputaciones").status_code == 401
    assert c.get("/api/erp/imputaciones",
                 headers={"X-API-Key": "adivinada"}).status_code == 401


def test_http_token_falso_no_ve_deuda(cliente):
    _, c, _ = cliente
    r = c.get("/api/portal/public/estado", params={"t": "a.b.c"})
    assert r.status_code == 401


def test_http_codigo_incorrecto_frena_por_fuerza_bruta(cliente):
    """Códigos de 6 dígitos: sin freno, un script los prueba todos. El
    limitador corta con 429 antes del sexto intento fallido."""
    api, c, _ = cliente
    api._LIMITE_PORTAL.__init__(permitidos=4, ventana_seg=300)
    codigos = [c.post("/api/portal/public/login",
                      json={"usuario": "KB-1", "codigo": f"{i:06d}"}).status_code
               for i in range(7)]
    assert 429 in codigos, f"el login del portal nunca frenó: {codigos}"


def test_http_no_se_paga_de_mas_ni_con_metodo_deshabilitado(cliente):
    api, c, admin = cliente
    token = c.get("/api/portal/acceso/KB-1", headers=admin).json()["token"]
    # MercadoPago viene deshabilitado por default.
    r = c.post("/api/portal/public/pagar",
               json={"t": token, "monto": 100.0, "metodo": "mercadopago"})
    assert r.status_code == 400
    # Más que el saldo → 422 con mensaje accionable.
    r = c.post("/api/portal/public/pagar",
               json={"t": token, "monto": 99999.0, "metodo": "transferencia"})
    assert r.status_code == 422


def test_http_webhook_al_erp_recibe_la_imputacion(cliente, monkeypatch):
    """La imputación directa al ERP/CRM: al confirmar el pago se hace POST
    del asiento al webhook configurado por la empresa."""
    api, c, admin = cliente
    recibidos = []

    class _RespOk:
        ok = True

    def _post_falso(url, json=None, timeout=None):
        recibidos.append((url, json))
        return _RespOk()

    import requests
    monkeypatch.setattr(requests, "post", _post_falso)
    # Sin hilo: el test necesita el POST ya hecho al volver.
    monkeypatch.setattr(api.kportal.threading, "Thread",
                        lambda target, daemon: type("T", (), {"start": staticmethod(target)})())

    c.post("/api/portal/config", headers=admin,
           json={"erp": {"webhook_url": "https://erp.cliente.com/hook"}})
    token = c.get("/api/portal/acceso/KB-1", headers=admin).json()["token"]
    ref = c.post("/api/portal/public/pagar",
                 json={"t": token, "monto": 250.0, "metodo": "transferencia"}).json()["referencia"]
    c.post("/api/portal/public/confirmar", json={"t": token, "referencia": ref})

    assert len(recibidos) == 1
    url, cuerpo = recibidos[0]
    assert url == "https://erp.cliente.com/hook"
    assert cuerpo["referencia"] == ref and cuerpo["monto"] == 250.0
    assert cuerpo["tipo"] == "pago_portal"


def test_mercadopago_nunca_se_auto_aprueba_sin_verificar(cliente):
    """El agujero real: un deudor con su token de acceso legítimo (el mismo
    que la empresa le mandó por WhatsApp/mail) podía marcar su propia deuda
    como pagada por MercadoPago sin haber pagado un peso, porque el endpoint
    nunca volvía a consultar la API de MercadoPago — a diferencia de
    `api/verify-payment.js`, que sí lo hace antes de emitir una licencia."""
    api, c, admin = cliente
    c.post("/api/portal/config", headers=admin,
          json={"mercadopago": {"habilitado": True}})
    token = c.get("/api/portal/acceso/KB-1", headers=admin).json()["token"]

    r = c.post("/api/portal/public/pagar",
              json={"t": token, "monto": 1000.0, "metodo": "mercadopago"})
    assert r.status_code == 200
    referencia = r.json()["referencia"]

    # El deudor NUNCA completó nada en MercadoPago — llama a /confirmar
    # directo, como cualquiera que conozca este endpoint podría hacer.
    r = c.post("/api/portal/public/confirmar", json={"t": token, "referencia": referencia})
    assert r.status_code == 200
    assert r.json()["estado"] != "aprobado", (
        "un deudor no puede obtener el estado 'aprobado' —que implica pago "
        "verificado— sin que el servidor haya verificado nada")
    assert r.json()["estado"] == "informado", (
        "sin verificación real, el estado tiene que ser el mismo que una "
        "transferencia declarada: informado, pendiente de conciliar")
