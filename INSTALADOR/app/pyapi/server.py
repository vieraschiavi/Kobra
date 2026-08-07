"""
MV Kobra AI · API local para la app de escritorio (Electron)
==============================================================
Servidor FastAPI chico que corre en localhost y expone el MISMO motor
Python que usa el panel Streamlit (kobra/probpago.py, kobra/negociador.py,
kobra/config.py) — sin Streamlit de por medio. Electron lo levanta como
proceso hijo al arrancar y le habla por HTTP desde el renderer.

No reemplaza backend_venta/ (ese sigue siendo el backend de venta web con
Mercado Pago). Este server es solo para que la app de escritorio muestre
datos y valide una licencia ya emitida.

Ejecutar (desarrollo):
    uvicorn server:app --port 8420
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from kobra.probpago import ProbPagoModel          # noqa: E402
from kobra import negociador                      # noqa: E402
from kobra import config as kconfig                # noqa: E402
from backend_venta import licencias                # noqa: E402

app = FastAPI(title="MV Kobra AI · API local (desktop)", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

kconfig.aplicar()

_cache: dict = {}


def _cargar():
    if "full" in _cache:
        return _cache["full"], _cache["metrics"]
    import pandas as pd

    csv = os.path.join(ROOT, "data", "kobra_cartera.csv")
    if os.path.exists(csv):
        df = pd.read_csv(csv)
    else:
        from data.generate_dataset import generar
        df = generar(12000, 42)
    model = ProbPagoModel().fit(df)
    scored = model.score(df)
    full = negociador.recomendar(scored)
    _cache["full"] = full
    _cache["metrics"] = model.metrics
    return full, model.metrics


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/vision")
def vision_general():
    """KPIs + top oportunidades para la vista 'Visión general'."""
    full, metrics = _cargar()
    top = full.sort_values("valor_esperado_recupero", ascending=False).head(10)
    return {
        "metrics": metrics,
        "kpis": {
            "deudores": int(len(full)),
            "cartera_total_uyu": float(full["monto_deuda"].sum()),
            "recupero_esperado_uyu": float(full["valor_esperado_recupero"].sum()),
            "probpago_prom": float(full["probpago"].mean()),
        },
        "top_oportunidades": top[
            ["id_deudor", "monto_deuda", "probpago", "estrategia", "valor_esperado_recupero"]
        ].to_dict(orient="records"),
    }


@app.get("/api/negociador")
def agente_negociador():
    """Resumen de estrategias + acciones prioritarias para 'Agente Negociador'."""
    full, _ = _cargar()
    resumen = negociador.resumen_estrategias(full)
    top_acciones = full.sort_values("prioridad").head(15)
    return {
        "resumen_estrategias": resumen.to_dict(orient="records"),
        "top_acciones": top_acciones[
            ["id_deudor", "estrategia", "canal_recomendado", "descuento_recomendado",
             "plan_cuotas", "prioridad", "guion"]
        ].to_dict(orient="records"),
    }


@app.get("/api/config/estado")
def config_estado():
    return kconfig.estado()


class ActivarLicenciaBody(BaseModel):
    token: str


@app.post("/api/licencia/activar")
def activar_licencia(body: ActivarLicenciaBody):
    """Valida una licencia emitida por el backend de venta (mismo esquema JWT)."""
    r = licencias.licencia_activa(body.token)
    if not r["ok"]:
        raise HTTPException(401, r["error"])
    return {"ok": True, "claims": r["claims"]}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("KOBRA_LOCAL_API_PORT", "8420"))
    uvicorn.run(app, host="127.0.0.1", port=port)
