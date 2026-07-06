"""
MV Kobra AI · Conector Avaya / SIPREC (puente RTP → Copiloto en vivo)
==================================================================
Recibe el audio que la central telefónica forkea por **RTP** (G.711 μ-law o
A-law, 8 kHz) — el mecanismo estándar de SIPREC (Avaya Aura/SBC, Genesys,
Cisco) y de Avaya DMCC/AES — y lo puentea al Copiloto de MV Kobra AI
(`/ws_audio`), que asesora al gestor turno a turno.

    Central (Avaya)                    Este conector                MV Kobra AI
    ───────────────                    ─────────────                ────────
    RTP gestor  → UDP :5004  ─┐   decodifica G.711 (PT 0/8),   ┌→ asesoría en
    RTP cliente → UDP :5006  ─┴─→ VAD por energía, corta el  ──┤  vivo por
                                  turno al silencio y lo       └→ WebSocket
                                  envía por WS a /ws_audio

Cómo se configura del lado Avaya (equipo de telefonía):
  - SIPREC: en el SBC/Aura, apuntar el Recording Server al host de este
    conector; el media de cada pata (gestor/cliente) llega como stream RTP
    a los puertos configurados.
  - DMCC/AES: registrar la estación virtual y dirigir el RTP del canal a
    este host/puerto.
  - El `id_deudor` viaja por el CTI (UUI / header SIP / evento de screen-pop):
    pasarlo por --deudor o por la API del CTI al iniciar cada llamada.

Uso:
    python -m realtime.conector_avaya --deudor KB-100773 --gestor G03
    # opciones: --kobra ws://localhost:8000/ws_audio --puerto-gestor 5004
    #           --puerto-cliente 5006 --silencio 0.6 --transcript archivo.txt

Prueba sin central real (simulador de RTP incluido):
    python -m realtime.server            # terminal 1
    python -m realtime.conector_avaya --deudor KB-100773   # terminal 2
    python -m realtime.simular_rtp       # terminal 3 (hace de central Avaya)
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from realtime import connectors   # noqa: E402

SR = 8000
UMBRAL_VOZ = 0.004        # RMS mínimo para considerar que hay voz


def parse_rtp(data: bytes):
    """Parsea un paquete RTP (RFC 3550). Devuelve (payload_type, seq, payload)."""
    if len(data) < 12 or (data[0] >> 6) != 2:      # versión RTP = 2
        return None
    cc = data[0] & 0x0F
    tiene_ext = (data[0] >> 4) & 1
    padding = (data[0] >> 5) & 1
    pt = data[1] & 0x7F
    seq = int.from_bytes(data[2:4], "big")
    off = 12 + cc * 4
    if tiene_ext:
        if len(data) < off + 4:
            return None
        ext_words = int.from_bytes(data[off + 2:off + 4], "big")
        off += 4 + ext_words * 4
    payload = data[off:]
    if padding and payload:
        payload = payload[:-payload[-1]]
    return pt, seq, payload


def decodificar(pt: int, payload: bytes) -> np.ndarray:
    """G.711 según payload type RTP: 0 = PCMU (μ-law), 8 = PCMA (A-law)."""
    if pt == 0:
        return connectors.ulaw_to_float(payload)
    if pt == 8:
        return connectors.alaw_to_float(payload)
    return np.zeros(0, dtype=np.float32)


class _CanalRTP(asyncio.DatagramProtocol):
    """Recibe el RTP de una pata (gestor o cliente) y acumula el turno."""

    def __init__(self, canal: str, puente: "PuenteAvaya"):
        self.canal = canal
        self.puente = puente
        self.buf: list = []
        self.hablando = False
        self.ultima_voz = 0.0
        self.paquetes = 0

    def datagram_received(self, data, addr):
        parsed = parse_rtp(data)
        if not parsed:
            return
        pt, _seq, payload = parsed
        samples = decodificar(pt, payload)
        if not samples.size:
            return
        self.paquetes += 1
        energia = float(np.sqrt(np.mean(samples ** 2)))
        ahora = time.monotonic()
        if energia > UMBRAL_VOZ:
            self.buf.append(samples)
            self.hablando = True
            self.ultima_voz = ahora
        elif self.hablando:
            self.buf.append(samples)       # pausas cortas dentro del turno

    def turno_listo(self, silencio_s: float) -> bool:
        return (self.hablando and self.buf
                and (time.monotonic() - self.ultima_voz) >= silencio_s)

    def extraer(self) -> np.ndarray:
        audio = np.concatenate(self.buf) if self.buf else np.zeros(0, "float32")
        self.buf, self.hablando = [], False
        return audio


class PuenteAvaya:
    """Orquesta: 2 sockets RTP → VAD → WebSocket /ws_audio de MV Kobra AI."""

    def __init__(self, args):
        self.args = args
        self.canales = {}
        self.ws = None
        self.hints = {"gestor": [], "cliente": []}
        if args.transcript and os.path.exists(args.transcript):
            from kobra import copiloto
            conv = copiloto.parsear_conversacion(
                open(args.transcript, encoding="utf-8").read(),
                nombre_gestor="Gestor")
            for t in conv.turnos:
                self.hints[t.emisor].append(t.texto)
            print(f"[conector] Transcript CTI cargado: "
                  f"{len(self.hints['gestor'])} turnos gestor / "
                  f"{len(self.hints['cliente'])} cliente")

    async def conectar_ws(self):
        import websockets
        self.ws = await websockets.connect(self.args.kobra)
        await self.ws.send(json.dumps({
            "tipo": "start", "sr": SR,
            "id_deudor": self.args.deudor, "gestor_id": self.args.gestor}))
        print(f"[conector] Conectado a {self.args.kobra} · deudor={self.args.deudor}")

    async def escuchar_asesoria(self):
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                if m.get("tipo") == "brief":
                    print(f"📋 BRIEF: {m['brief']['resumen']}")
                elif m.get("tipo") == "fin":
                    g = m.get("gestion")
                    if g:
                        print(f"💾 Gestión registrada: {g['id_gestion']} · "
                              f"{g['resultado']} · recupero $U {g['recupero']:,.0f}")
                    break
                elif "turno" in m:
                    t = m["turno"]
                    print(f"🗣️  {t['canal'].upper():<8} voz={t['emocion_voz']:<12}"
                          f" «{(t['texto'] or '(sin transcripción)')[:48]}»")
                    if m.get("sugerencias"):
                        s = m["sugerencias"][-1]
                        print(f"   💡 {s[0]}: {s[1][:70]}")
                    if m.get("proxima_frase"):
                        print(f"   💬 Próxima frase: {m['proxima_frase'][:78]}")
        except Exception as e:
            print(f"[conector] WS cerrado: {e}")

    async def vigilar_turnos(self):
        """Corta el turno de una pata cuando entra en silencio y lo envía."""
        while True:
            await asyncio.sleep(0.1)
            for canal, proto in self.canales.items():
                if proto.turno_listo(self.args.silencio):
                    audio = proto.extraer()
                    if len(audio) < SR * self.args.min_turno:
                        continue
                    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
                    texto = (self.hints[canal].pop(0)
                             if self.hints.get(canal) else None)
                    await self.ws.send(json.dumps({
                        "tipo": "media", "canal": canal,
                        "pcm_b64": base64.b64encode(pcm).decode(),
                        "texto": texto, "fin_turno": True}))

    async def correr(self):
        await self.conectar_ws()
        loop = asyncio.get_running_loop()
        for canal, puerto in (("gestor", self.args.puerto_gestor),
                              ("cliente", self.args.puerto_cliente)):
            _t, proto = await loop.create_datagram_endpoint(
                lambda c=canal: _CanalRTP(c, self),
                local_addr=(self.args.host, puerto))
            self.canales[canal] = proto
            print(f"[conector] RTP {canal} escuchando en udp://{self.args.host}:{puerto}")

        tareas = [asyncio.create_task(self.escuchar_asesoria()),
                  asyncio.create_task(self.vigilar_turnos())]
        if self.args.duracion:
            await asyncio.sleep(self.args.duracion)
            await self.ws.send(json.dumps({"tipo": "stop"}))
            await asyncio.wait(tareas, timeout=10)
        else:
            await asyncio.gather(*tareas)


def main():
    ap = argparse.ArgumentParser(description="Conector Avaya/SIPREC → MV Kobra AI")
    ap.add_argument("--kobra", default=os.getenv("KOBRA_WS", "ws://localhost:8000/ws_audio"))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--puerto-gestor", type=int, default=5004)
    ap.add_argument("--puerto-cliente", type=int, default=5006)
    ap.add_argument("--deudor", default=None, help="id_deudor (viene del CTI/UUI)")
    ap.add_argument("--gestor", default="G01", help="id del gestor")
    ap.add_argument("--silencio", type=float, default=0.6,
                    help="segundos de silencio que cierran el turno")
    ap.add_argument("--min-turno", type=float, default=0.4,
                    help="duración mínima (s) para considerar un turno")
    ap.add_argument("--transcript", default=None,
                    help="opcional: transcript del CTI para enriquecer sin Whisper")
    ap.add_argument("--duracion", type=float, default=None,
                    help="opcional: cortar y registrar la gestión a los N segundos")
    args = ap.parse_args()
    asyncio.run(PuenteAvaya(args).correr())


if __name__ == "__main__":
    main()
