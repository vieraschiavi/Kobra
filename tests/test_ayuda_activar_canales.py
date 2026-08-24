# © 2026 Martín Viera. Todos los derechos reservados.

"""Los pasos de voz y WhatsApp los tiene que poder hacer el CLIENTE.

La cuenta de telefonía es del cliente y la factura le llega a él: no hay forma
de que el proveedor haga estos pasos por él, ni queriendo. Así que la
instrucción tiene que estar DENTRO del programa que compró, no en un mail que
alguien le mandó una vez.

Está en tres lugares y los tres tienen que decir lo mismo:

  * `docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md` — alimenta al asistente de ayuda de
    los dos programas (Streamlit y React) vía `kobra/ayuda.py`;
  * la pestaña Ayuda del tablero Streamlit;
  * la pantalla Asistente de la webapp.

Lo que se protege acá es sobre todo que no se contradigan, y dos advertencias
concretas que valen plata si faltan.
"""
import json
import os
import pathlib

import pytest

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIA = ROOT / "docs" / "AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md"


def leer(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1) El asistente de los dos programas la encuentra
# ---------------------------------------------------------------------------
def test_la_guia_del_cliente_alimenta_al_asistente():
    from kobra import ayuda
    assert "docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md" in ayuda.FUENTES_DOCS


def test_va_antes_que_la_guia_de_quien_arma_el_producto():
    """Quien pregunta «¿cómo hago para que llame?» es el que compró el
    programa, no quien lo desarrolla."""
    from kobra import ayuda
    fuentes = ayuda.FUENTES_DOCS
    assert (fuentes.index("docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md")
            < fuentes.index("docs/GUIA_LLAMADA_REAL_TWILIO.md"))


@pytest.mark.parametrize("pregunta", [
    "¿qué necesito para que llame de verdad por teléfono?",
    "¿le tengo que mandar el auth token a alguien?",
    "¿quién paga los minutos de las llamadas?",
    "las llamadas entrantes se cortan apenas atienden",
    "¿por qué no puedo mandar whatsapp?",
])
def test_el_asistente_responde_con_la_guia_del_cliente(pregunta):
    """Las preguntas que hace un cliente real el primer día."""
    from kobra import ayuda
    fuentes = {f["fuente"] for f in ayuda.buscar(pregunta, k=3)}
    assert "docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md" in fuentes, (
        f"«{pregunta}» no cae en la guía del cliente: {fuentes}")


# ---------------------------------------------------------------------------
# 2) Las dos advertencias que valen plata
# ---------------------------------------------------------------------------
def test_en_los_tres_lugares_se_avisa_de_no_mandar_el_auth_token():
    """Con el Auth Token se hacen llamadas, se compran números y se escuchan
    las grabaciones — y lo gastado lo paga el cliente. Que se lo pidan por
    mail es el pedido que hay que enseñarle a rechazar."""
    for rel in ("docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md", "app/app.py"):
        texto = leer(rel).lower()
        assert "nunca mandes el auth token" in texto, f"{rel} no lo advierte"
    es = json.loads(leer("webapp/frontend/src/i18n/es.json"))
    aviso = es["asistente"]["activar_canales"]["aviso_token"].lower()
    assert "nunca" in aviso and "auth token" in aviso


def test_se_avisa_de_salir_del_trial():
    """El trial de Twilio reproduce un mensaje grabado ANTES de cada llamada.
    Con un deudor real eso arruina la gestión, y el cliente lo descubre en
    vivo si nadie se lo dijo antes."""
    for rel in ("docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md", "app/app.py"):
        texto = leer(rel).lower()
        assert "grabado" in texto and ("trial" in texto or "modo de prueba" in texto), (
            f"{rel} no avisa del mensaje grabado del trial")


def test_se_explica_el_paso_del_webhook():
    """La razón número uno de «las salientes andan pero las entrantes no»."""
    for rel in ("docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md", "app/app.py"):
        assert "/voz/entrante" in leer(rel), f"{rel} no dice adónde apuntar el número"


# ---------------------------------------------------------------------------
# 3) Quién paga: la parte que no se puede decir a medias
# ---------------------------------------------------------------------------
def test_queda_claro_que_la_cuenta_es_del_cliente():
    """Si el cliente cree que los minutos los pone el proveedor, la primera
    factura de Twilio es una discusión. Y al revés: si el proveedor abre
    subcuentas de la suya, Twilio le factura A ÉL todo el consumo de todos."""
    doc = leer("docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md").lower()
    assert "no revende minutos" in doc
    assert "te factura a vos" in doc


def test_la_guia_no_le_pide_al_cliente_que_entregue_credenciales():
    """El modelo es que las claves se cargan en el programa del cliente. Si
    alguna vez este texto le pide que las mande, el modelo cambió y hay que
    revisarlo a propósito, no de pasada."""
    doc = leer("docs/AYUDA_CLIENTE_VOZ_Y_WHATSAPP.md").lower()
    for frase in ("pasanos el auth token", "mandanos el auth token",
                  "enviá el auth token", "envianos las credenciales"):
        assert frase not in doc, f"la guía pide entregar credenciales: {frase!r}"


# ---------------------------------------------------------------------------
# 4) Los dos idiomas
# ---------------------------------------------------------------------------
def test_la_pantalla_del_asistente_esta_traducida():
    es = json.loads(leer("webapp/frontend/src/i18n/es.json"))
    pt = json.loads(leer("webapp/frontend/src/i18n/pt-BR.json"))
    claves_es = set(es["asistente"]["activar_canales"])
    claves_pt = set(pt["asistente"]["activar_canales"])
    assert claves_es == claves_pt, (
        f"faltan traducciones: solo en es {claves_es - claves_pt}, "
        f"solo en pt {claves_pt - claves_es}")
    assert claves_es, "el bloque quedó vacío"


def test_la_webapp_muestra_los_pasos_sin_tener_que_preguntar():
    """Quien acaba de comprar el programa no sabe todavía qué preguntarle a un
    chatbot: los pasos tienen que verse."""
    jsx = leer("webapp/frontend/src/pages/Asistente.jsx")
    assert "ActivarCanales" in jsx
    assert "asistente.activar_canales." in jsx
