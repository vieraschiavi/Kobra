"""
Kobra IA · "Mi cartera de prueba" (modo cliente, no premium)
============================================================
Corré el flujo COMPLETO de Kobra sobre TUS propios contactos —nombre,
teléfono, monto— para probarlo de punta a punta sin la cartera sintética:

    ProbPago (por qué)  →  estrategia + descuento + guion  →  chequeo de
    cumplimiento (¿puedo llamar ahora?)  →  Gestor IA negociando  →  resultado

La conversación se **simula** (el deudor responde según su ProbPago). Para
llamar de verdad a esos números necesitás telefonía (Twilio/central) y el
consentimiento de la persona — ver la nota "LLAMADA REAL" al final.

Uso:
    python -m realtime.mi_cartera                      # data/mi_cartera_prueba.csv
    python -m realtime.mi_cartera --base otros.csv
    python -m realtime.mi_cartera --sin-claude         # sin API de Claude

> ⚠️ El CSV con datos reales es privado (`.gitignore`). No se sube al repo.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd                                      # noqa: E402

from kobra.probpago import ProbPagoModel                 # noqa: E402
from kobra import (cartera_manual, negociador, explicabilidad,   # noqa: E402
                   cumplimiento, gestor_ia)
from realtime.voicebot import ClienteSimulado            # noqa: E402
from data.generate_dataset import generar                # noqa: E402

BASE_DEFAULT = os.path.join(ROOT, "data", "mi_cartera_prueba.csv")


def _ancho(txt, n):
    return (txt[: n - 1] + "…") if len(txt) > n else txt


def correr(contactos: list[dict], usar_claude: bool = True) -> list[dict]:
    # 1) Modelo ProbPago entrenado con la cartera sintética (el "cerebro")
    model = ProbPagoModel().fit(generar(6000, 42))
    base_expl = explicabilidad.baseline_cartera(generar(6000, 42))

    # 2) Tu cartera → score + estrategia + reason codes
    df = cartera_manual.cargar_manual(contactos)
    df = cartera_manual.puntuar(model, df)
    df = negociador.recomendar(df)

    resultados = []
    for _, fila in df.iterrows():
        nombre = fila["nombre"] or fila["id_deudor"]
        tel = fila["telefono"]
        motivo = explicabilidad.explicar_texto(model, fila, base_expl, top=2)

        print("\n" + "═" * 68)
        print(f"  {nombre}   ☎ {tel or '—'}   ·   deuda $U {fila['monto_deuda']:,.0f}")
        print("═" * 68)
        print(f"  ProbPago: {fila['probpago']:.0%} ({fila['segmento_propension']})  ·  "
              f"{fila['estrategia']}  ·  desc. máx {fila['descuento_recomendado']:.0%}  ·  "
              f"{int(fila['plan_cuotas'])} cuota(s)")
        print(f"  ¿Por qué?  {motivo}")

        # 3) Cumplimiento: ¿se puede contactar ahora?
        d = cumplimiento.puede_contactar(fila["id_deudor"], "Llamada")
        estado = "✓ permitido" if d.permitido else f"✗ bloqueado ({d.codigo})"
        print(f"  Cumplimiento: {estado} — {d.motivo}")

        # 4) Gestor IA negocia (conversación simulada)
        brief = cartera_manual.brief_desde_fila(fila)
        ses = gestor_ia.SesionGestorIA(
            id_deudor=fila["id_deudor"], canal="Llamada", gestor_id="IA01",
            usar_claude=usar_claude, brief=brief)
        cliente = ClienteSimulado(fila["id_deudor"], float(fila["probpago"]))

        print("  ── conversación ─────────────────────────────────────────────")
        r = ses.responder(None)
        print(f"    🤖 {r['texto']}")
        for _ in range(12):
            if r["fin"]:
                break
            msg = cliente.responder(r["texto"])
            print(f"    🧑 {msg}")
            r = ses.responder(msg)
            print(f"    🤖 {r['texto']}")

        erp = ses.campos_erp
        print("  ── resultado ────────────────────────────────────────────────")
        print(f"    Resultado: {erp.get('resultado', 'Sin acuerdo')}"
              + (f"  ·  acordado $U {erp.get('monto_acordado', 0):,.0f}"
                 f" en {erp.get('cuotas', 0)} cuota(s)"
                 if erp.get('resultado') == 'Promesa' else ""))
        resultados.append({
            "nombre": nombre, "telefono": tel,
            "id_deudor": fila["id_deudor"],
            "probpago": round(float(fila["probpago"]), 3),
            "estrategia": fila["estrategia"],
            "resultado": erp.get("resultado", "Sin acuerdo"),
            "monto_acordado": erp.get("monto_acordado", 0),
        })
    return resultados


def main():
    ap = argparse.ArgumentParser(description='Kobra · "mi cartera de prueba"')
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

    print("\n" + "═" * 68)
    print("  RESUMEN")
    print("═" * 68)
    for r in res:
        print(f"  {_ancho(r['nombre'], 22):22} {r['telefono']:12} "
              f"ProbPago {r['probpago']:.0%}  →  {r['resultado']}")

    print("\n  ── LLAMADA REAL ─────────────────────────────────────────────")
    print("  Esta corrida SIMULA la conversación. Para llamar de verdad a estos")
    print("  números necesitás: (1) telefonía —tu cuenta de Twilio con un número,")
    print("  o tu central Avaya/Asterisk— y (2) el CONSENTIMIENTO de la persona.")
    print("  Con Twilio: el <Connect><Stream> apunta a wss://<host>/twilio y el")
    print("  Gestor IA toma la llamada (ver realtime/server.py y README).")


if __name__ == "__main__":
    main()
