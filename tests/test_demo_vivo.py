# © 2026 Martín Viera. Todos los derechos reservados.

"""El caso de demostración en vivo: que el circuito completo cierre, y que los
datos personales no terminen en el repositorio.

Lo que se muestra en una reunión —el agente llama, escribe, manda el link, entra
la plata, baja el saldo y queda la promesa— tiene que funcionar de punta a
punta o no se puede mostrar. Estos tests recorren ese circuito con el portal de
pagos real, sin tocar Twilio (que cobra por llamada) ni la red.

Y blindan la parte que no se ve: `vieraschiavi/Kobra` es un repositorio
público, así que el teléfono y el correo de la demostración viven en el
almacén cifrado de la máquina, nunca en el código. Si alguien los pega en el
módulo "para que funcione más fácil", esto falla.
"""
import importlib
import os
import re
import sys
from datetime import date

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import demo_vivo
    importlib.reload(demo_vivo)
    return demo_vivo


# --- Los datos personales no van al repositorio ---------------------------
def test_el_modulo_no_lleva_datos_de_contacto_reales():
    """El repositorio es público. Un celular escrito en el código queda
    indexado por Google y lo levantan los bots que rastrean GitHub."""
    with open(os.path.join(ROOT, "kobra", "demo_vivo.py"), encoding="utf-8") as f:
        codigo = f.read()

    # Un celular uruguayo real: 09X seguido de 6 dígitos, o +5989…
    assert not re.search(r"\+?598\s?9[1-9]\d[\s.-]?\d{3}[\s.-]?\d{3}", codigo), \
        "hay un teléfono uruguayo real en el código"
    assert not re.search(r"\b09[1-9]\d{6}\b", codigo), \
        "hay un celular uruguayo real en el código"
    # Un correo de verdad. El sintético usa .invalid, que es un TLD reservado
    # por la RFC 2606 justamente para que nunca resuelva.
    reales = [m for m in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", codigo)
              if not m.endswith((".invalid", ".example"))]
    assert not reales, f"hay correos reales en el código: {reales}"


def test_sin_configurar_el_caso_es_sintetico(demo):
    d = demo.caso()
    assert d["sintetico"] is True
    assert not demo.configurado()
    assert d["telefono"].endswith("555 000")   # rango reservado para ficción


def test_los_datos_reales_salen_del_almacen_cifrado(demo):
    from kobra import config as kconfig
    kconfig.guardar_extra("DEMO_VIVO_NOMBRE", "Martín Viera")
    kconfig.guardar_extra("DEMO_VIVO_TELEFONO", "+59899123456")

    d = demo.caso()
    assert d["nombre"] == "Martín Viera"
    assert d["telefono"] == "+59899123456"
    assert d["sintetico"] is False
    assert demo.configurado()

    # Y no quedaron escritos en ningún archivo del repositorio.
    assert not os.path.commonpath([kconfig.CONFIG_DIR, ROOT]) == ROOT


# --- El caso ---------------------------------------------------------------
def test_la_deuda_es_la_del_guion(demo):
    """$U 200 desde el 1/1/2026, para que el pago de demostración sea la mitad
    exacta y quede un saldo redondo que negociar."""
    assert demo.MONTO_DEUDA == 200.0
    assert demo.PAGO_DEMO == 100.0
    assert demo.FECHA_ALTA == date(2026, 1, 1)
    d = demo.caso(hoy=date(2026, 3, 2))
    assert d["dias_mora"] == 60
    assert d["moneda"] == "UYU"


def test_la_mora_nunca_es_negativa(demo):
    """Si alguien corre la demo con la fecha de la máquina atrasada, el caso no
    puede mostrar una mora negativa."""
    assert demo.caso(hoy=date(2025, 6, 1))["dias_mora"] == 0


# --- El circuito completo --------------------------------------------------
def test_el_circuito_cierra_de_punta_a_punta(demo, tmp_path):
    """Link → entra la plata → baja el saldo → queda la promesa. Es
    exactamente lo que se muestra en la reunión."""
    tenant = str(tmp_path / "tenant")
    os.makedirs(tenant, exist_ok=True)

    # Arranca debiendo los 200.
    assert demo.saldo(tenant) == 200.0

    # El link de pago por la mitad.
    pago = demo.link_de_pago(tenant, monto=100.0, metodo="mercadopago")
    assert pago["monto"] == 100.0
    assert pago["tipo"] == "parcial"
    assert pago["estado"] == "pendiente"

    # Entra la plata.
    conf = demo.acreditar(tenant, pago["referencia"])
    # Sin payment_id no hay nada verificado: `informado`, no `aprobado`.
    assert conf["estado"] == "informado"

    # Y el saldo baja solo: este es el número que se negocia.
    assert demo.saldo(tenant) == 100.0


