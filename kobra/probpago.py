# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · ProbPago
================
Modelo de probabilidad de pago (payment propensity) para carteras de
cobranzas. Entrena un Gradient Boosting sobre features de comportamiento
y mora, y devuelve para cada deudor:

    - probpago            : probabilidad de recupero (0-1)
    - decil               : decil de propensión (10 = mejor)
    - segmento_propension : Alta / Media / Baja

Es agnóstico del cliente: cualquier empresa puede entrenarlo con su cartera
respetando el esquema de columnas.
"""
import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from kobra import rutas as _krutas

# Escribible siempre (ver kobra/rutas.py): en dev/tests es el repo, igual
# que antes; instalado, es una carpeta propia del usuario, no Program Files.
_ROOT = _krutas.DIR_DATOS
_MODEL_PATH = os.path.join(_ROOT, "outputs", "probpago_model.joblib")
_SELECTION_PATH = os.path.join(_ROOT, "outputs", "model_selection.json")
_MODEL_DISPLAY = {
    "LogisticRegression": "Regresión Logística",
    "RandomForest": "Random Forest",
    "GradientBoosting": "Gradient Boosting",
    "HistGradientBoosting": "HistGradientBoosting",
    "EnsembleV13": "Ensemble Boosting (motor v13)",
}

NUM_FEATURES = [
    "monto_deuda", "dias_mora", "cuotas_atrasadas", "antiguedad_cliente_meses",
    "score_buro", "ingreso_estimado", "pagos_ultimos_12m",
    "promesas_cumplidas", "promesas_incumplidas", "contactabilidad",
    "gestiones_previas",
]
CAT_FEATURES = ["segmento", "producto", "departamento", "canal_preferido"]
TARGET = "pago"


@dataclass
class ProbPagoModel:
    pipeline: Pipeline = None
    metrics: dict = field(default_factory=dict)

    def fit(self, df: pd.DataFrame):
        X = df[NUM_FEATURES + CAT_FEATURES]
        y = df[TARGET]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y)

        pre = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
            ("num", "passthrough", NUM_FEATURES),
        ])
        clf = GradientBoostingClassifier(
            n_estimators=250, max_depth=3, learning_rate=0.06,
            subsample=0.9, random_state=42)
        self.pipeline = Pipeline([("pre", pre), ("clf", clf)])
        self.pipeline.fit(X_tr, y_tr)

        p_te = self.pipeline.predict_proba(X_te)[:, 1]
        self.metrics = {
            "auc_roc": round(float(roc_auc_score(y_te, p_te)), 4),
            "auc_pr": round(float(average_precision_score(y_te, p_te)), 4),
            "n_train": int(len(X_tr)),
            "n_test": int(len(X_te)),
            "tasa_pago_base": round(float(y.mean()), 4),
        }
        # Lift del decil superior vs. base
        te = pd.DataFrame({"y": y_te.values, "p": p_te})
        te["decil"] = pd.qcut(te["p"].rank(method="first"), 10, labels=False) + 1
        top = te[te["decil"] == 10]["y"].mean()
        self.metrics["lift_decil10"] = round(float(top / y.mean()), 2)
        self.metrics["modelo"] = "Gradient Boosting"
        return self

    def fit_seleccionado(self, df: pd.DataFrame):
        """Como `fit()`, pero usa el modelo elegido por `kobra.train` (comparación
        con validación cruzada entre Regresión Logística/RF/GBM/HistGB + calibración
        isotónica), si ya fue entrenado (`outputs/probpago_model.joblib` +
        `outputs/model_selection.json`). Sin eso, cae en el Gradient Boosting
        ad-hoc de `fit()` — mismo comportamiento de siempre, pero etiquetado con
        honestidad en `metrics['modelo']`."""
        try:
            import joblib
            if os.path.exists(_MODEL_PATH) and os.path.exists(_SELECTION_PATH):
                with open(_SELECTION_PATH, encoding="utf-8") as f:
                    sel = json.load(f)
                requeridas = ("auc_roc", "auc_pr", "n_train", "n_test",
                              "tasa_pago_base", "lift_decil10", "mejor_modelo")
                if all(sel.get(k) is not None for k in requeridas):
                    self.pipeline = joblib.load(_MODEL_PATH)
                    nombre = sel["mejor_modelo"]
                    self.metrics = {
                        "auc_roc": sel["auc_roc"], "auc_pr": sel["auc_pr"],
                        "n_train": sel["n_train"], "n_test": sel["n_test"],
                        "tasa_pago_base": sel["tasa_pago_base"],
                        "lift_decil10": sel["lift_decil10"],
                        "modelo": _MODEL_DISPLAY.get(nombre, nombre)
                        + " (seleccionado por CV + calibrado)",
                    }
                    return self
        except Exception:
            pass
        self.fit(df)
        self.metrics["modelo"] = (
            "Gradient Boosting (fallback sin selección — corré "
            "`python -m kobra.train` para elegir y calibrar el mejor modelo)")
        return self

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["probpago"] = self.pipeline.predict_proba(
            out[NUM_FEATURES + CAT_FEATURES])[:, 1]
        out["decil"] = (
            pd.qcut(out["probpago"].rank(method="first"), 10, labels=False) + 1)
        out["segmento_propension"] = pd.cut(
            out["probpago"], bins=[-0.01, 0.35, 0.65, 1.01],
            labels=["Baja", "Media", "Alta"])
        return out

    def _pipeline_ajustado(self):
        """Devuelve el Pipeline (pre + clf) ya ajustado, sea `fit()` (Pipeline
        directo) o `fit_seleccionado()` (CalibratedClassifierCV envolviendo un
        Pipeline por cada fold de calibración — se usa el del primer fold)."""
        if hasattr(self.pipeline, "named_steps"):
            return self.pipeline
        calibrados = getattr(self.pipeline, "calibrated_classifiers_", None)
        if calibrados:
            base = calibrados[0]
            return getattr(base, "estimator", None) or getattr(base, "base_estimator", None)
        return None

    def feature_importance(self) -> pd.DataFrame:
        pipe = self._pipeline_ajustado()
        pre = pipe.named_steps["pre"]
        clf = pipe.named_steps["clf"]
        cat_names = list(
            pre.named_transformers_["cat"].get_feature_names_out(CAT_FEATURES))
        names = cat_names + NUM_FEATURES
        if hasattr(clf, "feature_importances_"):        # modelos de árboles
            valores = clf.feature_importances_
        elif hasattr(clf, "coef_"):                      # modelos lineales (Regresión Logística)
            valores = np.abs(clf.coef_[0])
        else:
            valores = np.zeros(len(names))
        imp = pd.DataFrame({"feature": names, "importancia": valores})
        return imp.sort_values("importancia", ascending=False).reset_index(drop=True)
