"""
Kobra · Briefing pre-llamada y registro post-llamada
====================================================
Cierra el ciclo de la negociación con la central telefónica:

  1. `brief(id_deudor)` — ANTES de llamar: devuelve el briefing del deudor
     (ProbPago, estrategia, descuento, plan, canal, guion, prioridad) listo
     para el screen-pop del CTI (Avaya Workspaces, etc.).

  2. `registrar_gestion(...)` — DESPUÉS de colgar: persiste el resumen de la
     negociación real (calidad, sentimiento, emoción, técnicas, resultado,
     recupero) en `data/kobra_gestiones.csv`, la misma base que alimenta la
     pestaña "Gestores & Evolución" del dashboard. Así el dashboard pasa de
     datos de demo a llamadas reales sin ningún cambio.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORED_CSV = os.path.join(ROOT, "outputs", "kobra_scored.csv")
GESTIONES_CSV = os.path.join(ROOT, "data", "kobra_gestiones.csv")

GESTION_COLS = [
    "id_gestion", "gestor_id", "gestor", "mes", "id_deudor", "segmento",
    "producto", "departamento", "tramo_mora", "canal", "usa_kobra",
    "calidad_gestion", "sentimiento_cliente", "emocion_dominante",
    "tecnicas_usadas", "resultado", "monto_gestionado", "recupero",
]

_scored_cache: pd.DataFrame | None = None


def _scored(refrescar=False) -> pd.DataFrame | None:
    """Cartera scoreada por el pipeline (outputs/kobra_scored.csv)."""
    global _scored_cache
    if _scored_cache is None or refrescar:
        if not os.path.exists(SCORED_CSV):
            return None
        _scored_cache = pd.read_csv(SCORED_CSV)
    return _scored_cache


# ---------------------------------------------------------------------------
# 1) Briefing pre-llamada
# ---------------------------------------------------------------------------
BRIEF_CAMPOS = [
    "id_deudor", "segmento", "producto", "departamento", "tramo_mora",
    "dias_mora", "monto_deuda", "probpago", "segmento_propension",
    "estrategia", "descuento_recomendado", "plan_cuotas", "canal_recomendado",
    "valor_esperado_recupero", "prioridad", "guion",
]


def brief(id_deudor: str) -> dict | None:
    """Briefing del deudor para el gestor antes de marcar. None si no existe."""
    df = _scored()
    if df is None:
        return None
    fila = df[df["id_deudor"] == id_deudor]
    if fila.empty:
        return None
    r = fila.iloc[0]
    out = {c: r[c] for c in BRIEF_CAMPOS if c in fila.columns}
    # tipos nativos para JSON
    for k, v in out.items():
        if hasattr(v, "item"):
            out[k] = v.item()
    out["resumen"] = (
        f"ProbPago {out['probpago']:.0%} ({out['segmento_propension']}) · "
        f"{out['estrategia']} · descuento máx. {out['descuento_recomendado']:.0%} · "
        f"{int(out['plan_cuotas'])} cuota(s) · canal {out['canal_recomendado']} · "
        f"prioridad #{int(out['prioridad'])}")
    return out


# ---------------------------------------------------------------------------
# 2) Registro post-llamada
# ---------------------------------------------------------------------------
def _inferir_resultado(clima: float | None, tecnicas: list | None,
                       emociones: list | None = None) -> str:
    """Heurística si el CRM no envía la tipificación real."""
    cierre = "Cierre" in (tecnicas or [])
    intencion = "intencion_pago" in (emociones or [])
    if clima is None:
        return "Sin acuerdo"
    if intencion and clima > 0:            # el cliente expresó que va a pagar
        return "Promesa"
    if cierre and clima > 0.15:            # hubo cierre y clima favorable
        return "Promesa"
    if clima > 0.35:
        return "Promesa"
    return "Sin acuerdo"


def registrar_gestion(id_deudor: str, gestor_id: str = "G01",
                      canal: str = "Llamada", calidad: float | None = None,
                      clima: float | None = None, emociones: list | None = None,
                      tecnicas: list | None = None, resultado: str | None = None,
                      recupero: float | None = None, mes: str | None = None,
                      archivo: str = GESTIONES_CSV) -> dict:
    """
    Persiste una gestión real. `resultado` idealmente viene de la tipificación
    del CRM ("Pago" / "Promesa" / "Sin acuerdo" / "No contacto"); si falta se
    infiere del clima + técnica de cierre.
    """
    df = _scored()
    d = None
    if df is not None:
        fila = df[df["id_deudor"] == id_deudor]
        d = fila.iloc[0] if not fila.empty else None

    monto = float(d["monto_deuda"]) if d is not None else 0.0
    prob = float(d["probpago"]) if d is not None else 0.5
    resultado = resultado or _inferir_resultado(clima, tecnicas, emociones)
    if recupero is None:
        if resultado == "Pago":
            recupero = monto * (0.6 + 0.4 * prob)
        elif resultado == "Promesa":
            recupero = monto * (0.3 + 0.3 * prob)
        else:
            recupero = 0.0

    existentes = 0
    if os.path.exists(archivo):
        with open(archivo, encoding="utf-8") as f:
            existentes = max(sum(1 for _ in f) - 1, 0)

    fila_out = dict(
        id_gestion=f"GR-{existentes + 1:07d}",
        gestor_id=gestor_id,
        gestor=f"Gestor {gestor_id.lstrip('G') or gestor_id}",
        mes=mes or datetime.now().strftime("%Y-%m"),
        id_deudor=id_deudor,
        segmento=(d["segmento"] if d is not None else "Desconocido"),
        producto=(d["producto"] if d is not None else "Desconocido"),
        departamento=(d["departamento"] if d is not None else "Desconocido"),
        tramo_mora=(d["tramo_mora"] if d is not None else "1-30"),
        canal=canal,
        usa_kobra=True,
        calidad_gestion=round(float(calidad), 1) if calidad is not None else None,
        sentimiento_cliente=round(float(clima), 3) if clima is not None else None,
        emocion_dominante=(emociones[0] if emociones else "neutro"),
        tecnicas_usadas=len(tecnicas or []),
        resultado=resultado,
        monto_gestionado=round(monto, 0),
        recupero=round(float(recupero), 0),
    )

    nueva = pd.DataFrame([fila_out], columns=GESTION_COLS)
    os.makedirs(os.path.dirname(archivo), exist_ok=True)
    nueva.to_csv(archivo, mode="a", index=False,
                 header=not os.path.exists(archivo))
    return fila_out