def test_la_transferencia_entra_como_informada_no_como_cobrada(demo, tmp_path):
    """Una transferencia la declara el deudor; la empresa todavía la tiene que
    ver en el banco. Mostrarla como cobrada antes de eso es el error que hace
    desconfiar a un gerente de cobranzas."""
    tenant = str(tmp_path / "t2")
    os.makedirs(tenant, exist_ok=True)
    pago = demo.link_de_pago(tenant, monto=100.0, metodo="transferencia")
    assert "·" in pago["destino"]          # banco · cuenta
    conf = demo.acreditar(tenant, pago["referencia"])
    assert conf["estado"] == "informado"


def test_no_se_puede_cobrar_mas_que_la_deuda(demo, tmp_path):
    tenant = str(tmp_path / "t3")
    os.makedirs(tenant, exist_ok=True)
    with pytest.raises(ValueError):
        demo.link_de_pago(tenant, monto=250.0)


# --- La negociación de la diferencia ---------------------------------------
def test_las_propuestas_van_de_la_que_mas_recupera_a_la_que_menos(demo):
    """Es el orden en que un gestor las pone sobre la mesa: el descuento
    grande se ofrece último, no primero."""
    p = demo.propuestas(100.0)
    assert [x["descuento"] for x in p] == [5, 0, 15]
    assert p[0]["monto"] == 95.0
    assert p[1]["cuotas"] == 2 and p[1]["monto"] == 100.0
    assert p[2]["monto"] == 85.0        # el piso
    # Ninguna propuesta regala más del 15 %.
    assert max(x["descuento"] for x in p) <= 15


def test_las_propuestas_se_calculan_sobre_el_saldo_y_no_sobre_la_deuda(demo):
    """Después de pagar la mitad se negocia sobre lo que queda. Ofrecer un
    descuento sobre los 200 originales sería regalar plata ya cobrada."""
    assert demo.propuestas(100.0)[0]["monto"] == 95.0
    assert demo.propuestas(200.0)[0]["monto"] == 190.0


# --- Los pasos que salen a la red no salen sin credenciales ----------------
def test_llamar_sin_twilio_avisa_y_no_revienta(demo, monkeypatch):
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        monkeypatch.delenv(k, raising=False)
    r = demo.llamar(base_url="https://ejemplo.invalid")
    assert r["ok"] is False and "Twilio" in r["detalle"]


def test_whatsapp_sin_plantilla_aprobada_avisa(demo, monkeypatch):
    """WhatsApp no deja que una empresa inicie la conversación sin una
    plantilla aprobada por Meta, y eso no se puede saltear."""
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM",
              "TWILIO_WHATSAPP_CONTENT_SID"):
        monkeypatch.delenv(k, raising=False)
    r = demo.escribir_whatsapp()
    assert r["ok"] is False


# --- Que la carpeta de datos exista de verdad ------------------------------
def test_el_ensayo_por_consola_corre_entero(demo, capsys, monkeypatch):
    """`python -m kobra.demo_vivo` tiene que recorrer el circuito sin reventar.

    Regresión: tanto el ensayo como la pestaña del dashboard pedían la carpeta
    del tenant con `krutas.dir_datos()`, que no existe —`kobra.rutas` expone la
    constante `DIR_DATOS`—, así que las dos cosas morían con AttributeError
    apenas se abrían. Un `getattr` mal escrito no lo ve el linter ni la
    sintaxis: solo se cae al ejecutar, que es justo cuando hay alguien mirando.
    """
    # El ensayo se detiene a pedir el payment_id: se contesta vacío, que es
    # lo que hace quien solo quiere recorrer el circuito sin cobrar nada.
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    demo._ensayo()
    salida = capsys.readouterr().out
    assert "ENSAYO" in salida, "no arrancó"
    # Y que haya llegado hasta el final: las propuestas para negociar el saldo
    # son el último tramo, así que si están, el circuito cerró entero.
    assert "Contado con quita" in salida, f"se cortó antes del final:\n{salida[-400:]}"


def test_la_carpeta_de_datos_del_tenant_se_puede_resolver():
    """Lo que rompía era el nombre del accesor, no el valor. Se fija acá para
    que renombrar `DIR_DATOS` obligue a actualizar a quien la consume."""
    from kobra import rutas as krutas
    assert isinstance(krutas.DIR_DATOS, str) and krutas.DIR_DATOS


