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
    conf = demo.acreditar(tenant, pago["referencia"], metodo="mercadopago")
    assert conf["estado"] == "aprobado"

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
    conf = demo.acreditar(tenant, pago["referencia"], metodo="transferencia")
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
