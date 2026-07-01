"""
Kobra · Simulador de streaming en vivo
======================================
Simula una central telefónica enviando el audio de la llamada en streaming al
endpoint /ws_audio, turno a turno (con el audio real de cada canal), y muestra
la asesoría del copiloto que llega en vivo. Sirve para probar el conector de
streaming sin una central real.

Uso (con el servidor corriendo: python -m realtime.server):
    python -m realtime.simular_stream
"""
import asyncio
import base64
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import voz, copiloto   # noqa: E402

WAV = os.path.join(ROOT, "data", "ejemplo_llamada.wav")
TXT = os.path.join(ROOT, "data", "ejemplo_whatsapp.txt")
URL = os.getenv("KOBRA_WS", "ws://localhost:8000/ws_audio")


async def main():
    import websockets
    if not os.path.exists(WAV):
        from data.generate_audio_demo import generar
        generar()

    y, sr, _ = voz.cargar_audio(WAV)
    tt = None
    if os.path.exists(TXT):
        conv = copiloto.parsear_conversacion(open(TXT, encoding="utf-8").read(),
                                             nombre_gestor="Gestor")
        tt = [{"emisor": t.emisor, "texto": t.texto} for t in conv.turnos]
    segmentos, _modo = voz.transcribir_llamada(WAV, transcript_turnos=tt)

    print(f"[sim] Conectando a {URL} … streaming {len(segmentos)} turnos\n")
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({"tipo": "start", "sr": sr,
                                  "probpago": 0.72, "estrategia": "Plan de cuotas"}))
        for s in segmentos:
            canal = "gestor" if s["hablante"].lower().startswith("gestor") else "cliente"
            ch = 0 if canal == "gestor" else 1
            chunk = y[int(s["inicio"] * sr):int(s["fin"] * sr),
                      ch if y.shape[1] > 1 else 0]
            pcm = (np.clip(chunk, -1, 1) * 32767).astype(np.int16).tobytes()
            await ws.send(json.dumps({
                "tipo": "media", "canal": canal,
                "pcm_b64": base64.b64encode(pcm).decode(),
                "texto": s["texto"], "fin_turno": True}))
            r = json.loads(await ws.recv())
            tinfo = r["turno"]
            print(f"🗣️  {tinfo['canal'].upper():<8} voz={tinfo['emocion_voz']:<11} "
                  f"fusion={tinfo['sent_fusion']}  «{tinfo['texto'][:45]}»")
            if r.get("sugerencias"):
                print(f"   💡 {r['sugerencias'][-1][0]}: {r['sugerencias'][-1][1][:70]}")
            await asyncio.sleep(0.2)
        await ws.send(json.dumps({"tipo": "stop"}))
    print("\n[sim] Fin del stream.")


if __name__ == "__main__":
    asyncio.run(main())
