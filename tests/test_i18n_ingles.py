# © 2026 Martín Viera. Todos los derechos reservados.

"""El programa en inglés: mismas claves, mismos huecos, mismo vocabulario.

La app tenía castellano y portugués, y el idioma salía del país del tenant
(Brasil → portugués). Dos cosas estaban mezcladas ahí: la moneda con la que se
factura y el idioma en el que trabaja el equipo. Ahora hay inglés y el idioma
se elige aparte.

Una traducción incompleta es peor que no tenerla: la pantalla queda mitad en
un idioma y mitad en otro, o —peor— un `{{monto}}` sin reemplazar delante de un
cliente. Lo que se fija acá es que los tres diccionarios sean intercambiables.
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

I18N = os.path.join(ROOT, "webapp", "frontend", "src", "i18n")
IDIOMAS = {"es": "es.json", "pt": "pt-BR.json", "en": "en.json"}
_PLACEHOLDER = re.compile(r"\{\{\w+\}\}")
_ETIQUETA = re.compile(r"</?([a-zA-Z][\w-]*)")


def _dic(idioma):
    with open(os.path.join(I18N, IDIOMAS[idioma]), encoding="utf-8") as f:
        return json.load(f)


def _rutas(o, prefijo=""):
    salida = {}
    for k, v in o.items():
        if isinstance(v, dict):
            salida.update(_rutas(v, f"{prefijo}{k}."))
        else:
            salida[f"{prefijo}{k}"] = v
    return salida


@pytest.mark.parametrize("idioma", ["pt", "en"])
def test_ningun_texto_de_la_interfaz_queda_sin_traducir(idioma):
    """Mismas claves exactas que el castellano: una que falte deja la pantalla
    mostrando la clave cruda (`app.nav.cartera`) o el texto en español."""
    es, otro = _rutas(_dic("es")), _rutas(_dic(idioma))
    faltan = sorted(set(es) - set(otro))
    sobran = sorted(set(otro) - set(es))
    assert not faltan, f"{idioma}: faltan {len(faltan)} claves, p. ej. {faltan[:8]}"
    assert not sobran, f"{idioma}: sobran claves que el castellano no tiene: {sobran[:8]}"


@pytest.mark.parametrize("idioma", ["pt", "en"])
def test_los_huecos_de_las_frases_sobreviven_a_la_traduccion(idioma):
    """`{{monto}}`, `{{dias}}`… los rellena el código. Si la traducción se come
    uno, el cliente ve la frase sin el número; si lo renombra, ve el hueco
    crudo en pantalla."""
    es, otro = _rutas(_dic("es")), _rutas(_dic(idioma))
    for clave, texto in es.items():
        if not isinstance(texto, str):
            continue
        esperados = sorted(_PLACEHOLDER.findall(texto))
        traidos = sorted(_PLACEHOLDER.findall(otro[clave]))
        assert esperados == traidos, (
            f"{idioma}:{clave} espera {esperados} y trae {traidos}")


@pytest.mark.parametrize("idioma", ["pt", "en"])
def test_el_html_de_las_frases_sobrevive_a_la_traduccion(idioma):
    """Algunas frases llevan <b> o <br> y se pintan con innerHTML. Una etiqueta
    rota se ve como marcado suelto en la pantalla."""
    es, otro = _rutas(_dic("es")), _rutas(_dic(idioma))
    for clave, texto in es.items():
        if not isinstance(texto, str):
            continue
        assert sorted(_ETIQUETA.findall(texto)) == sorted(_ETIQUETA.findall(otro[clave])), \
            f"{idioma}:{clave} cambió las etiquetas HTML"


@pytest.mark.parametrize("idioma", list(IDIOMAS))
def test_ninguna_frase_queda_vacia(idioma):
    vacias = [k for k, v in _rutas(_dic(idioma)).items()
              if isinstance(v, str) and not v.strip()]
    assert not vacias, f"{idioma}: frases vacías en {vacias[:5]}"


def test_el_menu_usa_los_mismos_nombres_que_la_web_en_ingles():
    """El módulo se vende como "Custom KPIs" en la landing en inglés: si el
    menú del programa lo llama de otra forma, el cliente no encuentra lo que
    compró. Mismo criterio que ya se fija para castellano y portugués."""
    en = _dic("en")
    assert en["app"]["nav"]["medidas"] == "Custom KPIs"
    assert en["medidas"]["titulo"] == "Custom KPIs"
    landing = open(os.path.join(ROOT, "landing", "index.html"),
                   encoding="utf-8").read()
    assert "Custom KPIs" in landing


def test_la_app_ofrece_los_tres_idiomas():
    """El selector y el resolvedor tienen que conocer los tres; si `IDIOMAS`
    se queda corto, el diccionario existe pero nadie puede elegirlo."""
    api = open(os.path.join(ROOT, "webapp", "frontend", "src", "api.js"),
               encoding="utf-8").read()
    assert 'export const IDIOMAS = ["es", "pt", "en"]' in api
    assert "kobra_idioma" in api, "el idioma elegido no se guarda"
    assert '"Accept-Language": getIdioma()' in api, (
        "la API no le dice al backend en qué idioma generar el texto")
    indice = open(os.path.join(I18N, "index.js"), encoding="utf-8").read()
    assert "en" in indice and "getIdioma" in indice


def test_el_backend_acepta_el_idioma_pedido():
    """El texto que GENERA el motor (avisos del tablero, guion del deudor)
    también tiene que venir en el idioma elegido."""
    from webapp.backend import api as backend
    assert backend.idioma_pedido("en") == "en"
    assert backend.idioma_pedido("pt-BR,pt;q=0.9") == "pt"
    assert backend.idioma_pedido("es-UY") == "es"
    # Cualquier cosa rara cae a castellano en vez de dejar la pantalla muda.
    assert backend.idioma_pedido("") == "es"
    assert backend.idioma_pedido("zz") == "es"
