# © 2026 Martín Viera. Todos los derechos reservados.

"""La landing no puede prometer un módulo que el plan no incluye.

El defecto que motivó este archivo: la tarjeta de Pro decía "APIs embebidas y
medidas" y Pro **no incluye** el módulo de medidas (`dax`). Sus features son
`excedente` y `gobernanza`. La misma tarjeta se contradecía sola —el último
renglón decía "Suite: Gobernanza de datos", que sí era correcto— y quien pagara
US$349 esperando definir sus KPIs no los iba a tener.

Eso no es un error de redacción: es una oferta publicada que no se puede
cumplir. Y como el catálogo vive en `backend_venta/licencias.py`, se puede
comprobar sin depender de que alguien se acuerde.

También se fija que lo que está en el núcleo aparezca, que es el problema
opuesto: `ingenieria_datos` está en TODOS los planes desde que se agregó y la
landing no lo nombraba en ninguno — una función incluida y gratis que nadie
sabía que tenía.
"""
import os
import pathlib
import re

import pytest

from backend_venta.licencias import _NUCLEO, MODULOS_VENTA, PLANES

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LANDING = ROOT / "landing" / "index.html"

# Cómo se llama cada feature en la web. El nombre comercial y el nombre técnico
# no tienen por qué coincidir, pero la relación tiene que estar escrita en algún
# lado — si no, no hay forma de comprobar nada.
#
# `dax` se llama "KPIs propios" y no "Medidas": "medida" es el término de Power
# BI, y a un gerente de cobranzas no le dice nada. El propio módulo habla de
# "KPIs" en su docstring.
NOMBRE_COMERCIAL = {
    "gobernanza": "Gobernanza",
    "dax": "KPIs propios",
    "automl": "AutoML",
}

# Qué tarjeta de la landing corresponde a cada plan del catálogo.
TARJETA = {"basico": "p0", "starter": "p1", "pro": "p2", "enterprise": "p3"}


def _html():
    return LANDING.read_text(encoding="utf-8")


def _tarjeta(prefijo: str) -> str:
    """Los renglones (`<li>`) de una tarjeta de plan, en castellano."""
    html = _html()
    items = re.findall(rf'data-i="{prefijo}[a-z]+"[^>]*>(.*?)</li>', html, re.S)
    if not items:
        items = re.findall(rf'<li[^>]*data-i="{prefijo}\w*"[^>]*>(.*?)</li>', html, re.S)
    return " · ".join(re.sub(r"<[^>]+>", "", i) for i in items)


# --- Lo que un plan promete tiene que estar en el plan ----------------------
@pytest.mark.parametrize("plan", sorted(TARJETA))
def test_ningun_plan_promete_un_modulo_que_no_incluye(plan):
    """El control que faltaba. Si la tarjeta nombra un módulo de la suite, ese
    módulo tiene que estar en las features del plan."""
    texto = _tarjeta(TARJETA[plan]).lower()
    features = PLANES[plan]["features"]
    for tecnico, comercial in NOMBRE_COMERCIAL.items():
        if comercial.lower() in texto:
            assert tecnico in features, (
                f"la tarjeta de '{plan}' nombra {comercial!r} y el plan NO "
                f"incluye {tecnico!r}. Sus features son {features}. Eso es una "
                "oferta publicada que no se puede cumplir.")


@pytest.mark.parametrize("plan", sorted(TARJETA))
def test_cada_plan_nombra_los_modulos_que_si_incluye(plan):
    """El problema opuesto: pagar por algo y no enterarse de que lo tenés."""
    texto = _tarjeta(TARJETA[plan]).lower()
    for tecnico, comercial in NOMBRE_COMERCIAL.items():
        if tecnico in PLANES[plan]["features"]:
            assert comercial.lower() in texto, (
                f"'{plan}' incluye {tecnico!r} y la tarjeta no lo dice: se paga "
                "por algo que el cliente no sabe que tiene")


def test_el_nucleo_se_nombra_en_los_planes_de_entrada():
    """`ingenieria_datos` entró al núcleo —va en todos los planes, gratis— y la
    landing no lo mencionaba en ninguno."""
    assert "ingenieria_datos" in _NUCLEO
    for plan in ("basico", "starter"):
        texto = _tarjeta(TARJETA[plan]).lower()
        assert "ingeniería de datos" in texto or "ingenieria de datos" in texto, (
            f"la tarjeta de '{plan}' no nombra la ingeniería de datos, que está "
            "incluida en todos los planes")


# --- Precios ---------------------------------------------------------------
@pytest.mark.parametrize("plan", ["basico", "pro", "starter"])
def test_el_precio_de_la_tarjeta_es_el_del_catalogo(plan):
    """Un precio viejo en la landing es una oferta que hay que honrar."""
    precio = int(PLANES[plan]["precio"])
    html = _html()
    assert f"US${precio}" in html or f"US$ {precio}" in html, (
        f"'{plan}' cuesta US${precio} en el catálogo y la landing dice otra cosa")


def test_enterprise_no_muestra_un_precio_cerrado():
    """Su precio en el catálogo es `None` (a medida). Mostrar un número fijo
    contradice el botón, que manda a hablar con ventas."""
    assert PLANES["enterprise"]["precio"] is None
    html = _html()
    assert 'data-i="p3amt">A medida' in html, (
        "Enterprise tiene que decir 'A medida': el catálogo no le fija precio")


@pytest.mark.parametrize("modulo", sorted(MODULOS_VENTA))
def test_los_modulos_sueltos_muestran_su_precio_real(modulo):
    precio = int(MODULOS_VENTA[modulo]["precio"])
    html = _html()
    assert f"US${precio}" in html or f"US$ {precio}" in html, (
        f"el módulo '{modulo}' cuesta US${precio} y la landing dice otra cosa")


# --- El nombre -------------------------------------------------------------
def test_no_se_usa_el_nombre_viejo_del_modulo_de_kpis():
    """"Medidas" es el término de Power BI. Fuera de ese contexto se lee como
    "mediciones" o "medidas a tomar", que es cualquier otra cosa."""
    prohibidos = ["Medidas propias", "Medidas próprias", "Custom measures",
                  "Medidas calculadas"]
    for archivo in [LANDING,
                    ROOT / "webapp" / "frontend" / "src" / "i18n" / "es.json",
                    ROOT / "webapp" / "frontend" / "src" / "i18n" / "pt-BR.json"]:
        texto = archivo.read_text(encoding="utf-8")
        for frase in prohibidos:
            assert frase not in texto, (
                f"{archivo.name} todavía usa {frase!r}: el módulo se llama "
                "'KPIs propios'")


def test_el_menu_de_la_app_usa_el_mismo_nombre_que_la_web():
    """Que la web venda "KPIs propios" y el menú diga otra cosa hace que el
    cliente no encuentre lo que compró."""
    import json
    for arch, esperado in (("es.json", "KPIs propios"), ("pt-BR.json", "KPIs próprios")):
        d = json.loads((ROOT / "webapp" / "frontend" / "src" / "i18n" / arch)
                       .read_text(encoding="utf-8"))
        assert d["app"]["nav"]["medidas"] == esperado
        assert d["medidas"]["titulo"] == esperado
