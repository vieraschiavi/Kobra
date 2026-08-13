# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Entrenamiento ML de ProbPago (model selection)
======================================================
Mejora el modelo de probabilidad de pago pasando de un único estimador a una
**selección de modelos**: entrena y compara varios algoritmos con validación
cruzada, elige el mejor por ROC-AUC, lo calibra y lo persiste en disco.

Modelos comparados:
    - Regresión Logística (baseline lineal, interpretable)
    - Random Forest
    - Gradient Boosting
    - HistGradientBoosting (rápido, maneja no linealidades)
    - Ensemble v13 (promedio de dos boosting con configuraciones distintas —
      motor adaptado del ProbPago v13 walk-forward; ver nota abajo)

Nota sobre el motor v13 (evaluado el 2026-08-05):
    Se pidió reemplazar la metodología por el motor v13 "si es mejor". Se
    corrió el backtest con ESTE mismo protocolo (mismos folds, misma semilla,
    mismo holdout) y sobre la cartera sintética el resultado fue:

        LogisticRegression  CV-AUC 0.8728 · holdout 0.8744 · Brier 0.1417
        Ensemble v13        CV-AUC 0.8647 · holdout 0.8690 · Brier 0.1444
        Segmentado v13      CV-AUC 0.8626 (OOF) → rechazado por su propio
                            umbral de ganancia (gain_threshold=0.005)

    No es sorpresa: el generador sintético produce `pago` desde un score
    latente LINEAL con enlace logístico, así que la Regresión Logística es
    prácticamente la familia óptima para estos datos. En una cartera real con
    no-linealidades, el boosting suele ganar — por eso el motor v13 queda como
    CANDIDATO: si con los datos de un cliente gana la validación cruzada, la
    selección lo elige sola, sin tocar código. La segmentación por modelo
    (automl_segmentado) quedó afuera: perdió por -0.0102 contra el global.

    Ojo: si algún día un modelo de árboles gana la selección, el scoring del
    demo web deja de poder exportarse (`kobra.exportar_modelo_web` se planta
    a propósito: solo reimplementa modelos lineales en JS). Ese es el aviso
    para decidir entre servir el scoring desde backend o destilar el modelo.

Salidas:
    - outputs/probpago_model.joblib      (mejor modelo, listo para producción)
    - outputs/model_selection.json       (ranking y métricas de todos)

Uso:
    python -m kobra.train
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import rutas as krutas  # noqa: E402
from kobra.probpago import CAT_FEATURES, NUM_FEATURES, TARGET  # noqa: E402

# Escribible siempre (ver kobra/rutas.py): en dev/tests es el repo, igual
# que antes; instalado, es una carpeta propia del usuario, no Program Files.
OUT_DIR = os.path.join(krutas.DIR_DATOS, "outputs")
DATA_CSV = os.path.join(krutas.DIR_DATOS, "data", "kobra_cartera.csv")


def _preprocessor(scale=False):
    num = StandardScaler() if scale else "passthrough"
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
        ("num", num, NUM_FEATURES),
    ])


def _modelos():
    return {
        "LogisticRegression": Pipeline([
            ("pre", _preprocessor(scale=True)),
            ("clf", LogisticRegression(max_iter=1000, C=0.5)),
        ]),
        "RandomForest": Pipeline([
            ("pre", _preprocessor()),
            ("clf", RandomForestClassifier(
                n_estimators=300, max_depth=12, min_samples_leaf=20,
                n_jobs=-1, random_state=42)),
        ]),
        "GradientBoosting": Pipeline([
            ("pre", _preprocessor()),
            ("clf", GradientBoostingClassifier(
                n_estimators=250, max_depth=3, learning_rate=0.06,
                subsample=0.9, random_state=42)),
        ]),
        "HistGradientBoosting": Pipeline([
            ("pre", _preprocessor()),
            ("clf", HistGradientBoostingClassifier(
                max_depth=4, learning_rate=0.07, max_iter=300,
                l2_regularization=1.0, random_state=42)),
        ]),
        # Motor del ProbPago v13: promedio en probabilidad de dos boosting con
        # configuraciones deliberadamente distintas (una flexible, una muy
        # regularizada). Son las dos configs del v13 original con su fallback
        # sin LightGBM (HistGradientBoosting), que es exactamente como corre
        # ese motor cuando LightGBM no está instalado — y acá no lo está a
        # propósito: agregarlo engordaría el instalador de Windows para un
        # candidato que hoy no gana.
        "EnsembleV13": Pipeline([
            ("pre", _preprocessor()),
            ("clf", VotingClassifier([
                ("hgb_a", HistGradientBoostingClassifier(
                    max_leaf_nodes=31, learning_rate=0.05, max_iter=350,
                    l2_regularization=5.0, early_stopping=True,
                    random_state=42)),
                ("hgb_b", HistGradientBoostingClassifier(
                    max_leaf_nodes=15, learning_rate=0.03, max_iter=450,
                    l2_regularization=20.0, early_stopping=True,
                    random_state=42)),
            ], voting="soft", n_jobs=-1)),
        ]),
    }


