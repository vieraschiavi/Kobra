"""
Kobra IA · Voicebot (campañas salientes con Gestor IA)
======================================================
Corre campañas de llamadas donde el **Gestor IA** negocia como un humano:
cargás una base de teléfonos y el bot llama, negocia según ProbPago,
completa los campos ERP y registra cada gestión (aparece en el dashboard
"Gestores & Evolución" como gestor IA, medible contra humanos).

Concurrencia: hasta **50 líneas simultáneas** (asyncio.Semaphore) — el motor
de diálogo es puro CPU local, así que la concurrencia real la limita el canal
de voz, no Kobra.

Capas (para no depender de APIs externas):
  ┌───────────────────────────────────────────────────────────┐
  │ CEREBRO   kobra/gestor_ia.py — 100% local (Claude opcional)│
  ├───────────────────────────────────────────────────────────┤
  │ VOZ       TTS/STT enchufables y LOCALES:                   │
  │           - TTS: Piper (voz neuronal es-ES/es-AR, ~100 ms) │
  │           - STT: faster-whisper local                      │
  │           (si no están instalados, el motor corre en modo  │
  │            texto: mismo diálogo, sin audio)                │
  ├───────────────────────────────────────────────────────────┤
  │ CANAL     telefonía del cliente: Twilio (<Connect>),       │
  │           Avaya/SIPREC (conector RTP incluido), Asterisk…  │
  │           En demo: ClienteSimulado (sin canal externo).    │
  └───────────────────────────────────────────────────────────┘

Uso (demo, sin telefonía real):
    python -m realtime.voicebot --lineas 50 --llamadas 50
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra.gestor_ia import SesionGestorIA        # noqa: E402
from kobra import registro                        # noqa: E402


# ---------------------------------------------------------------------------
# Adaptador de VOZ local (opcional): Piper TTS / faster-whisper STT
# ---------------------------------------------------------------------------
def tts_local_disponible() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


def stt_local_disponible() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Cliente simulado (para demo/carga): responde según su propensión real
# ---------------------------------------------------------------------------
class ClienteSimulado:
    """Simula al deudor con una personalidad derivada de su ProbPago."""

    def __init__(self, id_deudor: str, probpago: float, semilla: int = 0):
        self.rng = random.Random(f"{id_deudor}-{semilla}")
        if probpago >= 0.65:
            self.libreto = ["Sí, soy yo, ¿qué necesitan?",
                            "Es mucha plata junta, ¿hay descuento?",
                            "Dale, acepto, me sirve."]
        elif probpago >= 0.35:
            self.libreto = ["Sí, con él habla.",
                            "No tengo ese dinero ahora, estoy complicado.",
                            "¿Y en cuotas se puede?",
                            "Está bien, de acuerdo, acepto las cuotas."]
        else:
            enojado = self.rng.random() < 0.5
            inicio = ("¡Estoy harto de que me llamen!" if enojado
                      else "Sí, soy yo, pero estoy sin trabajo.")
            final = ("Está bien, acepto esa última." if self.rng.random() < 0.4
                     else "No, no me interesa, no insista.")
            self.libreto = [inicio,
                            "No puedo pagar eso, es imposible.",
                            "Sigue siendo mucho, no me alcanza.",
                            final]
        self.i = 0

    def responder(self, _texto_gestor: str) -> str:
        r = self.libreto[min(self.i, len(self.libreto) - 1)]
        self.i += 1
        return r


# ---------------------------------------------------------------------------
# Campaña
# ---------------------------------------------------------------------------
async def _llamada(id_deudor: str, gestor_id: str, sem: asyncio.Semaphore,
                   metricas: dict, archivo_gestiones: str | None,
                   usar_claude: bool):
    async with sem:
        metricas["en_curso"] += 1
        metricas["pico"] = max(metricas["pico"], metricas["en_curso"])
        try:
            ses = SesionGestorIA(id_deudor=id_deudor, canal="Llamada",
                                 gestor_id=gestor_id, usar_claude=usar_claude)
            cliente = ClienteSimulado(id_deudor, float(ses.brief["probpago"]))
            r = ses.responder(None)                      # saludo
            for _ in range(12):                          # tope de turnos
                if r["fin"]:
                    break
                await asyncio.sleep(0.01)                # cede el loop (I/O real iría acá)
                r = ses.responder(cliente.responder(r["texto"]))
            g = ses.registrar(archivo=archivo_gestiones)
            metricas[g["resultado"]] = metricas.get(g["resultado"], 0) + 1
            metricas["ok"] += 1
        except Exception as e:
            metricas["errores"] += 1
            metricas.setdefault("detalle_errores", []).append(f"{id_deudor}: {e}")
        finally:
            metricas["en_curso"] -= 1


async def correr_campania(ids: list, lineas: int = 50, gestor_id: str = "IA01",
                          archivo_gestiones: str | None = None,
                          usar_claude: bool = True) -> dict:
    sem = asyncio.Semaphore(lineas)
    metricas = {"total": len(ids), "ok": 0, "errores": 0, "en_curso": 0, "pico": 0}
    t0 = time.perf_counter()
    await asyncio.gather(*[
        _llamada(i, gestor_id, sem, metricas, archivo_gestiones, usar_claude)
        for i in ids])
    metricas["segundos"] = round(time.perf_counter() - t0, 2)
    return metricas


def base_desde_cartera(n: int) -> list:
    """Demo: toma los top-N deudores priorizados como base de la campaña."""
    df = registro._scored()
    if df is None:
        raise SystemExit("Corré antes: python -m kobra.pipeline")
    return df.nsmallest(n, "prioridad")["id_deudor"].tolist()


def main():
    ap = argparse.ArgumentParser(description="Campaña saliente con Gestor IA")
    ap.add_argument("--base", default=None,
                    help="CSV con columna id_deudor (default: top prioridad de la cartera)")
    ap.add_argument("--llamadas", type=int, default=50)
    ap.add_argument("--lineas", type=int, default=50, help="líneas simultáneas (máx. 50)")
    ap.add_argument("--gestor", default="IA01")
    ap.add_argument("--sin-claude", action="store_true",
                    help="forzar plantillas locales (sin API de Claude)")
    args = ap.parse_args()

    if args.base:
        import pandas as pd
        ids = pd.read_csv(args.base)["id_deudor"].astype(str).tolist()[:args.llamadas]
    else:
        ids = base_desde_cartera(args.llamadas)

    lineas = min(args.lineas, 50)
    print(f"[voicebot] Campaña: {len(ids)} llamadas · {lineas} líneas simultáneas · "
          f"gestor {args.gestor}")
    print(f"[voicebot] Voz local: TTS Piper {'✓' if tts_local_disponible() else '– (modo texto)'} · "
          f"STT faster-whisper {'✓' if stt_local_disponible() else '– (modo texto)'}")
    m = asyncio.run(correr_campania(
        ids, lineas=lineas, gestor_id=args.gestor,
        usar_claude=not args.sin_claude))
    print(f"[voicebot] Listo en {m['segundos']}s · concurrencia pico: {m['pico']} · "
          f"OK {m['ok']}/{m['total']} · errores {m['errores']}")
    for k in ("Promesa", "Sin acuerdo"):
        if m.get(k):
            print(f"           {k}: {m[k]}")
    print("[voicebot] Gestiones registradas → dashboard 'Gestores & Evolución' "
          f"(gestor {args.gestor}).")


if __name__ == "__main__":
    main()
