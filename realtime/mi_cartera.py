"""
MV Kobra AI · "Mi cartera de prueba" (modo cliente, no premium)
============================================================
Corré el flujo COMPLETO de MV Kobra AI sobre TUS propios contactos —nombre,
teléfono, monto— para probarlo de punta a punta sin la cartera sintética:

    ProbPago (por qué)  →  estrategia + descuento + guion  →  chequeo de
    cumplimiento (¿puedo llamar ahora?)  →  Gestor IA negociando  →  resultado

La conversación se **simula** (el deudor responde según su ProbPago). Para
llamar de verdad a esos números necesitás telefonía (Twilio/central) y el
consentimiento de la persona — ver `docs/GUIA_LLAMADA_REAL_TWILIO.md`.

Se usa desde el **dashboard** (pestaña "🧪 Probar mi cartera", con subir
archivo / tabla editable / descarga) o por CLI:

    python -m realtime.mi_cartera                      # data/mi_cartera_prueba.csv
    python -m realtime.mi_cartera --base otros.csv --sin-claude

> ⚠️ El CSV con datos reales es privado (`.gitignore`). No se sube al repo.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from data.generate_dataset import generar  # noqa: E402
from kobra import cartera_manual, cumplimiento, explicabilidad, gestor_ia, negociador  # noqa: E402
from kobra.probpago import ProbPagoModel  # noqa: E402
from realtime.voicebot import ClienteSimulado  # noqa: E402

BASE_DEFAULT = os.path.join(ROOT, "data", "mi_cartera_prueba.csv")


def preparar_modelo(n: int = 6000, seed: int = 42):
    """Entrena ProbPago con la cartera sintética y devuelve (modelo, baseline)."""
    sint = generar(n, seed)
    model = ProbPagoModel().fit(sint)
    base = explicabilidad.baseline_cartera(sint)
    return model, base


def procesar(contactos: list[dict], model, base_expl,
             usar_claude: bool = False) -> list[dict]:
    """
    Corre el flujo completo sobre una lista de contactos y devuelve, por cada
    uno: score, reason codes, decisión de cumplimiento, transcripción de la
    negociación simulada y resultado. Sin efectos de impresión (para el
    dashboard y los tests).
    """
    df = cartera_manual.cargar_manual(contactos)
    df = cartera_manual.puntuar(model, df)
    df = negociador.recomendar(df)

    resultados = []
    for _, fila in df.iterrows():
        motivo = explicabilidad.explicar_texto(model, fila, base_expl, top=2)
        d = cumplimiento.puede_contactar(fila["id_deudor"], "Llamada")

        brief = cartera_manual.brief_desde_fila(fila)
        ses = gestor_ia.SesionGestorIA(
            id_deudor=fila["id_deudor"], canal="Llamada", gestor_id="IA01",
            usar_claude=usar_claude, brief=brief)
        cliente = ClienteSimulado(fila["id_deudor"], float(fila["probpago"]))

        transcript = []
        r = ses.responder(None)
        transcript.append(("gestor", r["texto"]))
        for _ in range(12):
            if r["fin"]:
                break
            msg = cliente.responder(r["texto"])
            transcript.append(("cliente", msg))
            r = ses.responder(msg)
            transcript.append(("gestor", r["texto"]))

        erp = ses.campos_erp
        resultados.append({
            "nombre": fila["nombre"] or fila["id_deudor"],
            "telefono": fila["telefono"],
            "id_deudor": fila["id_deudor"],
            "monto_deuda": float(fila["monto_deuda"]),
            "probpago": round(float(fila["probpago"]), 3),
            "propension": str(fila.get("segmento_propension", "Media")),
            "estrategia": fila["estrategia"],
            "descuento_recomendado": float(fila["descuento_recomendado"]),
            "plan_cuotas": int(fila["plan_cuotas"]),
            "motivo_probpago": motivo,
            "cumplimiento_ok": bool(d.permitido),
            "cumplimiento_codigo": d.codigo,
            "cumplimiento_motivo": d.motivo,
            "resultado": erp.get("resultado", "Sin acuerdo"),
            "monto_acordado": float(erp.get("monto_acordado", 0) or 0),
            "cuotas_acordadas": int(erp.get("cuotas", 0) or 0),
            "transcript": transcript,
        })
    return resultados


def resultados_a_dataframe(resultados: list[dict]) -> pd.DataFrame:
    """Tabla descargable (sin la transcripción, que va aparte)."""
    filas = [{k: v for k, v in r.items() if k != "transcript"} for r in resultados]
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _ancho(txt, n):
    return (txt[: n - 1] + "…") if len(txt) > n else txt


def correr(contactos: list[dict], usar_claude: bool = True) -> list[dict]:
    model, base = preparar_modelo()
    resultados = procesar(contactos, model, base, usar_claude=usar_claude)
    for r in resultados:
        print("\n" + "═" * 68)
        print(f"  {r['nombre']}   ☎ {r['telefono'] or '—'}   ·   "
              f"deuda $U {r['monto_deuda']:,.0f}")
        print("═" * 68)
        print(f"  ProbPago: {r['probpago']:.0%} ({r['propension']})  ·  "
              f"{r['estrategia']}  ·  desc. máx {r['descuento_recomendado']:.0%}  ·  "
              f"{r['plan_cuotas']} cuota(s)")
        print(f"  ¿Por qué?  {r['motivo_probpago']}")
        estado = "✓ permitido" if r["cumplimiento_ok"] else f"✗ bloqueado ({r['cumplimiento_codigo']})"
        print(f"  Cumplimiento: {estado} — {r['cumplimiento_motivo']}")
        print("  ── conversación ─────────────────────────────────────────────")
        for quien, texto in r["transcript"]:
            print(f"    {'🤖' if quien == 'gestor' else '🧑'} {texto}")
        print("  ── resultado ────────────────────────────────────────────────")
        print(f"    Resultado: {r['resultado']}"
              + (f"  ·  acordado $U {r['monto_acordado']:,.0f} "
                 f"en {r['cuotas_acordadas']} cuota(s)"
                 if r["resultado"] == "Promesa" else ""))
    return resultados


def main():
    ap = argparse.ArgumentParser(description='MV Kobra AI · "mi cartera de prueba"')
    ap.add_argument("--base", default=BASE_DEFAULT,
                    help="CSV con columnas nombre, telefono, monto_deuda (deuda)")
    ap.add_argument("--sin-claude", action="store_true",
                    help="usar plantillas locales (sin API de Claude)")
    args = ap.parse_args()

    if not os.path.exists(args.base):
        print(f"[mi_cartera] No encuentro {args.base}.")
        print("             Creá un CSV con columnas: nombre, telefono, deuda")
        raise SystemExit(1)

    contactos = cartera_manual.leer_csv(args.base)
    print(f"[mi_cartera] Cartera de prueba: {len(contactos)} contacto(s) · "
          f"{datetime.now():%Y-%m-%d %H:%M}")
    res = correr(contactos, usar_claude=not args.sin_claude)

    print("\n" + "═" * 68 + "\n  RESUMEN\n" + "═" * 68)
    for r in res:
        print(f"  {_ancho(r['nombre'], 22):22} {r['telefono']:12} "
              f"ProbPago {r['probpago']:.0%}  →  {r['resultado']}")
    print("\n  Para llamar de verdad: docs/GUIA_LLAMADA_REAL_TWILIO.md "
          "(telefonía + consentimiento).")


if __name__ == "__main__":
    main()
