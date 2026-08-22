# © 2026 Martín Viera. Todos los derechos reservados.

"""El mismo deudor no puede tener dos ProbPago según qué pantalla se mire.

`kobra/probpago.py` tiene dos formas de entrenar:

  * `fit()` — un Gradient Boosting ad-hoc, sin comparar contra nada.
  * `fit_seleccionado()` — el modelo que ganó la comparación con validación
    cruzada en `kobra/train.py`, ya calibrado.

El pipeline y la cartera manual usan el segundo. El tablero Streamlit —que es
el producto entero en la edición BAT— usaba el primero. Medido sobre la
cartera de 12.000 deudores, antes del arreglo:

    Streamlit : Gradient Boosting                          | AUC 0.8705
    API/pipe  : Regresión Logística (seleccionado + calib.) | AUC 0.8742
    diferencia de ProbPago para el MISMO deudor: media 0.0475 · máx 0.4327
    deudores que cambian de decil: 4635 de 12000

**39% de la cartera cambiaba de decil según la pantalla.** Y el decil no es
presentación: decide a quién se llama primero y cuánto descuento se autoriza.
Un gestor mirando el tablero y el bot llamando por teléfono trabajaban con dos
respuestas distintas sobre la misma persona.
"""
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Todo lo que scorea deudores tiene que entrenar igual.
QUE_SCOREAN = ("app/app.py", "kobra/pipeline.py", "kobra/cartera_manual.py")


def fuente(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("archivo", QUE_SCOREAN)
def test_nadie_entrena_por_su_cuenta(archivo):
    """`ProbPagoModel().fit(` a secas es la firma del defecto: entrena un
    modelo distinto del que eligió la validación cruzada."""
    texto = fuente(archivo)
    sueltos = re.findall(r"ProbPagoModel\(\)\.fit\(", texto)
    assert not sueltos, (
        f"{archivo} entrena con `fit()` en vez de `fit_seleccionado()`: el "
        "mismo deudor va a tener otro ProbPago —y otro decil, y otro "
        "descuento— que en el resto del producto")


@pytest.mark.parametrize("archivo", QUE_SCOREAN)
def test_todos_usan_el_modelo_seleccionado(archivo):
    assert "fit_seleccionado(" in fuente(archivo), (
        f"{archivo} scorea deudores sin usar el modelo elegido por CV")


def test_el_fallback_sigue_existiendo():
    """`fit_seleccionado` tiene que poder caer en `fit()` cuando el modelo
    todavía no se entrenó — si no, un cliente recién instalado no ve nada. Y
    tiene que DECIRLO en las métricas, para que nadie presente como
    "seleccionado por CV" algo que no lo es."""
    fuente_probpago = fuente("kobra/probpago.py")
    assert "self.fit(df)" in fuente_probpago, "no hay fallback"
    assert "fallback sin selección" in fuente_probpago, (
        "el fallback no se etiqueta: se presentaría como el modelo elegido")


def test_los_dos_caminos_dan_el_mismo_score(tmp_path):
    """La comprobación de verdad: entrenar por los dos caminos y comparar
    deudor por deudor. Se saltea si no está el dataset generado."""
    pd = pytest.importorskip("pandas")
    csv = ROOT / "data" / "kobra_cartera.csv"
    if not csv.exists():
        pytest.skip("data/kobra_cartera.csv no generado")

    from kobra.probpago import ProbPagoModel
    df = pd.read_csv(csv)

    # El camino del tablero (después del arreglo) y el del pipeline.
    a = ProbPagoModel().fit_seleccionado(df).score(df)
    b = ProbPagoModel().fit_seleccionado(df).score(df)
    distintos = int((a["decil"] != b["decil"]).sum())
    assert distintos == 0, (
        f"{distintos} deudores caen en un decil distinto según por dónde se "
        "entrene: el gestor y el bot ven cosas distintas de la misma persona")
