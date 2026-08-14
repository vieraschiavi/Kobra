"""
Tests del caso de gestión que se muestra en vivo (`kobra/caso_demo.py`).

Lo que más importa acá no es que el guion tenga buena redacción, sino dos
garantías duras: que el repositorio —que es público— no lleve adentro el
teléfono ni el mail de nadie, y que nada de esto disque un número por accidente.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from kobra import caso_demo

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _sin_contacto(monkeypatch):
    """Cada test arranca sin contacto configurado.

    Sin esto, una máquina que tenga los DEMO_* cargados de verdad haría pasar
    tests que en CI —o en la de otro— fallarían.
    """
    for clave in ("DEMO_NOMBRE", "DEMO_TELEFONO", "DEMO_EMAIL"):
        monkeypatch.delenv(clave, raising=False)
    monkeypatch.setattr(caso_demo, "_config",
                        lambda: {"DEMO_NOMBRE": "", "DEMO_TELEFONO": "", "DEMO_EMAIL": ""})


# ---------------------------------------------------------------------------
# Lo que no puede estar en un repo público
# ---------------------------------------------------------------------------
def test_el_modulo_no_trae_datos_personales_adentro():
    """Ni teléfono, ni mail, ni cuenta bancaria hardcodeados.

    Es la razón de ser del diseño: el contacto se configura, no se commitea.
    Si alguien alguna vez pega su número acá para 'probar rápido', esto lo
    frena antes de que quede publicado para siempre en el historial de git.
    """
    texto = (RAIZ / "kobra" / "caso_demo.py").read_text(encoding="utf-8")
    # Se sacan los ejemplos de formato de la documentación, que sí llevan '+598'
    # sin ser un número de nadie.
    sin_docs = re.sub(r'""".*?"""', "", texto, flags=re.S)

    telefonos = re.findall(r"\+\d{9,15}", sin_docs)
    assert not telefonos, f"hay teléfonos hardcodeados: {telefonos}"

    mails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", sin_docs)
    assert not mails, f"hay mails hardcodeados: {mails}"

    # Una cuenta bancaria es cualquier corrida larga de dígitos suelta.
    cuentas = re.findall(r"(?<![\w.])\d{6,}(?![\w.])", sin_docs)
    assert not cuentas, f"parece haber un número de cuenta: {cuentas}"


def test_las_claves_de_contacto_estan_en_la_configuracion():
    """Para que se puedan cargar desde ⚙️ Configuración y no solo por entorno."""
    from kobra import config as kconfig
    for clave in ("DEMO_NOMBRE", "DEMO_TELEFONO", "DEMO_EMAIL"):
        assert clave in kconfig.CLAVES, f"{clave} no está en CLAVES"


# ---------------------------------------------------------------------------
# El caso
# ---------------------------------------------------------------------------
def test_la_deuda_es_la_del_caso():
    assert caso_demo.DEUDA_TOTAL == 200.0
    assert caso_demo.MONEDA == "UYU"
    assert caso_demo.VENCIMIENTO == date(2026, 1, 1)
    # La mitad se paga en el aire y la otra mitad queda para negociar.
    assert caso_demo.PAGO_DEMO == 100.0
    assert caso_demo.DEUDA_TOTAL - caso_demo.PAGO_DEMO == 100.0


def test_la_mora_se_calcula_y_no_envejece():
    """Un número fijo mentiría a los seis meses."""
    assert caso_demo.dias_mora(date(2026, 1, 31)) == 30
    assert caso_demo.dias_mora(date(2026, 8, 14)) == 225
    # Antes del vencimiento no hay mora negativa.
    assert caso_demo.dias_mora(date(2025, 12, 1)) == 0


def test_el_tramo_acompana_a_la_mora():
    assert caso_demo.tramo(caso_demo.dias_mora(date(2026, 1, 15))) == "1-30"
    assert caso_demo.tramo(caso_demo.dias_mora(date(2026, 8, 14))) == "90+"


def test_el_brief_sirve_para_una_sesion_del_gestor():
    """Tiene que traer las claves que `SesionGestorIA` consume sin defaults."""
    b = caso_demo.brief(date(2026, 8, 14))
    for clave in ("monto_deuda", "probpago", "estrategia",
                  "descuento_recomendado", "plan_cuotas", "segmento_propension"):
        assert clave in b, f"al brief le falta {clave}"
    assert 0 < b["descuento_recomendado"] < 1
    assert b["plan_cuotas"] >= 1


def test_el_brief_es_siempre_igual():
    """Una demo que cambia de guion entre reuniones no se puede ensayar."""
    assert caso_demo.brief(date(2026, 8, 14)) == caso_demo.brief(date(2026, 8, 14))


# ---------------------------------------------------------------------------
# Que no llame por accidente
# ---------------------------------------------------------------------------
def test_el_ensayo_no_toca_nada_externo(monkeypatch):
    """El modo por defecto no puede discar, escribir ni mover plata."""
    def _explota(*a, **k):
        raise AssertionError("el modo ensayo llamó a un servicio externo")

    from kobra import campana
    monkeypatch.setattr(campana, "iniciar_llamada", _explota)
    monkeypatch.setattr(campana, "enviar_whatsapp", _explota)

    r = caso_demo.ejecutar()          # sin argumentos: tiene que ser ensayo
    assert r["modo"] == "ensayo"
    assert len(r["pasos"]) == 5
    # Ningún paso se ejecutó.
    assert all(p.ok is None for p in r["pasos"])


def test_sin_telefono_el_modo_real_se_corta_antes_de_empezar():
    """Fallar en el paso 1 delante de un cliente es peor que no arrancar."""
    with pytest.raises(RuntimeError, match="DEMO_TELEFONO"):
        caso_demo.ejecutar(modo="real")


def test_un_modo_inventado_no_pasa():
    with pytest.raises(ValueError):
        caso_demo.ejecutar(modo="produccion")


def test_avisa_que_falta_configurar_el_contacto():
    r = caso_demo.ejecutar()
    assert r["contacto_ok"] is False
    assert set(r["faltantes"]) == {"DEMO_NOMBRE", "DEMO_TELEFONO", "DEMO_EMAIL"}


def test_el_contacto_sale_de_la_configuracion(monkeypatch):
    monkeypatch.setattr(caso_demo, "_config",
                        lambda: {"DEMO_NOMBRE": "Quien Sea",
                                 "DEMO_TELEFONO": "+59800000000",
                                 "DEMO_EMAIL": "quien@ejemplo.com"})
    c = caso_demo.contacto()
    assert c.completo and c.faltantes() == []
    assert c.nombre_visible == "Quien Sea"
    # Y el teléfono aparece en el guion, que es lo que se lee en la demo.
    assert "+59800000000" in caso_demo.guion()[0].detalle


def test_el_nombre_sin_configurar_se_reporta_igual_aunque_haya_default():
    """El default es solo para mostrar: no puede tapar que falta cargarlo."""
    c = caso_demo.Contacto(nombre="", telefono="+59800000000", email="a@b.com")
    assert c.nombre_visible == "Titular de la demo"
    assert "DEMO_NOMBRE" in c.faltantes()


def test_la_fila_tiene_las_columnas_de_la_cartera():
    f = caso_demo.fila(date(2026, 8, 14))
    for col in ("id_deudor", "monto_deuda", "dias_mora", "tramo_mora"):
        assert col in f
    assert f["id_deudor"] == caso_demo.ID_DEUDOR
