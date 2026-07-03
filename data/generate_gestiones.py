"""
Kobra · Generador de gestiones (interacciones de cobranza)
==========================================================
Genera el historial de GESTIONES (llamadas / WhatsApp) por gestor y por mes,
vinculado a la cartera. Cada gestión trae la calidad de la gestión, el
sentimiento del cliente, la emoción dominante, las técnicas usadas, el
resultado y el recupero.

Incluye un efecto de **adopción de Kobra** INYECTADO POR DISEÑO: los gestores
que "adoptan" mejoran su calidad mes a mes según una curva codificada abajo
(variable `efecto`). En consecuencia, cualquier "uplift con vs. sin Kobra"
calculado sobre estos datos es CIRCULAR: sirve para demostrar la METODOLOGÍA
de medición (grupo de control, cohortes, evolución temporal), nunca como
evidencia de impacto real. Datos 100% sintéticos, sin nombres reales.

Uso:
    python data/generate_gestiones.py --seed 42
"""
import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARTERA_CSV = os.path.join(ROOT, "data", "kobra_cartera.csv")

MESES = ["2025-08", "2025-09", "2025-10", "2025-11", "2025-12",
         "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

# Emoción dominante típica por tramo de mora (probabilidades)
EMO_POR_TRAMO = {
    "1-30":   {"intencion_pago": .40, "neutro": .30, "ansiedad": .12, "objecion": .10, "frustracion": .05, "enojo": .03},
    "31-60":  {"intencion_pago": .28, "neutro": .27, "objecion": .18, "ansiedad": .13, "frustracion": .10, "enojo": .04},
    "61-90":  {"objecion": .25, "ansiedad": .20, "neutro": .18, "dificultad_economica": .15, "frustracion": .14, "enojo": .08},
    "91-180": {"dificultad_economica": .28, "frustracion": .22, "objecion": .18, "enojo": .14, "ansiedad": .12, "neutro": .06},
    "180+":   {"enojo": .30, "frustracion": .28, "dificultad_economica": .22, "objecion": .12, "neutro": .05, "ansiedad": .03},
}
RESULTADOS = ["Pago", "Promesa", "Sin acuerdo", "No contacto"]


def _pick(rng, dist):
    keys = list(dist.keys())
    p = np.array([dist[k] for k in keys], float); p = p / p.sum()
    return rng.choice(keys, p=p)


def _prob_proxy(row):
    """Propensión de pago aproximada (sin correr el modelo)."""
    z = (0.4 - 1.1 * (row["dias_mora"] / 100)
         + 1.5 * (row["score_buro"] - 560) / 130
         + 1.0 * row["contactabilidad"])
    return 1 / (1 + np.exp(-z))


def generar(seed=42, gestiones_por_gestor_mes=42):
    rng = np.random.default_rng(seed)
    cartera = pd.read_csv(CARTERA_CSV)

    n_gestores = 12
    gestores = [f"G{str(i+1).zfill(2)}" for i in range(n_gestores)]
    # Habilidad base por gestor
    skill = {g: float(np.clip(rng.normal(62, 9), 42, 82)) for g in gestores}
    # Mes de adopción de Kobra (índice en MESES). 2 gestores nunca adoptan (control).
    adopcion = {}
    for i, g in enumerate(gestores):
        if i < 2:
            adopcion[g] = None                      # grupo control (no usa Kobra)
        else:
            adopcion[g] = int(rng.integers(1, 6))   # adopta entre mes 1 y 5

    # Plan de gestión: humanos + Gestor IA. El Gestor IA (INYECTADO POR DISEÑO,
    # igual de ilustrativo que el resto) se incorpora en 2026-02 con calidad
    # alta y estable y ~4x el volumen humano (no duerme, 50 líneas en paralelo).
    plan = []
    for mi, mes in enumerate(MESES):
        for g in gestores:
            usa_kobra = adopcion[g] is not None and mi >= adopcion[g]
            meses_con_kobra = (mi - adopcion[g]) if usa_kobra else 0
            # Efecto Kobra: mejora progresiva de la calidad (curva con techo)
            efecto = 14 * (1 - np.exp(-meses_con_kobra / 3)) if usa_kobra else 0
            n = gestiones_por_gestor_mes + int(rng.integers(-6, 7))
            plan.append((g, f"Gestor {g[1:]}", mes, usa_kobra,
                         skill[g] + efecto, 8.0, n))
        if mi >= 6:
            for gia in ("IA01", "IA02"):
                plan.append((gia, f"Gestor {gia}", mes, True, 84.0, 4.0,
                             gestiones_por_gestor_mes * 4))

    rows = []
    gid = 0
    for gestor_id, gestor_nombre, mes, usa_kobra, calidad_media, calidad_sd, n in plan:
            muestra = cartera.sample(n=n, replace=True, random_state=int(rng.integers(1e9)))
            for _, d in muestra.iterrows():
                gid += 1
                prob = _prob_proxy(d)
                canal = rng.choice(["Llamada", "WhatsApp"], p=[0.55, 0.45])

                calidad = np.clip(rng.normal(calidad_media, calidad_sd), 20, 100)
                emo = _pick(rng, EMO_POR_TRAMO.get(d["tramo_mora"], EMO_POR_TRAMO["61-90"]))

                # Sentimiento del cliente: peor en emociones negativas
                base_sent = {"enojo": -0.6, "frustracion": -0.4, "dificultad_economica": -0.3,
                             "ansiedad": -0.2, "objecion": -0.1, "neutro": 0.05,
                             "intencion_pago": 0.5}[emo]
                sentimiento = float(np.clip(base_sent + (calidad - 60) / 200
                                            + rng.normal(0, 0.12), -1, 1))
                tecnicas = int(np.clip(round((calidad / 100) * 5 + rng.normal(0, 1)), 0, 8))

                # Conversión: depende (fuerte) de la calidad de gestión, la
                # propensión y la emoción del cliente
                logit = (-2.7 + 1.8 * prob + 3.8 * (calidad / 100)
                         + (0.6 if emo == "intencion_pago" else 0)
                         - (0.6 if emo in ("enojo", "frustracion") else 0))
                p_conv = 1 / (1 + np.exp(-logit))
                r = rng.random()
                if r < p_conv * 0.45:
                    resultado = "Pago"
                elif r < p_conv:
                    resultado = "Promesa"
                elif r < p_conv + 0.20:
                    resultado = "Sin acuerdo"
                else:
                    resultado = "No contacto"

                monto = float(d["monto_deuda"])
                if resultado == "Pago":
                    recupero = monto * (0.6 + 0.4 * prob)
                elif resultado == "Promesa":
                    recupero = monto * (0.3 + 0.3 * prob)
                else:
                    recupero = 0.0

                rows.append(dict(
                    id_gestion=f"GE-{gid:07d}",
                    gestor_id=gestor_id,
                    gestor=gestor_nombre,
                    mes=mes,
                    id_deudor=d["id_deudor"],
                    segmento=d["segmento"],
                    producto=d["producto"],
                    departamento=d["departamento"],
                    tramo_mora=d["tramo_mora"],
                    canal=canal,
                    usa_kobra=usa_kobra,
                    calidad_gestion=round(float(calidad), 1),
                    sentimiento_cliente=round(sentimiento, 3),
                    emocion_dominante=emo,
                    tecnicas_usadas=tecnicas,
                    resultado=resultado,
                    monto_gestionado=round(monto, 0),
                    recupero=round(recupero, 0),
                ))

    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "kobra_gestiones.csv"))
    args = ap.parse_args()
    if not os.path.exists(CARTERA_CSV):
        from generate_dataset import generar as gen_cartera
        gen_cartera(12000, 42).to_csv(CARTERA_CSV, index=False)
    df = generar(args.seed)
    df.to_csv(args.out, index=False)
    print(f"[OK] Gestiones generadas: {args.out}  ({len(df):,} filas)")
    print(f"     Gestores: {df['gestor'].nunique()} · Meses: {df['mes'].nunique()}")
    print(f"     Tasa de pago: {(df['resultado']=='Pago').mean():.1%} · "
          f"Recupero total: $U {df['recupero'].sum():,.0f}")
    print(f"     Calidad prom (con Kobra): {df[df.usa_kobra]['calidad_gestion'].mean():.1f} · "
          f"(sin Kobra): {df[~df.usa_kobra]['calidad_gestion'].mean():.1f}")
