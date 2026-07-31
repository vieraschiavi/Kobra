"""
MV Kobra AI · Pipeline end-to-end
===========================
Orquesta todo el flujo:

    1. Carga (o genera) la cartera de cobranzas.
    2. Entrena / aplica ProbPago (probabilidad de pago).
    3. Corre el Agente IA Negociador (estrategia + guion por deudor).
    4. Exporta resultados a CSV, Excel y un bundle JSON para el dashboard.

Uso:
    python -m kobra.pipeline            # usa data/kobra_cartera.csv (o la genera)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kobra import (
    explicabilidad,  # noqa: E402
    negociador,  # noqa: E402
)
from kobra import rutas as krutas  # noqa: E402
from kobra.probpago import ProbPagoModel  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Escribible siempre (ver kobra/rutas.py): en dev/tests es el repo, igual
# que antes; instalado, es una carpeta propia del usuario, no Program Files.
DATA_CSV = os.path.join(krutas.DIR_DATOS, "data", "kobra_cartera.csv")
OUT_DIR = os.path.join(krutas.DIR_DATOS, "outputs")


def _load_or_generate():
    if not os.path.exists(DATA_CSV):
        from data.generate_dataset import generar
        df = generar(12000, 42)
        os.makedirs(os.path.dirname(DATA_CSV), exist_ok=True)
        df.to_csv(DATA_CSV, index=False)
        print(f"[pipeline] Dataset generado en {DATA_CSV}")
    return pd.read_csv(DATA_CSV)


def _to_native(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


def run():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = _load_or_generate()
    print(f"[pipeline] Cartera cargada: {len(df):,} deudores")

    # 1) Modelo ProbPago (usa el modelo seleccionado+calibrado por `kobra.train`
    #    si ya fue entrenado; si no, cae en un Gradient Boosting ad-hoc)
    model = ProbPagoModel().fit_seleccionado(df)
    print(f"[pipeline] ProbPago: {model.metrics['modelo']} · "
          f"AUC-ROC={model.metrics['auc_roc']} "
          f"· Lift decil10={model.metrics['lift_decil10']}x")
    scored = model.score(df)

    # 2) Agente Negociador
    full = negociador.recomendar(scored)
    print(f"[pipeline] Negociador aplicado sobre {len(full):,} casos")

    # 2b) Explicabilidad: reason codes por deudor (por qué esta ProbPago)
    full["motivo_probpago"] = explicabilidad.explicar_cartera(model, full)
    print("[pipeline] Explicabilidad: reason codes generados por deudor")

    # 3) Exports tabulares
    cols_export = [
        "id_deudor", "segmento", "producto", "departamento", "tramo_mora",
        "dias_mora", "monto_deuda", "score_buro", "contactabilidad",
        "probpago", "decil", "segmento_propension", "estrategia",
        "descuento_recomendado", "plan_cuotas", "canal_recomendado",
        "valor_esperado_recupero", "prioridad", "pago", "guion",
        "motivo_probpago",
    ]
    export = full[cols_export].copy()
    export.round(4).to_csv(os.path.join(OUT_DIR, "kobra_scored.csv"), index=False)

    with pd.ExcelWriter(os.path.join(OUT_DIR, "kobra_scored.xlsx"),
                        engine="xlsxwriter") as xl:
        export.to_excel(xl, sheet_name="Cartera_scoreada", index=False)
        negociador.resumen_estrategias(full).to_excel(
            xl, sheet_name="Resumen_estrategias", index=False)
        model.feature_importance().to_excel(
            xl, sheet_name="Drivers_modelo", index=False)

    # 4) Bundle JSON para el dashboard estático
    bundle = {
        "metrics": {k: _to_native(v) for k, v in model.metrics.items()},
        "feature_importance": model.feature_importance().head(12).to_dict("records"),
        "kpis": _kpis(full),
        "registros": json.loads(
            export.round(3).to_json(orient="records", force_ascii=False)),
    }
    with open(os.path.join(OUT_DIR, "kobra_bundle.json"), "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False)

    with open(os.path.join(OUT_DIR, "model_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(bundle["metrics"], f, ensure_ascii=False, indent=2)

    # 5) Data file JS para el dashboard estático (funciona con file://)
    dash_dir = os.path.join(ROOT, "dashboard_estatico")
    os.makedirs(dash_dir, exist_ok=True)
    with open(os.path.join(dash_dir, "kobra_data.js"), "w", encoding="utf-8") as f:
        f.write("window.KOBRA = ")
        json.dump(bundle, f, ensure_ascii=False)
        f.write(";")

    # 6) Historial de gestiones + analítica por gestor/mes
    _analitica_gestiones()

    print(f"[pipeline] Exports listos en {OUT_DIR}/")
    print("           - kobra_scored.csv / .xlsx")
    print("           - kobra_bundle.json (dashboard)")
    _print_kpis(bundle["kpis"])
    return full, model


def _analitica_gestiones():
    """Genera (si falta) el historial de gestiones y exporta la analítica."""
    from kobra import analitica
    gest_csv = os.path.join(ROOT, "data", "kobra_gestiones.csv")
    if not os.path.exists(gest_csv):
        from data.generate_gestiones import generar as gen_g
        gen_g(42).to_csv(gest_csv, index=False)
    g = pd.read_csv(gest_csv)
    with pd.ExcelWriter(os.path.join(OUT_DIR, "kobra_analitica_gestion.xlsx"),
                        engine="xlsxwriter") as xl:
        analitica.ranking_gestores(g).to_excel(xl, sheet_name="Ranking_gestores", index=False)
        analitica.mejora_por_gestor(g).to_excel(xl, sheet_name="Mejora_gestores", index=False)
        analitica.evolucion_mensual(g).to_excel(xl, sheet_name="Evolucion_mensual", index=False)
        analitica.caracteristicas_por(g, "tramo_mora").to_excel(xl, sheet_name="Por_tramo", index=False)
        analitica.caracteristicas_por(g, "segmento").to_excel(xl, sheet_name="Por_segmento", index=False)
    ik = analitica.impacto_kobra(g)
    ik_out = {"NOTA": ("ILUSTRATIVO: datos sintéticos con efecto de adopción "
                       "inyectado por el generador (data/generate_gestiones.py). "
                       "Demuestra la metodología de medición, NO es impacto medido."),
              **ik}
    with open(os.path.join(OUT_DIR, "impacto_kobra.json"), "w", encoding="utf-8") as f:
        json.dump(ik_out, f, ensure_ascii=False, indent=2)
    print(f"[pipeline] Analítica de gestión (datos sintéticos ilustrativos) · "
          f"uplift conversión: +{ik['uplift_conversion']*100:.1f}pp · "
          f"calidad: +{ik['uplift_calidad']:.1f} — efecto inyectado por el "
          f"generador para demostrar la metodología, no un resultado medido")


def _kpis(df):
    cartera = float(df["monto_deuda"].sum())
    recupero = float(df["valor_esperado_recupero"].sum())
    return {
        "deudores": int(len(df)),
        "cartera_total_uyu": cartera,
        "recupero_esperado_uyu": recupero,
        "tasa_recupero_esperada": round(recupero / cartera, 4),
        "probpago_promedio": round(float(df["probpago"].mean()), 4),
        "mora_promedio_dias": round(float(df["dias_mora"].mean()), 1),
        "prioridad_alta": int((df["segmento_propension"] == "Alta").sum()),
        "en_riesgo_uyu": float(
            df.loc[df["segmento_propension"] == "Baja", "monto_deuda"].sum()),
    }


def _print_kpis(k):
    print("\n=== KPIs de cartera ===")
    print(f"  Deudores:              {k['deudores']:,}")
    print(f"  Cartera total:         $U {k['cartera_total_uyu']:,.0f}")
    print(f"  Recupero esperado:     $U {k['recupero_esperado_uyu']:,.0f} "
          f"({k['tasa_recupero_esperada']:.1%})")
    print(f"  ProbPago promedio:     {k['probpago_promedio']:.1%}")
    print(f"  Cartera en riesgo:     $U {k['en_riesgo_uyu']:,.0f}")


if __name__ == "__main__":
    run()
