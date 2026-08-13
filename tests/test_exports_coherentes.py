# © 2026 Martín Viera. Todos los derechos reservados.

"""Los exports publicados tienen que atar con los datos que los generan.

Hallazgo del loop de verificación end-to-end: `outputs/impacto_kobra.json`
estaba commiteado con `con_kobra.gestiones = 5019`, pero recalcularlo desde el
`data/kobra_gestiones.csv` commiteado daba **5021**. El JSON había quedado de
una versión anterior del CSV y nadie volvió a correr el pipeline.

No era no-determinismo: `analitica.impacto_kobra()` es una función pura del
DataFrame (sin azar ni fechas) y devuelve lo mismo en corridas sucesivas. Era
un artefacto desactualizado respecto de su propia fuente.

Por qué importa más de lo que parece: ese JSON alimenta las cifras de impacto
que se muestran para vender. Un prospecto técnico que pida los datos y
recalcule tiene que llegar al mismo número. Un export que no ata con su fuente
es exactamente el tipo de detalle que hunde la credibilidad de una demo, aunque
la diferencia sea de dos gestiones sobre cinco mil.
"""
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import analitica  # noqa: E402

GESTIONES = os.path.join(ROOT, "data", "kobra_gestiones.csv")
IMPACTO = os.path.join(ROOT, "outputs", "impacto_kobra.json")


@pytest.fixture(scope="module")
def gestiones():
    if not os.path.exists(GESTIONES):
        pytest.skip("falta data/kobra_gestiones.csv (correr el pipeline)")
    return pd.read_csv(GESTIONES)


@pytest.fixture(scope="module")
def publicado():
    if not os.path.exists(IMPACTO):
        pytest.skip("falta outputs/impacto_kobra.json (correr el pipeline)")
    with open(IMPACTO, encoding="utf-8") as f:
        return json.load(f)


def test_el_impacto_publicado_ata_con_las_gestiones(gestiones, publicado):
    """El defecto exacto: JSON commiteado que no coincide con su propio CSV."""
    recalculado = analitica.impacto_kobra(gestiones)
    for grupo in ("con_kobra", "sin_kobra"):
        assert publicado[grupo] == recalculado[grupo], (
            f"{grupo}: el JSON publicado no coincide con recalcularlo desde "
            f"data/kobra_gestiones.csv. Correr `python3 -m kobra.pipeline`.")


@pytest.mark.parametrize("clave", ["uplift_conversion", "uplift_calidad",
                                   "uplift_recupero"])
def test_los_uplift_publicados_atan(gestiones, publicado, clave):
    """Son las cifras que se muestran en la landing y la presentación."""
    assert publicado[clave] == analitica.impacto_kobra(gestiones)[clave]


def test_el_calculo_es_determinista(gestiones):
    """Si dependiera de la fecha o de un rng sin semilla, el export cambiaría
    solo y este guard sería ruido en vez de señal."""
    a = analitica.impacto_kobra(gestiones)
    b = analitica.impacto_kobra(gestiones)
    assert a == b


def test_el_json_avisa_que_las_cifras_son_ilustrativas(publicado):
    """Es dato sintético con el efecto de adopción inyectado por el generador.
    Publicarlo sin esa aclaración sería presentarlo como impacto medido."""
    nota = publicado.get("NOTA", "")
    assert "ILUSTRATIVO" in nota.upper()
    assert "NO es impacto medido" in nota or "no es impacto medido" in nota.lower()
