"""
MV Kobra AI · Voicebot (campañas salientes con Gestor IA)
======================================================
Corre campañas de llamadas donde el **Gestor IA** negocia como un humano:
cargás una base de teléfonos y el bot llama, negocia según ProbPago,
completa los campos ERP y registra cada gestión (aparece en el dashboard
"Gestores & Evolución" como gestor IA, medible contra humanos).

Concurrencia: hasta **50 líneas simultáneas** (asyncio.Semaphore + el tope
compartido de `kobra/concurrencia.py`). Cada turno de diálogo se resuelve en un
hilo, no en el event loop: sin key de LLM el motor es CPU local y rendía igual
de las dos formas, pero con LLM la espera de red bloqueaba el loop y las 50
líneas se atendían de a una (medido: 15,1 s contra 0,66 s con 50 simultáneas).

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
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra.gestor_ia import SesionGestorIA        # noqa: E402
from kobra import concurrencia as kconc           # noqa: E402
from kobra import cumplimiento, registro          # noqa: E402


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
            r = await asyncio.to_thread(ses.responder, None)      # saludo
            for _ in range(12):                          # tope de turnos
                if r["fin"]:
                    break
                await asyncio.sleep(0.01)                # cede el loop (I/O real iría acá)
                r = await asyncio.to_thread(ses.responder, cliente.responder(r["texto"]))
            g = await asyncio.to_thread(ses.registrar, archivo_gestiones)
            metricas[g["resultado"]] = metricas.get(g["resultado"], 0) + 1
            metricas["ok"] += 1
        except Exception as e:
            metricas["errores"] += 1
            metricas.setdefault("detalle_errores", []).append(f"{id_deudor}: {e}")
        finally:
            metricas["en_curso"] -= 1


async def correr_campania(ids: list, lineas: int = 50, gestor_id: str = "IA01",
                          archivo_gestiones: str | None = None,
                          usar_claude: bool = True,
                          respetar_no_contactar: bool = True,
                          archivo_dnc: str = cumplimiento.NO_CONTACTAR_CSV) -> dict:
    solicitados = len(ids)
    bloqueados = 0
    if respetar_no_contactar:
        permitidos = [i for i in ids
                      if not cumplimiento.esta_en_no_contactar(i, "Llamada", archivo_dnc)]
        bloqueados = solicitados - len(permitidos)
        ids = permitidos
    # El tope vive acá, no solo en el CLI: `correr_campania` se llama también
    # desde el dashboard y desde tests, y ahí `--lineas 200` entraba sin
    # chistar (medido: pico 200 líneas simultáneas). El tope es el mismo del
    # resto del producto (kobra/concurrencia.py, KOBRA_MAX_LLAMADAS).
    lineas = max(min(int(lineas), kconc.MAX_SIMULTANEAS), 1)
    sem = asyncio.Semaphore(lineas)
    metricas = {"total": len(ids), "solicitados": solicitados,
                "bloqueados_no_contactar": bloqueados, "lineas": lineas,
                "ok": 0, "errores": 0, "en_curso": 0, "pico": 0}
    t0 = time.perf_counter()
    # El executor por default de asyncio tiene min(32, cpu+4) hilos — 8 en una
    # máquina de 4 núcleos. Con 50 líneas pedidas, 42 quedarían esperando un
    # hilo libre sin que nada lo diga. Se dimensiona por las líneas reales.
    ejecutor = ThreadPoolExecutor(max_workers=lineas, thread_name_prefix="linea")
    asyncio.get_running_loop().set_default_executor(ejecutor)
    try:
        await asyncio.gather(*[
            _llamada(i, gestor_id, sem, metricas, archivo_gestiones, usar_claude)
            for i in ids])
    finally:
        ejecutor.shutdown(wait=False)
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
    ap.add_argument("--lineas", type=int, default=kconc.MAX_SIMULTANEAS,
                    help=f"líneas simultáneas (máx. {kconc.MAX_SIMULTANEAS})")
    ap.add_argument("--gestor", default="IA01")
    ap.add_argument("--sin-claude", action="store_true",
                    help="forzar plantillas locales (sin API de Claude)")
    args = ap.parse_args()

    if args.base:
        import pandas as pd
        ids = pd.read_csv(args.base)["id_deudor"].astype(str).tolist()[:args.llamadas]
    else:
        ids = base_desde_cartera(args.llamadas)

    lineas = min(args.lineas, kconc.MAX_SIMULTANEAS)
    print(f"[voicebot] Campaña: {len(ids)} llamadas · {lineas} líneas simultáneas · "
          f"gestor {args.gestor}")
    print(f"[voicebot] Voz local: TTS Piper {'✓' if tts_local_disponible() else '– (modo texto)'} · "
          f"STT faster-whisper {'✓' if stt_local_disponible() else '– (modo texto)'}")
    m = asyncio.run(correr_campania(
        ids, lineas=lineas, gestor_id=args.gestor,
        usar_claude=not args.sin_claude))
    if m.get("bloqueados_no_contactar"):
        print(f"[voicebot] Cumplimiento: {m['bloqueados_no_contactar']} deudor(es) "
              f"omitido(s) por estar en la lista de No Contactar (opt-out).")
    print(f"[voicebot] Listo en {m['segundos']}s · concurrencia pico: {m['pico']} · "
          f"OK {m['ok']}/{m['total']} · errores {m['errores']}")
    for k in ("Promesa", "Sin acuerdo"):
        if m.get(k):
            print(f"           {k}: {m[k]}")
    print("[voicebot] Gestiones registradas → dashboard 'Gestores & Evolución' "
          f"(gestor {args.gestor}).")


if __name__ == "__main__":
    main()