# ---------------------------------------------------------------------------
# Los endpoints: todo el circuito se opera desde la pantalla
# ---------------------------------------------------------------------------
# Si para mostrar el producto hay que abrir una terminal, la demo ya perdió.
# Estos tests fijan que cada paso —cargar el contacto, cobrar, acreditar,
# registrar la promesa— tenga su endpoint y no dependa de la consola.
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    # Directorio de datos propio: los pagos del portal viven junto a los datos
    # del tenant, así que sin aislarlos un test arrastra el saldo del anterior.
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    from fastapi.testclient import TestClient

    from kobra import registro as kregistro
    from kobra import rutas as krutas
    importlib.reload(krutas)
    importlib.reload(kregistro)
    from kobra import demo_vivo
    importlib.reload(demo_vivo)
    from webapp.backend import api
    importlib.reload(api)
    c = TestClient(api.app)
    tok = c.post("/api/auth/login", json={"password": "AdminTest123!"}).json()["token"]
    yield c, {"Authorization": f"Bearer {tok}"}

    # Estos módulos calculan rutas al importarse: recargarlos con el
    # KOBRA_DATA_DIR de prueba dejaría apuntando a un temporal a todo lo que
    # corra después. Se revierte el entorno y se recargan de nuevo.
    monkeypatch.undo()
    for mod in (krutas, kregistro, demo_vivo, api):
        importlib.reload(mod)


def test_la_pantalla_recibe_todo_de_un_solo_pedido(cliente):
    """Un GET tiene que alcanzar para dibujarla entera: caso, saldo, guion,
    propuestas y qué falta configurar."""
    c, h = cliente
    d = c.get("/api/demo/estado", headers=h).json()
    for clave in ("caso", "contacto_ok", "claves", "saldo", "pago_demo",
                  "guion", "propuestas", "pagos"):
        assert clave in d, f"falta {clave}"
    assert len(d["guion"]) == 6
    assert d["caso"]["monto_deuda"] == 200.0
    assert d["saldo"] == 200.0


def test_el_contacto_se_carga_desde_la_pantalla(cliente):
    """Sin esto habría que abrir una consola, que es justo lo que no puede
    pasar en medio de una reunión."""
    c, h = cliente
    assert c.get("/api/demo/estado", headers=h).json()["contacto_ok"] is False
    r = c.post("/api/demo/contacto", headers=h, json={"valores": {
        "DEMO_VIVO_NOMBRE": "Martín Viera", "DEMO_VIVO_TELEFONO": "+59899123456"}})
    assert r.status_code == 200 and r.json()["contacto_ok"] is True
    assert c.get("/api/demo/estado", headers=h).json()["caso"]["telefono"] == "+59899123456"


def test_no_se_guardan_claves_que_no_son_del_caso(cliente):
    """El endpoint escribe en el almacén de credenciales: solo acepta las
    claves que el módulo declara, no cualquier cosa que llegue."""
    c, h = cliente
    r = c.post("/api/demo/contacto", headers=h,
               json={"valores": {"ANTHROPIC_API_KEY": "sk-robada"}})
    assert r.status_code == 400


def test_cobrar_y_acreditar_desde_la_pantalla(cliente):
    c, h = cliente
    pago = c.post("/api/demo/cobrar", headers=h,
                  json={"monto": 100.0, "metodo": "mercadopago"}).json()
    assert pago["monto"] == 100.0 and pago["url_pago"]
    r = c.post("/api/demo/acreditar", headers=h,
               json={"referencia": pago["referencia"]}).json()
    # Sin payment_id no hay nada verificado.
    assert r["estado"] == "informado"
    assert c.get("/api/demo/estado", headers=h).json()["saldo"] == 100.0


def test_cobrar_de_mas_devuelve_un_error_util(cliente):
    c, h = cliente
    assert c.post("/api/demo/cobrar", headers=h, json={"monto": 9999.0}).status_code == 422


def test_metodo_de_pago_desconocido_se_rechaza(cliente):
    c, h = cliente
    assert c.post("/api/demo/cobrar", headers=h,
                  json={"monto": 10.0, "metodo": "bitcoin"}).status_code == 400


def test_contactar_sin_telefono_no_arranca_la_secuencia(cliente):
    """Arrancar para fallar en el paso 1 delante de un cliente es peor que no
    arrancar."""
    c, h = cliente
    r = c.post("/api/demo/contactar", headers=h, json={})
    assert r.status_code == 400 and "TELEFONO" in r.json()["detail"]


def test_la_promesa_se_registra_desde_la_pantalla(cliente):
    c, h = cliente
    r = c.post("/api/demo/promesa", headers=h, json={
        "monto_acordado": 95.0, "cuotas": 1, "descuento": 0.05,
        "fecha_compromiso": "2026-09-01"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_todo_el_circuito_exige_sesion(cliente):
    c, _ = cliente
    assert c.get("/api/demo/estado").status_code == 401
    for ruta in ("/api/demo/contacto", "/api/demo/cobrar", "/api/demo/acreditar",
                 "/api/demo/promesa", "/api/demo/contactar"):
        assert c.post(ruta, json={}).status_code == 401, f"{ruta} no exige sesión"
