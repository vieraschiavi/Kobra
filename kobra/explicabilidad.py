"""
Kobra IA · Explicabilidad de ProbPago (reason codes por deudor)
===============================================================
Responde, para un deudor concreto, **por qué** el modelo le asignó esa
probabilidad de pago: qué características la empujan hacia arriba y cuáles
hacia abajo, y cuánto (en puntos porcentuales).

Método: **atribución por oclusión** (model-agnostic). Se compara la predicción
con el valor real de cada feature contra la predicción llevando esa feature a
un valor "base" de la cartera (mediana para numéricas, moda para categóricas).
La diferencia es la contribución de esa feature para *ese* deudor. Funciona con
cualquier modelo del pipeline (Regresión Logística, GB, etc.) sin depender de
su interna.

Para qué sirve comercialmente: las decisiones automatizadas sobre personas
(a quién se prioriza, qué descuento se ofrece) deben poder **explicarse** —lo
exige la Ley 18.331 de Uruguay y marcos equivalentes en la región—. Esto
convierte a ProbPago de "caja negra" en una decisión auditable y defendible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from kobra.probpago import CAT_FEATURES, NUM_FEATURES

# Nombres legibles para las reason codes (sin jerga de features)
ETIQUETAS = {
    "monto_deuda": "Monto de la deuda",
    "dias_mora": "Días de mora",
    "cuotas_atrasadas": "Cuotas atrasadas",
    "antiguedad_cliente_meses": "Antigüedad como cliente",
    "score_buro": "Score de buró",
    "ingreso_estimado": "Ingreso estimado",
    "pagos_ultimos_12m": "Pagos en los últimos 12 meses",
    "promesas_cumplidas": "Promesas cumplidas",
    "promesas_incumplidas": "Promesas incumplidas",
    "contactabilidad": "Contactabilidad",
    "gestiones_previas": "Gestiones previas",
    "segmento": "Segmento",
    "producto": "Producto",
    "departamento": "Departamento",
    "canal_preferido": "Canal preferido",
}


def baseline_cartera(df: pd.DataFrame) -> dict:
    """Valor 'neutro' de referencia por feature: mediana (num) / moda (cat)."""
    base = {}
    for c in NUM_FEATURES:
        if c in df.columns:
            base[c] = float(df[c].median())
    for c in CAT_FEATURES:
        if c in df.columns and not df[c].mode().empty:
            base[c] = df[c].mode().iloc[0]
    return base


def _predict_proba(model, X: pd.DataFrame) -> np.ndarray:
    pipe = getattr(model, "pipeline", model)
    return pipe.predict_proba(X)[:, 1]


def explicar(model, fila, baseline: dict, top: int = 3) -> list[dict]:
    """
    Reason codes para un deudor.

    - `model`: ProbPagoModel (o pipeline sklearn con predict_proba).
    - `fila`: dict o pd.Series con las features del deudor.
    - `baseline`: salida de `baseline_cartera(df)`.
    - `top`: cuántos drivers devolver (los de mayor |contribución|).

    Devuelve lista de {feature, etiqueta, valor, delta_pp, direccion, texto}
    ordenada por impacto. `delta_pp` > 0 ⇒ sube la ProbPago.
    """
    fila = dict(fila)
    feats = [c for c in NUM_FEATURES + CAT_FEATURES if c in baseline]
    base_row = {c: fila.get(c, baseline[c]) for c in feats}
    X_full = pd.DataFrame([base_row])
    p_full = float(_predict_proba(model, X_full)[0])

    # Un batch: una fila por feature ocluida a su valor base
    filas = []
    for c in feats:
        r = dict(base_row)
        r[c] = baseline[c]
        filas.append(r)
    X_occ = pd.DataFrame(filas)
    p_occ = _predict_proba(model, X_occ)

    drivers = []
    for c, p in zip(feats, p_occ):
        delta = p_full - float(p)          # contribución de tener el valor real
        if abs(delta) < 1e-4:
            continue
        drivers.append({
            "feature": c,
            "etiqueta": ETIQUETAS.get(c, c),
            "valor": fila.get(c),
            "delta_pp": round(delta * 100, 1),
            "direccion": "sube" if delta > 0 else "baja",
            "texto": f"{ETIQUETAS.get(c, c)} "
                     f"({'+' if delta > 0 else ''}{round(delta * 100, 1)} pp)",
        })
    drivers.sort(key=lambda d: abs(d["delta_pp"]), reverse=True)
    return drivers[:top]


def explicar_texto(model, fila, baseline: dict, top: int = 2) -> str:
    """Reason codes en una línea, para el brief/screen-pop del gestor."""
    ds = explicar(model, fila, baseline, top=top)
    if not ds:
        return "Sin drivers destacados (perfil promedio de la cartera)."
    sube = [d["texto"] for d in ds if d["direccion"] == "sube"]
    baja = [d["texto"] for d in ds if d["direccion"] == "baja"]
    partes = []
    if sube:
        partes.append("A favor: " + ", ".join(sube))
    if baja:
        partes.append("En contra: " + ", ".join(baja))
    return " · ".join(partes)


def explicar_cartera(model, df: pd.DataFrame, baseline: dict | None = None,
                     top: int = 2) -> pd.Series:
    """
    Reason code (texto) por deudor para toda la cartera, vectorizado.
    Devuelve una Series alineada al índice de `df`.
    """
    baseline = baseline or baseline_cartera(df)
    feats = [c for c in NUM_FEATURES + CAT_FEATURES if c in baseline]
    base = df[feats].copy()
    p_full = _predict_proba(model, base)

    # Δ por feature: matriz (n_filas × n_feats) de contribuciones
    deltas = np.zeros((len(df), len(feats)))
    for j, c in enumerate(feats):
        occ = base.copy()
        occ[c] = baseline[c]
        deltas[:, j] = p_full - _predict_proba(model, occ)

    etiquetas = [ETIQUETAS.get(c, c) for c in feats]
    textos = []
    for i in range(len(df)):
        fila_d = deltas[i]
        idx = np.argsort(-np.abs(fila_d))[:top]
        piezas = []
        for j in idx:
            if abs(fila_d[j]) < 1e-4:
                continue
            pp = round(fila_d[j] * 100, 1)
            piezas.append(f"{etiquetas[j]} ({'+' if pp > 0 else ''}{pp} pp)")
        textos.append(" · ".join(piezas) if piezas else "perfil promedio")
    return pd.Series(textos, index=df.index, name="motivo_probpago")
