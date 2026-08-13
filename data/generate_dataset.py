# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Generador de dataset de cobranzas (Uruguay)
====================================================
Genera una cartera de cobranzas SINTÉTICA pero estadísticamente realista,
localizada para Uruguay. No contiene nombres de clientes ni datos personales
reales -> apta para demo comercial sin problemas legales.

El esquema es genérico: sirve para cualquier empresa (banco, financiera,
retail, telco, utility, fintech). Para usar un dataset real basta con
respetar las mismas columnas.

Uso:
    python data/generate_dataset.py --n 12000 --seed 42
"""
import argparse

import numpy as np
import pandas as pd

# --- Catálogos localizados Uruguay -------------------------------------------
DEPARTAMENTOS = [
    ("Montevideo", 0.42), ("Canelones", 0.16), ("Maldonado", 0.07),
    ("Salto", 0.04), ("Colonia", 0.04), ("Paysandú", 0.03),
    ("San José", 0.04), ("Rivera", 0.03), ("Tacuarembó", 0.03),
    ("Cerro Largo", 0.02), ("Soriano", 0.02), ("Artigas", 0.02),
    ("Durazno", 0.02), ("Florida", 0.02), ("Lavalleja", 0.01),
    ("Rocha", 0.02), ("Río Negro", 0.01), ("Treinta y Tres", 0.01),
    ("Flores", 0.005), ("Trinidad", 0.005),
]
SEGMENTOS = [("Retail", 0.62), ("Pyme", 0.28), ("Corporativo", 0.10)]
PRODUCTOS = [
    ("Préstamo personal", 0.30), ("Tarjeta de crédito", 0.28),
    ("Crédito automotor", 0.10), ("Microcrédito", 0.12),
    ("Cuenta corriente", 0.08), ("Financiación retail", 0.12),
]
CANALES = ["WhatsApp", "Llamada", "Email", "SMS"]


def _pick(rng, catalog):
    vals = [c[0] for c in catalog]
    probs = np.array([c[1] for c in catalog], dtype=float)
    probs = probs / probs.sum()
    return rng.choice(vals, p=probs)


def generar(n=12000, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        segmento = _pick(rng, SEGMENTOS)
        producto = _pick(rng, PRODUCTOS)
        depto = _pick(rng, DEPARTAMENTOS)

        # Monto de deuda por segmento (UYU)
        if segmento == "Retail":
            monto = float(rng.lognormal(mean=10.2, sigma=0.7))
        elif segmento == "Pyme":
            monto = float(rng.lognormal(mean=11.6, sigma=0.8))
        else:  # Corporativo
            monto = float(rng.lognormal(mean=13.2, sigma=0.9))
        monto = round(min(monto, 8_000_000), -1)

        # Días de mora (sesgado a tramos tempranos)
        dias_mora = int(min(rng.exponential(scale=70) + rng.integers(0, 15), 720))

        antiguedad = int(rng.integers(1, 180))            # meses como cliente
        score_buro = int(np.clip(rng.normal(560, 130), 250, 950))
        ingreso_estimado = round(float(rng.lognormal(mean=10.7, sigma=0.55)), -2)

        pagos_12m = int(np.clip(rng.poisson(6) - dias_mora // 120, 0, 12))
        promesas_cumplidas = int(rng.integers(0, 6))
        promesas_incumplidas = int(rng.poisson(1 + dias_mora / 200))
        contactabilidad = float(np.clip(
            rng.normal(0.6 - dias_mora / 1500, 0.18), 0.02, 0.99))
        gestiones_previas = int(np.clip(rng.poisson(3 + dias_mora / 60), 0, 40))
        cuotas_atrasadas = int(np.clip(dias_mora // 30 + rng.integers(0, 2), 1, 24))
        canal_pref = rng.choice(CANALES, p=[0.45, 0.28, 0.15, 0.12])

        # ---- Propensión de pago "verdadera" (score latente) --------------
        z = (
            0.15
            - 1.15 * (dias_mora / 100)
            + 1.6 * (score_buro - 560) / 130
            + 0.7 * (pagos_12m / 12)
            + 1.1 * contactabilidad
            + 0.35 * promesas_cumplidas
            - 0.55 * promesas_incumplidas
            - 0.25 * (np.log1p(monto) - 11)
            + 0.15 * (antiguedad / 60)
            - 0.10 * (gestiones_previas / 10)
        )
        prob_real = 1 / (1 + np.exp(-z))
        pago = int(rng.random() < prob_real)

        rows.append(dict(
            id_deudor=f"KB-{100000 + i}",
            segmento=segmento,
            producto=producto,
            departamento=depto,
            monto_deuda=monto,
            dias_mora=dias_mora,
            cuotas_atrasadas=cuotas_atrasadas,
            antiguedad_cliente_meses=antiguedad,
            score_buro=score_buro,
            ingreso_estimado=ingreso_estimado,
            pagos_ultimos_12m=pagos_12m,
            promesas_cumplidas=promesas_cumplidas,
            promesas_incumplidas=promesas_incumplidas,
            contactabilidad=round(contactabilidad, 3),
            gestiones_previas=gestiones_previas,
            canal_preferido=canal_pref,
            pago=pago,
        ))

    df = pd.DataFrame(rows)

    # Tramo de mora (bucket comercial)
    bins = [-1, 30, 60, 90, 180, 10_000]
    labels = ["1-30", "31-60", "61-90", "91-180", "180+"]
    df["tramo_mora"] = pd.cut(df["dias_mora"], bins=bins, labels=labels)

    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/kobra_cartera.csv")
    args = ap.parse_args()

    df = generar(args.n, args.seed)
    df.to_csv(args.out, index=False)
    print(f"[OK] Dataset generado: {args.out}  ({len(df):,} deudores)")
    print(f"     Tasa de pago histórica: {df['pago'].mean():.1%}")
    print(f"     Cartera total (UYU): {df['monto_deuda'].sum():,.0f}")
