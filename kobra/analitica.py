"""
MV Kobra AI · Analítica de gestión (por gestor y por mes)
===================================================
Sobre el historial de gestiones responde:

  1. ¿Qué características suceden más por tramo de mora / segmento / canal?
     (emociones del cliente, resultados, calidad, recupero)
  2. ¿Cómo evolucionan en el tiempo? (calidad, sentimiento, conversión, recupero)
  3. ¿Cuál es el impacto en cobranza? (calidad de gestión ↔ recupero)
  4. ¿Mejoran los gestores con el tiempo usando las herramientas de MV Kobra AI?
"""
import numpy as np
import pandas as pd

CONVERSION = ("Pago", "Promesa", "Arreglo de pago", "Promesa de pago")


def _tasa_conversion(s):
    return s.isin(CONVERSION).mean()


# 1) Características más frecuentes por dimensión ----------------------------
def caracteristicas_por(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Resumen por valor de `dim` (tramo_mora / segmento / canal / producto)."""
    g = df.groupby(dim, observed=True)
    out = g.agg(
        gestiones=("id_gestion", "count"),
        calidad_prom=("calidad_gestion", "mean"),
        sentimiento_prom=("sentimiento_cliente", "mean"),
        tecnicas_prom=("tecnicas_usadas", "mean"),
        recupero=("recupero", "sum"),
        monto=("monto_gestionado", "sum"),
    )
    out["tasa_conversion"] = g["resultado"].apply(_tasa_conversion)
    out["tasa_recupero"] = out["recupero"] / out["monto"]
    # Emoción dominante más frecuente por dimensión
    emo = (df.groupby([dim, "emocion_dominante"], observed=True).size()
           .reset_index(name="n"))
    top_emo = (emo.sort_values("n", ascending=False)
               .groupby(dim, observed=True).first()["emocion_dominante"])
    out["emocion_top"] = top_emo
    return out.reset_index().round(3)


def matriz_emociones(df: pd.DataFrame, dim: str = "tramo_mora") -> pd.DataFrame:
    """Distribución (%) de emociones del cliente por valor de `dim`."""
    m = (pd.crosstab(df[dim], df["emocion_dominante"], normalize="index") * 100).round(1)
    return m.reset_index()


# 2) Evolución temporal ------------------------------------------------------
def evolucion_mensual(df: pd.DataFrame, por: str = None) -> pd.DataFrame:
    keys = ["mes"] + ([por] if por else [])
    g = df.groupby(keys, observed=True)
    out = g.agg(
        gestiones=("id_gestion", "count"),
        calidad_prom=("calidad_gestion", "mean"),
        sentimiento_prom=("sentimiento_cliente", "mean"),
        recupero=("recupero", "sum"),
        monto=("monto_gestionado", "sum"),
    )
    out["tasa_conversion"] = g["resultado"].apply(_tasa_conversion)
    out["tasa_recupero"] = out["recupero"] / out["monto"]
    return out.reset_index().round(3)


# 3) Impacto en cobranza (calidad ↔ recupero) --------------------------------
def impacto_calidad(df: pd.DataFrame, bins=(0, 50, 60, 70, 80, 100)) -> pd.DataFrame:
    labels = [f"{bins[i]}-{bins[i+1]}" for i in range(len(bins) - 1)]
    d = df.copy()
    d["rango_calidad"] = pd.cut(d["calidad_gestion"], bins=list(bins), labels=labels)
    g = d.groupby("rango_calidad", observed=True)
    out = g.agg(gestiones=("id_gestion", "count"),
                recupero=("recupero", "sum"),
                monto=("monto_gestionado", "sum"))
    out["tasa_conversion"] = g["resultado"].apply(_tasa_conversion)
    out["tasa_recupero"] = out["recupero"] / out["monto"]
    corr = float(df["calidad_gestion"].corr(
        df["resultado"].isin(CONVERSION).astype(int)))
    out.attrs["correlacion_calidad_conversion"] = round(corr, 3)
    return out.reset_index().round(3)


# 4) Ranking y mejora por gestor --------------------------------------------
def ranking_gestores(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["gestor_id", "gestor"], observed=True)
    out = g.agg(
        gestiones=("id_gestion", "count"),
        calidad_prom=("calidad_gestion", "mean"),
        recupero=("recupero", "sum"),
        monto=("monto_gestionado", "sum"),
        usa_kobra=("usa_kobra", "max"),
    )
    out["tasa_conversion"] = g["resultado"].apply(_tasa_conversion)
    out["tasa_recupero"] = out["recupero"] / out["monto"]
    return out.reset_index().sort_values("recupero", ascending=False).round(3)


def mejora_por_gestor(df: pd.DataFrame) -> pd.DataFrame:
    """Compara primeros 3 meses vs últimos 3 meses de cada gestor."""
    orden = sorted(df["mes"].unique())
    prim, ult = set(orden[:3]), set(orden[-3:])
    filas = []
    for (gid, gestor), sub in df.groupby(["gestor_id", "gestor"], observed=True):
        a = sub[sub["mes"].isin(prim)]
        b = sub[sub["mes"].isin(ult)]
        if a.empty or b.empty:
            continue
        filas.append(dict(
            gestor_id=gid, gestor=gestor,
            usa_kobra=bool(sub["usa_kobra"].max()),
            calidad_inicial=round(a["calidad_gestion"].mean(), 1),
            calidad_final=round(b["calidad_gestion"].mean(), 1),
            delta_calidad=round(b["calidad_gestion"].mean() - a["calidad_gestion"].mean(), 1),
            conversion_inicial=round(_tasa_conversion(a["resultado"]), 3),
            conversion_final=round(_tasa_conversion(b["resultado"]), 3),
            delta_conversion=round(_tasa_conversion(b["resultado"]) - _tasa_conversion(a["resultado"]), 3),
        ))
    return pd.DataFrame(filas).sort_values("delta_calidad", ascending=False)


def comparativa_ia(df: pd.DataFrame) -> dict | None:
    """Gestor IA vs. gestores humanos, sobre los meses en que conviven."""
    es_ia = df["gestor_id"].astype(str).str.startswith("IA")
    if not es_ia.any():
        return None
    meses_ia = sorted(df.loc[es_ia, "mes"].unique())
    d = df[df["mes"].isin(meses_ia)]
    es_ia = d["gestor_id"].astype(str).str.startswith("IA")

    def resumen(sub, gestores):
        meses = sub["mes"].nunique() or 1
        return dict(
            gestiones=int(len(sub)),
            gestiones_por_gestor_mes=round(len(sub) / max(gestores, 1) / meses, 1),
            calidad_prom=round(float(sub["calidad_gestion"].mean()), 1),
            tasa_conversion=round(float(_tasa_conversion(sub["resultado"])), 3),
            tasa_recupero=round(float(sub["recupero"].sum()
                                      / max(sub["monto_gestionado"].sum(), 1)), 3),
            sentimiento_prom=round(float(sub["sentimiento_cliente"].mean()), 3),
            recupero_total=float(sub["recupero"].sum()),
        )

    ia = resumen(d[es_ia], d.loc[es_ia, "gestor_id"].nunique())
    hum = resumen(d[~es_ia], d.loc[~es_ia, "gestor_id"].nunique())
    return {"ia": ia, "humanos": hum, "meses": meses_ia,
            "volumen_x": round(ia["gestiones_por_gestor_mes"]
                               / max(hum["gestiones_por_gestor_mes"], 0.1), 1)}


def impacto_kobra(df: pd.DataFrame) -> dict:
    """Compara gestiones con vs. sin MV Kobra AI."""
    def resumen(sub):
        return dict(
            gestiones=int(len(sub)),
            calidad_prom=round(float(sub["calidad_gestion"].mean()), 1),
            tasa_conversion=round(float(_tasa_conversion(sub["resultado"])), 3),
            tasa_recupero=round(float(sub["recupero"].sum() / max(sub["monto_gestionado"].sum(), 1)), 3),
            sentimiento_prom=round(float(sub["sentimiento_cliente"].mean()), 3),
        )
    con = resumen(df[df["usa_kobra"]])
    sin = resumen(df[~df["usa_kobra"]])
    return {"con_kobra": con, "sin_kobra": sin,
            "uplift_conversion": round(con["tasa_conversion"] - sin["tasa_conversion"], 3),
            "uplift_calidad": round(con["calidad_prom"] - sin["calidad_prom"], 1),
            "uplift_recupero": round(con["tasa_recupero"] - sin["tasa_recupero"], 3)}
