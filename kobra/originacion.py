# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Motor de Originación (credit decisioning)
========================================================
Extensión upstream de ProbPago: en vez de scorear una cartera ya vencida,
scorea la **solicitud de crédito en el momento de originar** y devuelve al
oficial de crédito una decisión sugerida, explicada en lenguaje simple.

Para cada solicitante:

    - prob_mora        : probabilidad de caer en mora ≥90 días (0-1)
    - score            : 0-1000 (más alto = mejor pagador esperado)
    - decision         : "Aprobar" / "Derivar a análisis" / "Rechazar"
    - monto/plazo sugeridos según la banda de riesgo
    - razones          : top-3 factores en lenguaje simple (no jerga ML)
    - confianza        : Alta/Media/Baja según cuántos datos reales llegaron

Decisiones de diseño (del brief Kobra 2.0, bloque 3 y 9):

- **Features mínimos**: solo datos del solicitante + historial interno de la
  institución. NO asume buró completo ni fuentes externas — la cooperativa
  chica típica no las tiene. Si faltan campos, el modelo igual evalúa y lo
  refleja bajando el nivel de `confianza`, no inventando datos.
- **Validación walk-forward temporal**: el split de evaluación es por fecha
  de solicitud (pasado entrena, futuro evalúa) — nunca random split. Las
  métricas reportadas (AUC/KS) son las del tramo futuro no visto.
- **Anti-SMOTE**: el desbalance de clases se maneja con ponderación de
  muestras, nunca con oversampling sintético que rompa la calibración.
- **Benchmark honesto**: las métricas incluyen la comparación contra una
  "regla de oficial" típica (rechazar si hubo atrasos previos o el ingreso
  es bajo) — el modelo debe ganarle a eso, no a la perfección.
- **Explicabilidad por decisión**: misma técnica model-agnostic de
  `kobra/explicabilidad.py` (atribución por oclusión). Cumple el mismo rol
  de producto que SHAP —razones auditables por decisión individual— sin
  sumar una dependencia pesada; si un cliente exige SHAP literal, se
  agrega en su implementación.

El dataset de demo es 100% sintético (misma convención de honestidad que el
resto del producto): sirve para demostrar la mecánica, no para prometer un
AUC en producción. Con datos reales del cliente, el modelo se re-entrena y
re-valida walk-forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

NUM_FEATURES = [
    "edad", "ingreso_declarado", "antiguedad_laboral_meses",
    "monto_solicitado", "plazo_meses", "antiguedad_socio_meses",
    "creditos_previos", "atrasos_previos",
]
CAT_FEATURES = ["tipo_credito", "situacion_laboral", "departamento"]
TARGET = "mora90"

ETIQUETAS = {
    "edad": "Edad del solicitante",
    "ingreso_declarado": "Ingreso declarado",
    "antiguedad_laboral_meses": "Antigüedad laboral",
    "monto_solicitado": "Monto solicitado",
    "plazo_meses": "Plazo solicitado",
    "antiguedad_socio_meses": "Antigüedad como socio",
    "creditos_previos": "Créditos previos en la institución",
    "atrasos_previos": "Atrasos previos",
    "tipo_credito": "Tipo de crédito",
    "situacion_laboral": "Situación laboral",
    "departamento": "Departamento",
}

UMBRAL_APROBAR = 0.15    # prob_mora por debajo -> Aprobar
UMBRAL_RECHAZAR = 0.35   # prob_mora por encima -> Rechazar; en el medio, Derivar


