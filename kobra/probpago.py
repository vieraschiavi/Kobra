"""
Kobra · ProbPago
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
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

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

    def feature_importance(self) -> pd.DataFrame:
        pre = self.pipeline.named_steps["pre"]
        clf = self.pipeline.named_steps["clf"]
        cat_names = list(
            pre.named_transformers_["cat"].get_feature_names_out(CAT_FEATURES))
        names = cat_names + NUM_FEATURES
        imp = pd.DataFrame({"feature": names, "importancia": clf.feature_importances_})
        return imp.sort_values("importancia", ascending=False).reset_index(drop=True)
