# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Caso de negocio (estimador de ROI)
=============================================
Traduce la cartera del comprador en un rango de valor esperado, para dar
sustento económico a la venta y al precio del piloto.

> ⚠️ **Honestidad primero.** El *uplift* (mejora de la tasa de recupero por
> usar MV Kobra AI) es un **supuesto que carga el usuario**, NO un resultado medido.
> Este módulo NO afirma que MV Kobra AI suba el recupero X puntos: proyecta *cuánto
> valdría* bajo distintos supuestos, para que el cliente vea el tamaño del
> premio y se justifique un **piloto pago acotado** que mida el uplift real.
> Recién con ese piloto los números dejan de ser hipótesis.
"""
from __future__ import annotations

from dataclasses import dataclass

ESCENARIOS_DEFAULT = {
    "conservador": 0.02,   # +2 pp de tasa de recupero
    "base": 0.05,          # +5 pp
    "optimista": 0.08,     # +8 pp
}


@dataclass
class Escenario:
    nombre: str
    uplift_pp: float                 # mejora en la tasa de recupero (fracción, ej. 0.05)
    recupero_base_uyu: float
    recupero_con_kobra_uyu: float
    recupero_adicional_uyu: float
    costo_periodo_uyu: float
    beneficio_neto_uyu: float
    roi: float | None                # beneficio_neto / costo
    payback_meses: float | None      # meses para cubrir el costo con el adicional

    def as_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "uplift_pp": round(self.uplift_pp * 100, 2),
            "recupero_base_uyu": round(self.recupero_base_uyu, 0),
            "recupero_con_kobra_uyu": round(self.recupero_con_kobra_uyu, 0),
            "recupero_adicional_uyu": round(self.recupero_adicional_uyu, 0),
            "costo_periodo_uyu": round(self.costo_periodo_uyu, 0),
            "beneficio_neto_uyu": round(self.beneficio_neto_uyu, 0),
            "roi": round(self.roi, 2) if self.roi is not None else None,
            "payback_meses": (round(self.payback_meses, 1)
                              if self.payback_meses is not None else None),
        }


def estimar(cartera_total_uyu: float, tasa_recupero_base: float,
            escenarios: dict | None = None, meses: int = 12,
            costo_mensual_uyu: float = 0.0,
            costo_implementacion_uyu: float = 0.0) -> dict:
    """
    Proyecta el caso de negocio sobre `meses` de operación.

    - `cartera_total_uyu`: monto gestionable en el período.
    - `tasa_recupero_base`: tasa de recupero actual del cliente (0–1), SIN MV Kobra AI.
    - `escenarios`: {nombre: uplift_pp} en fracción (default conservador/base/optimista).
    - `costo_mensual_uyu`: fee mensual de MV Kobra AI; `costo_implementacion_uyu`: setup único.

    El uplift se aplica de forma **absoluta** sobre la tasa (ej. 30 % → 35 % con
    +5 pp), acotado a 1.0.
    """
    escenarios = escenarios or ESCENARIOS_DEFAULT
    costo_total = costo_mensual_uyu * meses + costo_implementacion_uyu
    recupero_base = cartera_total_uyu * tasa_recupero_base

    out = {}
    for nombre, uplift in escenarios.items():
        tasa_kobra = min(tasa_recupero_base + uplift, 1.0)
        recupero_kobra = cartera_total_uyu * tasa_kobra
        adicional = recupero_kobra - recupero_base
        beneficio_neto = adicional - costo_total
        roi = (beneficio_neto / costo_total) if costo_total > 0 else None
        adicional_mensual = adicional / max(meses, 1)
        payback = (costo_total / adicional_mensual
                   if adicional_mensual > 0 else None)
        out[nombre] = Escenario(
            nombre=nombre, uplift_pp=uplift,
            recupero_base_uyu=recupero_base,
            recupero_con_kobra_uyu=recupero_kobra,
            recupero_adicional_uyu=adicional,
            costo_periodo_uyu=costo_total,
            beneficio_neto_uyu=beneficio_neto,
            roi=roi, payback_meses=payback).as_dict()

    return {
        "supuestos": {
            "cartera_total_uyu": round(cartera_total_uyu, 0),
            "tasa_recupero_base": round(tasa_recupero_base, 4),
            "meses": meses,
            "costo_mensual_uyu": round(costo_mensual_uyu, 0),
            "costo_implementacion_uyu": round(costo_implementacion_uyu, 0),
        },
        "escenarios": out,
        "NOTA": ("El uplift es un SUPUESTO del usuario, no un resultado medido. "
                 "Esta proyección dimensiona el premio para justificar un piloto "
                 "pago acotado que mida el uplift real con grupo de control."),
    }


def _cli():
    import argparse
    p = argparse.ArgumentParser(description="MV Kobra AI · estimador de caso de negocio")
    p.add_argument("--cartera", type=float, required=True, help="Cartera gestionable (UYU)")
    p.add_argument("--tasa-base", type=float, required=True, help="Tasa de recupero actual (0-1)")
    p.add_argument("--meses", type=int, default=12)
    p.add_argument("--costo-mensual", type=float, default=0.0)
    p.add_argument("--costo-setup", type=float, default=0.0)
    a = p.parse_args()
    r = estimar(a.cartera, a.tasa_base, meses=a.meses,
                costo_mensual_uyu=a.costo_mensual,
                costo_implementacion_uyu=a.costo_setup)
    print(f"\nCartera: $U {r['supuestos']['cartera_total_uyu']:,.0f} · "
          f"tasa base {r['supuestos']['tasa_recupero_base']:.1%} · {a.meses} meses\n")
    for nombre, e in r["escenarios"].items():
        print(f"  [{nombre:>11}] +{e['uplift_pp']:.0f} pp → "
              f"adicional $U {e['recupero_adicional_uyu']:,.0f}"
              + (f" · ROI {e['roi']:.1f}x · payback {e['payback_meses']:.1f} m"
                 if e["roi"] is not None else ""))
    print(f"\n  {r['NOTA']}\n")


if __name__ == "__main__":
    _cli()
