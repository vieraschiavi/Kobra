# © 2026 Martín Viera. Todos los derechos reservados.

"""El tablero conversacional: que los números sean cuentas y no invenciones.

La promesa del módulo es una sola y es la que hay que proteger: **pandas
calcula, el modelo redacta**. Un tablero gerencial con un número inventado es
peor que no tener tablero — uno se descubre al mirarlo, el otro recién cuando
ya se tomó la decisión.

Los tests de acá cubren tres cosas:

  * que las cifras salgan de una cuenta verificable,
  * que el tablero **abra igual sin proveedor de IA** — si la pantalla de
    inicio dependiera de una API externa, un corte de red dejaría al gerente
    sin sus indicadores,
  * que al modelo se le pasen los hechos y la instrucción de no inventar.

Datos sintéticos armados en el test, con valores elegidos para que la cuenta se
pueda verificar a mano.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import analista as kan  # noqa: E402


@pytest.fixture()
def cartera():
    """Diez deudores con números redondos: la cuenta se verifica de memoria."""
    return pd.DataFrame({
        "id_deudor": [f"KB-{i}" for i in range(10)],
        "monto_deuda": [100.0] * 5 + [200.0] * 5,          # total 1500
        "dias_mora": [10, 20, 30, 40, 50, 100, 120, 150, 200, 300],
        "segmento": ["Pyme"] * 6 + ["Individuo"] * 4,
        "canal_preferido": ["Llamada"] * 7 + ["WhatsApp"] * 3,
        "contactabilidad": [0.8] * 10,
        "prob_pago": [0.9, 0.8, 0.75, 0.7, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1],
        "promesas_cumplidas": [1] * 10,
        "promesas_incumplidas": [0] * 10,
    })


# ---------------------------------------------------------------------------
# Los hechos son cuentas
# ---------------------------------------------------------------------------
def test_los_totales_son_exactos(cartera):
    h = kan.hechos(cartera)
    assert h["deudores"] == 10
    assert h["deuda_total"] == 1500.0
    assert h["deuda_promedio"] == 150.0


def test_la_mora_alta_se_cuenta_bien(cartera):
    """Cinco de los diez pasan los 90 días."""
    h = kan.hechos(cartera)
    assert h["deudores_mora_alta"] == 5
    assert h["pct_mora_alta"] == 50.0
    assert h["deuda_en_mora_alta"] == 200.0 * 5


def test_la_deuda_recuperable_sale_de_la_propension(cartera):
    """Cuatro deudores con prob_pago >= 0.7, todos de $100."""
    h = kan.hechos(cartera)
    assert h["deudores_alta_propension"] == 4
    assert h["deuda_recuperable_alta_propension"] == 400.0


def test_el_reparto_por_dimension_suma_el_total(cartera):
    h = kan.hechos(cartera)
    assert sum(h["deuda_por_segmento"].values()) == h["deuda_total"]


def test_una_cartera_sin_una_columna_no_rompe(cartera):
    """Un cliente puede subir una cartera sin `prob_pago` o sin
    `contactabilidad`. El tablero tiene que mostrar lo que sí tiene."""
    minima = cartera[["id_deudor", "monto_deuda"]]
    h = kan.hechos(minima)
    assert h["deuda_total"] == 1500.0
    assert "pct_mora_alta" not in h
    assert "deudores_alta_propension" not in h


def test_una_cartera_vacia_no_rompe():
    h = kan.hechos(pd.DataFrame({"monto_deuda": pd.Series(dtype=float)}))
    assert h["deudores"] == 0


# ---------------------------------------------------------------------------
# Advertencias, sugerencias y acciones: reglas, no opiniones
# ---------------------------------------------------------------------------
def test_avisa_cuando_media_cartera_esta_en_mora_alta(cartera):
    a = kan.advertencias(kan.hechos(cartera))
    assert any("90 días" in x["titulo"] for x in a), a


def test_avisa_cuando_la_contactabilidad_es_baja(cartera):
    rota = cartera.copy()
    rota["contactabilidad"] = 0.15
    a = kan.advertencias(kan.hechos(rota))
    assert any("Contactabilidad" in x["titulo"] for x in a), a
    # Y la acción correspondiente aparece en la lista de qué hacer.
    acc = kan.acciones(kan.hechos(rota))
    assert any("contacto" in x["titulo"].lower() for x in acc), acc


def test_avisa_cuando_las_promesas_no_se_cumplen(cartera):
    rota = cartera.copy()
    rota["promesas_cumplidas"] = 1
    rota["promesas_incumplidas"] = 4
    a = kan.advertencias(kan.hechos(rota))
    assert any("promesas" in x["titulo"] for x in a), a


def test_una_cartera_sana_no_inventa_advertencias():
    """Si el tablero siempre encuentra algo mal, deja de mirarse."""
    sana = pd.DataFrame({
        "monto_deuda": [100.0] * 20,
        "dias_mora": [5] * 20,
        "contactabilidad": [0.9] * 20,
        "promesas_cumplidas": [5] * 20,
        "promesas_incumplidas": [0] * 20,
        "segmento": ["Pyme"] * 10 + ["Individuo"] * 10,
    })
    assert kan.advertencias(kan.hechos(sana)) == []


def test_las_acciones_vienen_priorizadas(cartera):
    acc = kan.acciones(kan.hechos(cartera))
    assert acc, "no se sugirió ninguna acción"
    assert [a["prioridad"] for a in acc] == sorted(a["prioridad"] for a in acc)


def test_las_preguntas_sugeridas_solo_ofrecen_lo_que_hay(cartera):
    """Ofrecer '¿qué segmento concentra más deuda?' a quien no subió la columna
    `segmento` es prometer una respuesta que va a ser 'no está en los datos'."""
    completas = kan.preguntas_sugeridas(kan.hechos(cartera))
    assert any("segmento" in p.lower() for p in completas), completas

    minima = kan.preguntas_sugeridas(kan.hechos(cartera[["monto_deuda"]]))
    assert not any("segmento" in p.lower() for p in minima), minima
    assert not any("mora" in p.lower() for p in minima), minima
    # Pero sigue ofreciendo lo que sí se puede contestar.
    assert minima, "no quedó ninguna pregunta ofrecible"


# ---------------------------------------------------------------------------
# El tablero abre sin IA
# ---------------------------------------------------------------------------
def test_el_tablero_funciona_sin_proveedor_de_ia(cartera, monkeypatch):
    """Si la pantalla de inicio dependiera de una API externa, un corte de red
    dejaría al gerente sin sus indicadores. Los números son locales."""
    monkeypatch.setattr(kan.kllm, "disponible", lambda *a, **k: False)
    t = kan.tablero(cartera)
    assert t["hechos"]["deuda_total"] == 1500.0
    assert t["advertencias"]
    assert t["acciones"]
    assert t["ia_disponible"] is False


def test_preguntar_sin_ia_explica_que_falta_configurar(cartera, monkeypatch):
    """Y el mensaje aclara que lo demás sigue andando, para que no parezca que
    el producto entero está roto."""
    monkeypatch.setattr(kan.kllm, "disponible", lambda *a, **k: False)
    with pytest.raises(kan.SinModelo) as e:
        kan.responder("¿cómo viene la cobranza?", cartera)
    assert "Configuración" in str(e.value)


# ---------------------------------------------------------------------------
# La pregunta libre: qué se le manda al modelo
# ---------------------------------------------------------------------------
def test_al_modelo_se_le_pasan_los_hechos_calculados(cartera, monkeypatch):
    """El modelo no ve la cartera: ve el resumen ya calculado. Es lo que
    impide que estime un número por su cuenta."""
    capturado = {}

    def falso_generar(prompt, system=None, max_tokens=600, **k):
        capturado["prompt"] = prompt
        capturado["system"] = system
        return "La deuda total es $1.500."

    monkeypatch.setattr(kan.kllm, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(kan.kllm, "generar", falso_generar)

    r = kan.responder("¿cuánta deuda hay?", cartera)
    assert "1500" in capturado["prompt"], "no se le pasaron los totales"
    assert r["hechos_usados"]["deuda_total"] == 1500.0


def test_al_modelo_se_le_prohibe_inventar_numeros(cartera, monkeypatch):
    """La instrucción está en el system prompt. Si alguien la saca, el módulo
    deja de dar la garantía que promete su docstring."""
    capturado = {}
    monkeypatch.setattr(kan.kllm, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(kan.kllm, "generar",
                        lambda p, system=None, **k: capturado.update(s=system) or "ok")

    kan.responder("¿cuánto?", cartera)
    s = capturado["s"].lower()
    assert "no inventes" in s
    assert "no está en los datos" in s
    assert "no hagas proyecciones" in s


def test_la_respuesta_incluye_los_hechos_para_poder_verificar(cartera, monkeypatch):
    """Quien lee el tablero tiene que poder chequear de dónde salió el número
    sin tener que creernos."""
    monkeypatch.setattr(kan.kllm, "disponible", lambda *a, **k: True)
    monkeypatch.setattr(kan.kllm, "generar", lambda *a, **k: "Respuesta.")
    r = kan.responder("¿y?", cartera)
    assert r["hechos_usados"]["deuda_total"] == 1500.0
    assert r["respuesta"] == "Respuesta."


def test_una_pregunta_vacia_se_rechaza(cartera):
    with pytest.raises(ValueError):
        kan.responder("   ", cartera)
