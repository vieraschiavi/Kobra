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
from sklearn.ensemble import (GradientBoostingClassifier,
                              HistGradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra.probpago import NUM_FEATURES, CAT_FEATURES, TARGET   # noqa: E402

OUT_DIR = os.path.join(ROOT, "outputs")
DATA_CSV = os.path.join(ROOT, "data", "kobra_cartera.csv")


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
    }


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
