# © 2026 Martín Viera. Todos los derechos reservados.

"""El precio que se muestra tiene que ser el precio que se cobra.

El bug que esto evita, encontrado en producción:

    un visitante de Argentina elegía su país en la landing
    -> veía "≈ $223.500 ARS (referencia)"   (convertido desde US$149)
    -> apretaba "Suscribirme al Pro"
    -> el checkout le cobraba US$349

Los precios viven en TRES lugares que nadie mantenía juntos:

  1. `api/checkout.js::PLANS[].price`  — lo que realmente se cobra.
  2. La tarjeta de la landing (`.amt`) — el número grande en pantalla.
  3. `USD_BASE` en la misma landing  — la base de la conversión a moneda
     local para AR/MX/CL/CO/PE/BR.

Las tres se editaron por separado a lo largo del tiempo y quedaron con
precios de épocas distintas: las tarjetas y el checkout se actualizaron a
99/690/349, y `USD_BASE` se quedó en 59/490/149 — los precios viejos. O sea
que el error solo lo veía un visitante de los seis países del selector, que
es exactamente el mercado que la conversión venía a atender.

No es un detalle cosmético: mostrar un precio y cobrar más del doble es
motivo de contracargo, y con una empresa como cliente es motivo de perder
la venta entera.
"""
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = os.path.join(ROOT, "landing", "index.html")
CHECKOUT = os.path.join(ROOT, "api", "checkout.js")

# Qué plan de checkout.js es cada tarjeta de la landing. Enterprise (p3) no
# está: se vende "a medida" y no tiene checkout, así que no hay nada contra
# qué compararlo — su número solo tiene que coincidir con su propia tarjeta.
TARJETA_A_PLAN = {"p0": "basico", "p1": "starter", "p2": "pro"}


def _landing() -> str:
    with open(LANDING, encoding="utf-8") as f:
        return f.read()


def _usd_base() -> dict:
    """`var USD_BASE={p0:[99,null],...}` -> {"p0": [99, None], ...}"""
    m = re.search(r"var USD_BASE=(\{.*?\});", _landing(), re.S)
    assert m, "no se encontró USD_BASE en la landing"
    # De JS a JSON: las claves van sin comillas y el nulo se escribe igual.
    crudo = re.sub(r"(\w+):", r'"\1":', m.group(1))
    return json.loads(crudo)


def _precios_checkout() -> dict:
    """`basico: { title: "...", price: 99.0 }` -> {"basico": 99.0, ...}"""
    with open(CHECKOUT, encoding="utf-8") as f:
        js = f.read()
    hallados = dict(re.findall(r"(\w+):\s*\{[^}]*?price:\s*([\d.]+)", js))
    assert hallados, "no se encontró ningún precio en checkout.js"
    return {k: float(v) for k, v in hallados.items()}


def _precios_tarjetas() -> dict:
    """El número grande de cada tarjeta: `<div class="amt">US$99<small>`."""
    # Cada tarjeta liga su .amt con su data-pais-precio; se recorre el bloque
    # de precios en orden y se emparejan por posición dentro de la sección.
    html = _landing()
    seccion = html[html.index('id="precios"'):]
    seccion = seccion[:seccion.index("</section>")]
    montos = re.findall(r'class="amt"[^>]*>(?:US\$)?([\d.,]+)?', seccion)
    claves = re.findall(r'data-pais-precio="(\w+)"', seccion)
    salida = {}
    for clave, monto in zip(claves, montos):
        if monto:
            salida[clave] = float(monto.replace(".", "").replace(",", "."))
    return salida


def test_la_base_de_conversion_es_lo_que_cobra_el_checkout():
    """El caso que estaba roto: se mostraba US$149 y se cobraba US$349."""
    base = _usd_base()
    cobra = _precios_checkout()
    for tarjeta, plan in TARJETA_A_PLAN.items():
        assert tarjeta in base, f"falta {tarjeta} en USD_BASE"
        assert plan in cobra, f"falta {plan} en checkout.js"
        mostrado, cobrado = base[tarjeta][0], cobra[plan]
        assert mostrado == cobrado, (
            f"el plan {plan} se muestra convertido desde US${mostrado:.0f} y "
            f"el checkout cobra US${cobrado:.0f}. Un visitante de "
            f"AR/MX/CL/CO/PE/BR ve un precio y paga otro.")


def test_la_base_de_conversion_es_lo_que_dice_la_tarjeta():
    """Y también tiene que coincidir con el número grande en pantalla, que es
    lo que ve un visitante de Uruguay (para el que no hay conversión)."""
    base = _usd_base()
    tarjetas = _precios_tarjetas()
    for clave, monto in tarjetas.items():
        assert clave in base, f"la tarjeta {clave} no tiene entrada en USD_BASE"
        assert base[clave][0] == monto, (
            f"la tarjeta {clave} muestra US${monto:.0f} pero convierte desde "
            f"US${base[clave][0]:.0f}")


def test_las_copias_de_idioma_no_quedan_con_precios_viejos():
    """`landing/en/` y `landing/pt/` se GENERAN desde `landing/index.html`
    (marketing/generar_paginas_idioma.py). Si se corrige el precio y no se
    regeneran, el error sigue vivo para el visitante en inglés o portugués —
    que es justamente el de Brasil, uno de los seis países del selector."""
    esperado = re.search(r"var USD_BASE=\{.*?\};", _landing(), re.S).group(0)
    for lang in ("en", "pt"):
        ruta = os.path.join(ROOT, "landing", lang, "index.html")
        if not os.path.exists(ruta):
            pytest.skip(f"no existe landing/{lang}/index.html")
        with open(ruta, encoding="utf-8") as f:
            copia = f.read()
        assert esperado in copia, (
            f"landing/{lang}/index.html quedó con precios viejos. "
            "Regeneralo: python marketing/generar_paginas_idioma.py")


@pytest.mark.skipif(not os.path.exists(CHECKOUT), reason="requiere api/")
def test_todo_plan_con_precio_visible_se_puede_comprar():
    """Si una tarjeta ofrece un botón de compra, el plan tiene que existir en
    el checkout — si no, el botón lleva a un error en vez de a un pago."""
    html = _landing()
    seccion = html[html.index('id="precios"'):]
    seccion = seccion[:seccion.index("</section>")]
    comprables = set(re.findall(r'data-pay="(\w+)"', seccion))
    cobra = set(_precios_checkout())
    # "enterprise" es el botón "Hablar con ventas": no pasa por checkout.
    faltantes = comprables - cobra - {"enterprise"}
    assert not faltantes, (
        f"la landing ofrece comprar {sorted(faltantes)} pero checkout.js no "
        "los tiene: el botón termina en error.")