def _ks(y, p):
    """Kolmogorov-Smirnov: separación máxima entre las distribuciones
    acumuladas de pagadores y no pagadores. Métrica clásica de scoring de
    crédito (viene de la suite del ProbPago v13): mide poder de ordenamiento
    sin depender de un umbral.

    Se acumula POR UMBRAL ÚNICO y no fila a fila. La versión fila a fila (la
    del v13 original) tiene un defecto con empates: como el sort es estable,
    un modelo que da la MISMA probabilidad a todos conserva el orden de
    llegada y puede reportar KS=1.0 — separación perfecta para un modelo que
    no separa nada. Lo atrapó el test del caso degenerado. Con scores
    continuos ambas versiones coinciden (los grupos son de una fila)."""
    d = (pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
         .groupby("p", sort=True)["y"].agg(pos="sum", n="count"))
    tot1 = max(int(d["pos"].sum()), 1)
    tot0 = max(int((d["n"] - d["pos"]).sum()), 1)
    c1 = d["pos"].cumsum() / tot1
    c0 = (d["n"] - d["pos"]).cumsum() / tot0
    return float(np.abs(c1 - c0).max())


def _ece(y, p, bins=10):
    """Expected Calibration Error: cuánto se aparta la probabilidad dicha de
    la frecuencia observada, promediado por decil. Complementa al Brier: un
    modelo puede ordenar bien (AUC alto) y aun así decir '80%' donde paga el
    60% — eso es lo que castiga el ECE.

    El caso degenerado importa: con probabilidad CONSTANTE, `qcut` colapsa
    los deciles y la suma quedaba vacía -> ECE 0.0 para el modelo del ejemplo
    de arriba, que es exactamente el que hay que castigar. Si no hay deciles
    válidos, el ECE es la distancia entre la media dicha y la observada."""
    y, p = np.asarray(y), np.asarray(p)
    q = pd.qcut(pd.Series(p), bins, duplicates="drop", labels=False)
    niveles = pd.Series(q).dropna().unique()
    if len(niveles) == 0:
        return float(abs(y.mean() - p.mean()))
    return float(sum(
        (q == b).sum() / len(p)
        * abs(y[(q == b).values].mean() - p[(q == b).values].mean())
        for b in niveles))


def entrenar(df: pd.DataFrame = None, guardar=True):
    if df is None:
        df = pd.read_csv(DATA_CSV)
    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    resultados = []
    modelos = _modelos()
    for nombre, pipe in modelos.items():
        cv_auc = cross_val_score(pipe, X_tr, y_tr, cv=cv, scoring="roc_auc", n_jobs=-1)
        pipe.fit(X_tr, y_tr)
        p = pipe.predict_proba(X_te)[:, 1]
        resultados.append({
            "modelo": nombre,
            "cv_auc_mean": round(float(cv_auc.mean()), 4),
            "cv_auc_std": round(float(cv_auc.std()), 4),
            "test_auc_roc": round(float(roc_auc_score(y_te, p)), 4),
            "test_auc_pr": round(float(average_precision_score(y_te, p)), 4),
            "test_brier": round(float(brier_score_loss(y_te, p)), 4),
            "test_ks": round(_ks(y_te, p), 4),
            "test_ece": round(_ece(y_te, p), 4),
        })
        print(f"  {nombre:22s} CV-AUC={cv_auc.mean():.4f}±{cv_auc.std():.4f} "
              f"Test-AUC={resultados[-1]['test_auc_roc']:.4f}")

    resultados.sort(key=lambda r: r["cv_auc_mean"], reverse=True)
    mejor_nombre = resultados[0]["modelo"]
    print(f"\n[train] Mejor modelo: {mejor_nombre} "
          f"(CV-AUC={resultados[0]['cv_auc_mean']})")

    # Lift del decil superior del mejor modelo, sobre el mismo holdout usado para el ranking
    mejor_holdout = _modelos()[mejor_nombre]
    mejor_holdout.fit(X_tr, y_tr)
    p_best_te = mejor_holdout.predict_proba(X_te)[:, 1]
    te = pd.DataFrame({"y": y_te.values, "p": p_best_te})
    te["decil"] = pd.qcut(te["p"].rank(method="first"), 10, labels=False) + 1
    lift_decil10 = round(float(te[te["decil"] == 10]["y"].mean() / y.mean()), 2)

    # Calibrar el mejor modelo sobre todo el train y re-entrenar en full data
    mejor = _modelos()[mejor_nombre]
    calibrado = CalibratedClassifierCV(mejor, method="isotonic", cv=3)
    calibrado.fit(X, y)

    reporte = {
        "mejor_modelo": mejor_nombre,
        "auc_roc": resultados[0]["test_auc_roc"],
        "auc_pr": resultados[0]["test_auc_pr"],
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "tasa_pago_base": round(float(y.mean()), 4),
        "lift_decil10": lift_decil10,
        "ranking": resultados,
        "n_muestras": int(len(df)),
        "features_num": NUM_FEATURES,
        "features_cat": CAT_FEATURES,
    }

    if guardar:
        os.makedirs(OUT_DIR, exist_ok=True)
        try:
            import joblib
            joblib.dump(calibrado, os.path.join(OUT_DIR, "probpago_model.joblib"))
            reporte["modelo_persistido"] = "outputs/probpago_model.joblib"
        except Exception as e:
            reporte["modelo_persistido"] = f"no guardado ({e})"
        with open(os.path.join(OUT_DIR, "model_selection.json"), "w",
                  encoding="utf-8") as f:
            json.dump(reporte, f, ensure_ascii=False, indent=2)
        print(f"[train] Reporte: {OUT_DIR}/model_selection.json")

    return reporte, calibrado


if __name__ == "__main__":
    print("[train] Comparando modelos ML para ProbPago…")
    entrenar()
