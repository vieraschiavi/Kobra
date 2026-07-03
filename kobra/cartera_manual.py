"""
Kobra IA · Cartera manual (modo "mi cartera de prueba")
=======================================================
Convierte una lista simple de contactos —nombre, teléfono, monto de deuda— en
una cartera completa que el pipeline puede scorear y negociar, para que puedas
**probar Kobra con tus propios casos** sin cargar todo el detalle de un ERP.

Los campos que no aportás (días de mora, score de buró, etc.) se completan con
**supuestos por defecto** claramente marcados: en una implementación real esos
datos vienen del ERP/CRM del cliente. Podés sobreescribir cualquiera por
contacto (columna en el CSV o clave en el dict).

> ⚠️ Privacidad: si cargás nombres y teléfonos **reales**, ese archivo es tuyo
> y privado (`data/mi_cartera_prueba.csv` está en `.gitignore`). El producto
> que se vende sigue siendo 100 % sintético. No subas datos personales al repo.
"""
from __future__ import annotations

import pandas as pd

from kobra.probpago import CAT_FEATURES, NUM_FEATURES

# Supuestos por defecto para las features que no vienen cargadas.
# En producción se reemplazan por los valores reales del ERP.
DEFAULTS = {
    "segmento": "Retail",
    "producto": "Préstamo personal",
    "departamento": "Montevideo",
    "canal_preferido": "Llamada",
    "dias_mora": 60,
    "cuotas_atrasadas": 2,
    "antiguedad_cliente_meses": 24,
    "score_buro": 600,
    "ingreso_estimado": 45_000,
    "pagos_ultimos_12m": 6,
    "promesas_cumplidas": 1,
    "promesas_incumplidas": 1,
    "contactabilidad": 0.7,
    "gestiones_previas": 2,
}

_TRAMO_BINS = [-1, 30, 60, 90, 180, 10_000]
_TRAMO_LABELS = ["1-30", "31-60", "61-90", "91-180", "180+"]


def cargar_manual(contactos: list[dict], prefijo: str = "MP") -> pd.DataFrame:
    """
    `contactos`: lista de dicts con al menos `monto_deuda`; opcional `nombre`,
    `telefono`, `id_deudor` y cualquier feature de `DEFAULTS` para sobreescribir.
    Devuelve un DataFrame con el esquema del modelo + `nombre` y `telefono`.
    """
    rows = []
    for k, c in enumerate(contactos, 1):
        row = dict(DEFAULTS)
        for key, val in c.items():
            if val is not None:
                row[key] = val
        row["id_deudor"] = str(c.get("id_deudor") or f"{prefijo}-{k:03d}")
        row["monto_deuda"] = float(c["monto_deuda"])
        row["nombre"] = str(c.get("nombre", "")).strip()
        row["telefono"] = str(c.get("telefono", "")).strip()
        rows.append(row)

    df = pd.DataFrame(rows)
    df["tramo_mora"] = pd.cut(df["dias_mora"], bins=_TRAMO_BINS, labels=_TRAMO_LABELS)
    return df


def puntuar(model, df: pd.DataFrame) -> pd.DataFrame:
    """
    Scorea una cartera chica sin depender de deciles (qcut necesita muchas
    filas): calcula ProbPago con el modelo y la propensión por umbrales.
    """
    out = df.copy()
    pipe = getattr(model, "pipeline", model)
    out["probpago"] = pipe.predict_proba(out[NUM_FEATURES + CAT_FEATURES])[:, 1]
    out["segmento_propension"] = pd.cut(
        out["probpago"], bins=[-0.01, 0.35, 0.65, 1.01],
        labels=["Baja", "Media", "Alta"])
    return out


def brief_desde_fila(fila) -> dict:
    """Arma el brief que consume el Gestor IA a partir de una fila scoreada."""
    return {
        "id_deudor": fila["id_deudor"],
        "nombre": fila.get("nombre", ""),
        "telefono": fila.get("telefono", ""),
        "monto_deuda": float(fila["monto_deuda"]),
        "probpago": float(fila["probpago"]),
        "estrategia": fila["estrategia"],
        "descuento_recomendado": float(fila["descuento_recomendado"]),
        "plan_cuotas": int(fila["plan_cuotas"]),
        "segmento_propension": str(fila.get("segmento_propension", "Media")),
        "canal_recomendado": fila.get("canal_recomendado", "Llamada"),
    }


_NUMERICAS = ("monto_deuda", "dias_mora", "cuotas_atrasadas",
              "antiguedad_cliente_meses", "score_buro", "ingreso_estimado",
              "pagos_ultimos_12m", "promesas_cumplidas", "promesas_incumplidas",
              "contactabilidad", "gestiones_previas")


def desde_dataframe(df: pd.DataFrame) -> list[dict]:
    """Normaliza un DataFrame de contactos (tabla editable o archivo subido en
    el dashboard) a la lista de contactos. Teléfono como texto (conserva el 0
    inicial); columnas numéricas coercionadas; nombres/vacíos tolerados."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "monto_deuda" not in df.columns:
        for alt in ("deuda", "monto"):
            if alt in df.columns:
                df = df.rename(columns={alt: "monto_deuda"})
                break
    if "telefono" in df.columns:
        df["telefono"] = df["telefono"].apply(
            lambda v: "" if pd.isna(v) else str(v).strip())
    for col in _NUMERICAS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    contactos = []
    for row in df.to_dict("records"):
        # descartar filas sin deuda válida y columnas numéricas vacías
        if pd.isna(row.get("monto_deuda")):
            continue
        contactos.append({k: v for k, v in row.items()
                          if not (k in _NUMERICAS and pd.isna(v))})
    return contactos


def leer_csv(ruta: str) -> list[dict]:
    """Lee un CSV de contactos (columnas: nombre, telefono, monto_deuda/deuda, …)."""
    return desde_dataframe(pd.read_csv(ruta, dtype=str).fillna(""))
