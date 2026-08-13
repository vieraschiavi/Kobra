# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Agente IA Negociador
============================
Motor de decisión que, combinando ProbPago + tramo de mora + monto + canal,
recomienda para cada deudor:

    - estrategia            : la jugada de cobranza óptima
    - descuento_recomendado : % de quita sugerida
    - plan_cuotas           : nº de cuotas propuesto
    - canal_recomendado     : mejor canal de contacto
    - prioridad             : ranking operativo (1 = máxima)
    - valor_esperado_recupero (UYU) = probpago * monto * (1 - descuento)
    - guion                 : mensaje de negociación listo para enviar

El guion es un template parametrizado (sin nombres reales) que cualquier
gestor puede usar tal cual. Diseñado para maximizar recupero minimizando
la quita, priorizando por valor esperado.
"""
import pandas as pd


def _estrategia(prob, dias_mora, monto):
    """Decide la jugada según propensión y severidad de la mora."""
    if prob >= 0.65:
        if dias_mora <= 30:
            return "Recordatorio suave", 0.00, 1
        return "Pago total facilitado", 0.05, 1
    if prob >= 0.35:
        if dias_mora <= 90:
            return "Plan de cuotas", 0.10, 3
        return "Plan de cuotas + quita moderada", 0.20, 6
    # Baja propensión
    if dias_mora <= 90:
        return "Quita agresiva por pago único", 0.30, 1
    if monto >= 500_000:
        return "Derivación a gestión especializada", 0.15, 12
    return "Descuento máximo / cierre de cuenta", 0.45, 1


def _canal(row):
    """Ajusta canal: alto valor -> contacto humano; resto -> canal preferido."""
    if row["monto_deuda"] >= 500_000 or row["segmento"] == "Corporativo":
        return "Llamada"
    return row["canal_preferido"]


def _guion(row):
    est = row["estrategia"]
    desc = row["descuento_recomendado"]
    cuotas = int(row["plan_cuotas"])
    monto = row["monto_deuda"]
    monto_final = monto * (1 - desc)
    cuota_val = monto_final / max(cuotas, 1)
    ref = row["id_deudor"]

    saludo = "Hola, le escribimos de su gestor de cobranzas."
    if est == "Recordatorio suave":
        cuerpo = (f"Notamos un saldo pendiente de $U {monto:,.0f} (ref. {ref}). "
                  "Regularizando hoy evita costos adicionales. ¿Le enviamos el link de pago?")
    elif est == "Pago total facilitado":
        cuerpo = (f"Tiene un saldo de $U {monto:,.0f}. Por pago de contado hoy le "
                  f"aplicamos un beneficio del {desc:.0%}, quedando en $U {monto_final:,.0f}. "
                  "¿Coordinamos el pago?")
    elif est.startswith("Plan de cuotas"):
        cuerpo = (f"Le ofrecemos regularizar su saldo de $U {monto:,.0f} en {cuotas} "
                  f"cuotas de $U {cuota_val:,.0f}" +
                  (f" con {desc:.0%} de descuento" if desc > 0 else "") +
                  ". ¿Le queda cómodo comenzar este mes?")
    elif est.startswith("Quita agresiva") or est.startswith("Descuento"):
        cuerpo = (f"Tenemos una oferta especial de cierre: pagando hoy $U {monto_final:,.0f} "
                  f"({desc:.0%} de descuento sobre $U {monto:,.0f}) cancela toda su deuda. "
                  "Es por tiempo limitado.")
    else:  # derivación
        cuerpo = (f"Su caso (ref. {ref}, saldo $U {monto:,.0f}) fue asignado a un gestor "
                  f"especializado que puede estructurar un plan de hasta {cuotas} cuotas. "
                  "Le contactaremos para encontrar la mejor solución.")
    return f"{saludo} {cuerpo}"


def recomendar(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica el motor de negociación sobre una cartera ya scoreada (probpago)."""
    out = df.copy()
    est = out.apply(
        lambda r: _estrategia(r["probpago"], r["dias_mora"], r["monto_deuda"]),
        axis=1, result_type="expand")
    out["estrategia"] = est[0]
    out["descuento_recomendado"] = est[1]
    out["plan_cuotas"] = est[2]
    out["canal_recomendado"] = out.apply(_canal, axis=1)

    out["valor_esperado_recupero"] = (
        out["probpago"] * out["monto_deuda"] * (1 - out["descuento_recomendado"]))
    # Prioridad operativa: máximo valor esperado primero
    out["prioridad"] = (
        out["valor_esperado_recupero"].rank(ascending=False, method="first").astype(int))
    out["guion"] = out.apply(_guion, axis=1)
    return out


def resumen_estrategias(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("estrategia").agg(
        deudores=("id_deudor", "count"),
        cartera_uyu=("monto_deuda", "sum"),
        recupero_esperado_uyu=("valor_esperado_recupero", "sum"),
        probpago_prom=("probpago", "mean"),
        descuento_prom=("descuento_recomendado", "mean"),
    ).reset_index().sort_values("recupero_esperado_uyu", ascending=False)
    return g