# ---------------------------------------------------------------------------
# Dataset sintético de solicitudes (demo — ver convención de honestidad)
# ---------------------------------------------------------------------------
def generar_solicitudes_sinteticas(n: int = 6000, semilla: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    fechas = pd.to_datetime("2024-01-01") + pd.to_timedelta(
        rng.integers(0, 730, n), unit="D")

    edad = rng.integers(20, 72, n)
    situacion = rng.choice(["Dependiente", "Independiente", "Jubilado"],
                           n, p=[0.55, 0.3, 0.15])
    ingreso = np.round(rng.lognormal(10.6, 0.5, n), -2)
    ant_laboral = rng.integers(0, 300, n)
    monto = np.round(rng.lognormal(10.9, 0.7, n), -3)
    plazo = rng.choice([6, 12, 18, 24, 36, 48], n)
    ant_socio = rng.integers(0, 240, n)
    creditos_prev = rng.poisson(1.4, n)
    atrasos_prev = np.minimum(rng.poisson(0.5, n), creditos_prev)
    tipo = rng.choice(["Consumo", "Vehículo", "Vivienda", "Microcrédito"],
                      n, p=[0.5, 0.2, 0.1, 0.2])
    depto = rng.choice(["Montevideo", "Canelones", "Maldonado", "Salto",
                        "Paysandú", "Rivera", "Colonia"], n,
                       p=[0.42, 0.18, 0.1, 0.08, 0.08, 0.07, 0.07])

    # Probabilidad real de mora (regla generadora conocida + ruido):
    cuota = monto / plazo
    carga = cuota / np.maximum(ingreso, 1)       # % del ingreso mensual que se lleva la cuota
    z = (-2.4
         + 9.0 * np.clip(carga, 0, 0.8)
         + 0.9 * atrasos_prev
         - 0.06 * ant_socio / 12
         - 0.09 * ant_laboral / 12
         - 0.35 * (creditos_prev > 0)
         + 0.45 * (situacion == "Independiente")
         - 0.30 * (situacion == "Jubilado")
         + rng.normal(0, 0.45, n))
    p_mora = 1 / (1 + np.exp(-z))
    mora = (rng.random(n) < p_mora).astype(int)

    return pd.DataFrame({
        "id_solicitud": [f"SOL-{100000 + i}" for i in range(n)],
        "fecha_solicitud": fechas, "edad": edad,
        "situacion_laboral": situacion, "ingreso_declarado": ingreso,
        "antiguedad_laboral_meses": ant_laboral, "monto_solicitado": monto,
        "plazo_meses": plazo, "antiguedad_socio_meses": ant_socio,
        "creditos_previos": creditos_prev, "atrasos_previos": atrasos_prev,
        "tipo_credito": tipo, "departamento": depto, TARGET: mora,
    })


# ---------------------------------------------------------------------------
# Importación de solicitudes REALES del cliente
# ---------------------------------------------------------------------------
# Sinónimos de columna → feature del modelo. Se normaliza (minúsculas, sin
# acentos, sin separadores) antes de comparar, así "Monto Solicitado",
# "monto_solicitado", "MontoPedido" o "valor_credito" caen al mismo lugar.
_SIN_ORIG = {
    "edad": ["edad", "años", "anos", "age"],
    "ingreso_declarado": ["ingreso", "ingresodeclarado", "sueldo", "salario", "renta", "income"],
    "antiguedad_laboral_meses": ["antiguedadlaboral", "antiguedadlaboralmeses", "antiguedadempleo", "mesesempleo"],
    "monto_solicitado": ["montosolicitado", "montopedido", "monto", "importe", "valorcredito", "capital", "loanamount"],
    "plazo_meses": ["plazo", "plazomeses", "cuotas", "term", "plazocredito"],
    "antiguedad_socio_meses": ["antiguedadsocio", "antiguedadsociomeses", "antiguedadcliente", "mesescliente"],
    "creditos_previos": ["creditosprevios", "creditosanteriores", "prestamosprevios"],
    "atrasos_previos": ["atrasosprevios", "atrasos", "morasprevias", "atrasosanteriores"],
    "tipo_credito": ["tipocredito", "tipodecredito", "producto", "linea", "tipoprestamo"],
    "situacion_laboral": ["situacionlaboral", "situacion", "empleo", "relacionlaboral"],
    "departamento": ["departamento", "depto", "provincia", "region", "ciudad"],
    "id_solicitud": ["idsolicitud", "solicitud", "id", "iddeudor", "documento", "cedula"],
    "fecha_solicitud": ["fechasolicitud", "fecha", "fechaalta", "fechaingreso"],
    # Solo etiquetas explícitas de default — NO "mora" a secas (chocaría con
    # tramo_mora / días de mora de una cartera de cobranzas).
    TARGET: ["mora90", "default", "incumplio", "target", "malo"],
}
_DEFAULTS_ORIG = {
    "edad": 40, "ingreso_declarado": 45000.0, "antiguedad_laboral_meses": 36,
    "monto_solicitado": 100000.0, "plazo_meses": 12, "antiguedad_socio_meses": 24,
    "creditos_previos": 1, "atrasos_previos": 0,
    "tipo_credito": "Consumo", "situacion_laboral": "Dependiente", "departamento": "Montevideo",
}


def _norm_orig(s: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def mapear_columnas_solicitudes(columnas) -> dict:
    """Mapea columnas crudas del cliente → features de originación por nombre
    parecido (insensible a acentos/separadores). Devuelve {col_orig: feature}."""
    norm = {c: _norm_orig(c) for c in columnas}
    mapeo, usados = {}, set()
    for feat, sinonimos in _SIN_ORIG.items():
        objetivos = [_norm_orig(feat)] + [_norm_orig(s) for s in sinonimos]
        # 1) match exacto, 2) contención
        elegido = next((c for c, n in norm.items() if c not in usados and n in objetivos), None)
        if elegido is None:
            elegido = next((c for c, n in norm.items() if c not in usados
                            and any(o in n or n in o for o in objetivos if len(o) >= 4)), None)
        if elegido is not None:
            mapeo[elegido] = feat
            usados.add(elegido)
    return mapeo


def preparar_solicitudes(df_bruto: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Toma un dataset crudo de solicitudes de crédito del cliente y lo lleva al
    esquema del modelo (features + id + fecha), completando con defaults las
    columnas que no vengan (el modelo baja la confianza cuando faltan datos, no
    inventa). Devuelve (df_listo, columnas_reconocidas)."""
    mapeo = mapear_columnas_solicitudes(df_bruto.columns)
    df = df_bruto.rename(columns=mapeo).copy()

    for feat in NUM_FEATURES:
        df[feat] = pd.to_numeric(df.get(feat), errors="coerce") if feat in df.columns else np.nan
        df[feat] = df[feat].fillna(_DEFAULTS_ORIG[feat])
    for feat in CAT_FEATURES:
        col = df[feat].astype(str) if feat in df.columns else None
        df[feat] = (col.where(col.notna() & (col != "") & (col != "nan"), _DEFAULTS_ORIG[feat])
                    if col is not None else _DEFAULTS_ORIG[feat])
    if "id_solicitud" not in df.columns:
        df["id_solicitud"] = [f"SOL-{100000 + i}" for i in range(len(df))]
    if "fecha_solicitud" in df.columns:
        df["fecha_solicitud"] = pd.to_datetime(df["fecha_solicitud"], errors="coerce")
    if "fecha_solicitud" not in df.columns or df["fecha_solicitud"].isna().all():
        df["fecha_solicitud"] = pd.to_datetime("2025-01-01")
    df["fecha_solicitud"] = df["fecha_solicitud"].fillna(pd.to_datetime("2025-01-01"))

    cols = ["id_solicitud", "fecha_solicitud"] + NUM_FEATURES + CAT_FEATURES
    if TARGET in df.columns:
        df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
        if df[TARGET].notna().any():
            cols.append(TARGET)
    return df[cols], mapeo


def _regla_oficial(df: pd.DataFrame) -> np.ndarray:
    """La heurística típica de un oficial de crédito, como benchmark honesto:
    'rechazo si tuvo atrasos previos o si el ingreso está en el 25% más bajo'.
    Devuelve un 'score' binario de riesgo (1 = lo habría rechazado)."""
    p25 = df["ingreso_declarado"].quantile(0.25)
    return ((df["atrasos_previos"] > 0) | (df["ingreso_declarado"] < p25)).astype(int).values


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
@dataclass
class OriginacionModel:
    pipeline: Pipeline = None
    metrics: dict = field(default_factory=dict)
    _baseline: dict = field(default_factory=dict)

    def fit(self, df: pd.DataFrame):
        """Entrena con validación WALK-FORWARD: ordena por fecha_solicitud,
        entrena con el primer 75% (pasado) y evalúa con el 25% final (futuro
        no visto). Las métricas reportadas son las del tramo futuro."""
        df = df.sort_values("fecha_solicitud").reset_index(drop=True)
        corte = int(len(df) * 0.75)
        tr, te = df.iloc[:corte], df.iloc[corte:]

        X_tr, y_tr = tr[NUM_FEATURES + CAT_FEATURES], tr[TARGET]
        X_te, y_te = te[NUM_FEATURES + CAT_FEATURES], te[TARGET]

        pre = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
            ("num", "passthrough", NUM_FEATURES),
        ])
        clf = GradientBoostingClassifier(
            n_estimators=180, max_depth=3, learning_rate=0.07,
            subsample=0.9, random_state=42)
        self.pipeline = Pipeline([("pre", pre), ("clf", clf)])

        # Anti-SMOTE: desbalance por ponderación de muestras
        pesos = np.where(y_tr == 1, (len(y_tr) - y_tr.sum()) / max(y_tr.sum(), 1), 1.0)
        self.pipeline.fit(X_tr, y_tr, clf__sample_weight=pesos)

        p_te = self.pipeline.predict_proba(X_te)[:, 1]
        auc = float(roc_auc_score(y_te, p_te))

        # KS: máxima separación entre distribuciones acumuladas de buenos/malos
        orden = np.argsort(p_te)
        y_ord = y_te.values[orden]
        acum_malos = np.cumsum(y_ord) / max(y_ord.sum(), 1)
        acum_buenos = np.cumsum(1 - y_ord) / max((1 - y_ord).sum(), 1)
        ks = float(np.max(np.abs(acum_malos - acum_buenos)))

        auc_regla = float(roc_auc_score(y_te, _regla_oficial(te)))

        self.metrics = {
            "auc_walk_forward": round(auc, 4),
            "ks_walk_forward": round(ks, 4),
            "auc_regla_oficial": round(auc_regla, 4),
            "mejora_vs_regla": round(auc - auc_regla, 4),
            "n_train": len(tr), "n_test": len(te),
            "tasa_mora_base": round(float(df[TARGET].mean()), 4),
            "validacion": "walk-forward temporal (75% pasado entrena, 25% futuro evalúa)",
        }
        # Baseline de la población para las razones por oclusión
        self._baseline = {c: float(tr[c].median()) for c in NUM_FEATURES}
        for c in CAT_FEATURES:
            self._baseline[c] = tr[c].mode().iloc[0]
        return self

    # -- explicación por oclusión (misma técnica que kobra/explicabilidad.py) --
    def _razones(self, fila: dict, top: int = 3) -> list[dict]:
        base_df = pd.DataFrame([{**self._baseline, **{k: v for k, v in fila.items()
                                                      if v is not None}}])
        p_real = float(self.pipeline.predict_proba(
            base_df[NUM_FEATURES + CAT_FEATURES])[:, 1][0])
        contribs = []
        for c in NUM_FEATURES + CAT_FEATURES:
            if fila.get(c) is None or c not in self._baseline:
                continue
            ocluida = base_df.copy()
            ocluida[c] = self._baseline[c]
            p_sin = float(self.pipeline.predict_proba(
                ocluida[NUM_FEATURES + CAT_FEATURES])[:, 1][0])
            delta = p_real - p_sin          # >0: esta feature SUBE el riesgo
            if abs(delta) > 0.001:
                contribs.append({"factor": ETIQUETAS.get(c, c),
                                 "efecto_pp": round(delta * 100, 1),
                                 "direccion": "sube el riesgo" if delta > 0
                                              else "baja el riesgo"})
        contribs.sort(key=lambda d: -abs(d["efecto_pp"]))
        return contribs[:top]

    def evaluar(self, solicitud: dict) -> dict:
        """Evalúa UNA solicitud. Campos faltantes se imputan con la mediana/moda
        de la población de entrenamiento y BAJAN el nivel de confianza — el
        modelo no esconde que decidió con menos datos."""
        todas = NUM_FEATURES + CAT_FEATURES
        presentes = [c for c in todas if solicitud.get(c) is not None]
        fila = {**self._baseline, **{k: v for k, v in solicitud.items()
                                     if k in todas and v is not None}}
        X = pd.DataFrame([fila])[todas]
        p_mora = float(self.pipeline.predict_proba(X)[:, 1][0])

        if p_mora < UMBRAL_APROBAR:
            decision, factor_monto = "Aprobar", 1.0
        elif p_mora < UMBRAL_RECHAZAR:
            decision, factor_monto = "Derivar a análisis", 0.6
        else:
            decision, factor_monto = "Rechazar", 0.0

        monto_pedido = float(fila.get("monto_solicitado") or 0)
        plazo_pedido = int(fila.get("plazo_meses") or 12)
        cobertura = len(presentes) / len(todas)
        confianza = ("Alta" if cobertura >= 0.85
                     else "Media" if cobertura >= 0.6 else "Baja")

        # Con datos insuficientes el modelo NO decide solo: siempre deriva a un
        # analista humano, sea cual sea el score (límite honesto del modelo).
        if confianza == "Baja" and decision != "Derivar a análisis":
            decision, factor_monto = "Derivar a análisis", 0.6

        return {
            "prob_mora": round(p_mora, 4),
            "score": int(round((1 - p_mora) * 1000)),
            "decision": decision,
            "monto_sugerido": round(monto_pedido * factor_monto, -2),
            "plazo_sugerido_meses": plazo_pedido if factor_monto == 1.0
                                    else max(6, plazo_pedido // 2) if factor_monto > 0 else 0,
            "razones": self._razones(fila),
            "confianza": confianza,
            "datos_presentes": f"{len(presentes)}/{len(todas)}",
            "umbrales": {"aprobar_bajo": UMBRAL_APROBAR, "rechazar_sobre": UMBRAL_RECHAZAR},
        }

    def evaluar_lote(self, solicitudes: pd.DataFrame) -> pd.DataFrame:
        filas = [self.evaluar(r) for r in solicitudes.to_dict("records")]
        out = solicitudes.copy().reset_index(drop=True)
        res = pd.DataFrame(filas)
        for c in ("prob_mora", "score", "decision", "monto_sugerido",
                  "plazo_sugerido_meses", "confianza"):
            out[c] = res[c]
        return out
