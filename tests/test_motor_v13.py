"""El motor del ProbPago v13 dentro de la selección de modelos de Kobra.

Pedido: «reemplazar la metodología de prob cobro por este modelo si es mejor;
debe adaptarse a los datasets y base de datos como estaba programado».

El veredicto del backtest (mismo protocolo que `kobra.train`: mismos folds,
misma semilla, mismo holdout) fue que sobre la cartera sintética el motor v13
NO es mejor:

    LogisticRegression  CV-AUC 0.8728 · holdout 0.8744 · Brier 0.1417
    Ensemble v13        CV-AUC 0.8647 · holdout 0.8690 · Brier 0.1444
    Segmentado v13      CV-AUC 0.8626 (OOF) → rechazado por su propio umbral

Tiene explicación: el generador sintético produce `pago` desde un score
latente LINEAL con enlace logístico — la Regresión Logística es prácticamente
la familia óptima para ese proceso. El boosting gana en carteras reales con
no-linealidades, no acá.

La adaptación honesta no es reemplazar a ciegas sino sumar el motor como
CANDIDATO de la selección ya programada: si con los datos de un cliente gana
la validación cruzada, la selección lo elige sola. Estos tests fijan esa
integración y sus consecuencias.
"""
import json
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import train as kt  # noqa: E402

SELECCION = os.path.join(ROOT, "outputs", "model_selection.json")


@pytest.fixture(scope="module")
def seleccion():
    if not os.path.exists(SELECCION):
        pytest.skip("falta outputs/model_selection.json (correr kobra.train)")
    with open(SELECCION, encoding="utf-8") as f:
        return json.load(f)


# --- El motor está en la cancha ---------------------------------------------
def test_el_motor_v13_es_candidato_de_la_seleccion():
    modelos = kt._modelos()
    assert "EnsembleV13" in modelos, "el motor v13 salió de la selección"
    clf = modelos["EnsembleV13"].named_steps["clf"]
    # Promedio en probabilidad de DOS boosting con configs distintas: esa
    # diversidad (una flexible, una muy regularizada) es lo que aporta el
    # ensemble. Dos configs iguales serían el mismo modelo dos veces.
    assert type(clf).__name__ == "VotingClassifier" and clf.voting == "soft"
    a, b = (est for _, est in clf.estimators)
    assert (a.max_leaf_nodes, a.l2_regularization) != \
        (b.max_leaf_nodes, b.l2_regularization)


def test_el_ranking_persistido_incluye_al_motor_v13(seleccion):
    nombres = [r["modelo"] for r in seleccion["ranking"]]
    assert "EnsembleV13" in nombres
    assert len(nombres) >= 5


def test_el_ranking_trae_ks_y_ece(seleccion):
    """Las métricas de la suite del v13 que sí se adoptaron: KS (poder de
    ordenamiento) y ECE (calibración). Sin ellas, el ranking no muestra si un
    modelo dice '80%' donde paga el 60%."""
    for fila in seleccion["ranking"]:
        assert "test_ks" in fila and "test_ece" in fila, fila["modelo"]
        assert 0.0 <= fila["test_ks"] <= 1.0
        assert 0.0 <= fila["test_ece"] <= 1.0


# --- La decisión sigue siendo por evidencia, no por novedad ------------------
def test_en_la_cartera_sintetica_gana_el_modelo_lineal(seleccion):
    """El resultado del backtest, fijado sobre el artefacto commiteado (el
    dataset y las semillas están versionados, así que es determinista). Si
    esto falla, cambió el dataset o el protocolo — y hay que volver a mirar
    el veredicto, no borrar el test."""
    assert seleccion["mejor_modelo"] == "LogisticRegression"
    ranking = {r["modelo"]: r["cv_auc_mean"] for r in seleccion["ranking"]}
    assert ranking["LogisticRegression"] > ranking["EnsembleV13"], (
        "el motor v13 pasó a ganar en CV: revisar la nota de kobra/train.py "
        "y el export web antes de festejar")


def test_el_ganador_actual_sigue_siendo_exportable_al_navegador(seleccion):
    """Consecuencia operativa: el flujo 'subí tu CSV' de la demo scorea en el
    navegador con el modelo exportado, y `exportar_modelo_web` solo puede
    reimplementar modelos lineales. Mientras gane la Logística esto es
    coherente; si un día gana un árbol, este test avisa ANTES de que la demo
    quede sin scoring."""
    assert seleccion["mejor_modelo"] == "LogisticRegression"
    bundle = os.path.join(ROOT, "dashboard_estatico", "modelo_web.json")
    assert os.path.exists(bundle)
    with open(bundle, encoding="utf-8") as f:
        assert "LogisticRegression" in json.load(f)["modelo"]


# --- Las métricas nuevas, verificadas con casos donde la respuesta se conoce -
def test_ks_es_1_con_separacion_perfecta_y_0_sin_señal():
    y = np.array([0, 0, 0, 1, 1, 1])
    assert kt._ks(y, np.array([.1, .2, .3, .7, .8, .9])) == pytest.approx(1.0)
    # Misma probabilidad para todos: el orden no separa nada. El acumulado
    # avanza en bloque y el máximo desvío es el de una sola fila.
    assert kt._ks(y, np.full(6, .5)) <= 1 / 3


def test_ece_castiga_al_modelo_que_dice_80_donde_paga_60():
    rng = np.random.default_rng(42)
    p = np.full(4000, .8)
    y = (rng.random(4000) < .6).astype(int)
    assert kt._ece(y, p) == pytest.approx(.2, abs=.03)
    # Y premia al que dice la frecuencia real.
    p2 = np.full(4000, .6)
    assert kt._ece(y, p2) < .03
