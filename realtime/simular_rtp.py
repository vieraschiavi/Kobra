# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Simulador de central Avaya (emisor RTP)
==================================================
Hace de central telefónica: toma la grabación demo dual-channel y la emite
como **RTP G.711** (μ-law o A-law) hacia el conector Avaya, tal como lo haría
un SBC con SIPREC — paquetes de 20 ms, seq/timestamp reales, una pata por
puerto. Sirve para probar el puente completo sin una Avaya física:

    central (este simulador) ──RTP──► conector_avaya ──WS──► MV Kobra AI

Uso (con server y conector corriendo):
    python -m realtime.simular_rtp [--codec ulaw|alaw] [--speed 2.0]
"""
import argparse
import asyncio
import os
import socket
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SR_RTP = 8000
FRAME = 160          # 20 ms @ 8 kHz


_SEG_UEND = np.array([0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF])
_SEG_AEND = np.array([0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF])


def lin_a_ulaw(x: np.ndarray) -> bytes:
    """Codifica float [-1,1] a μ-law (G.711, algoritmo de referencia CCITT)."""
    pcm = ((np.clip(x, -1, 1) * 32767).astype(np.int32)) >> 2
    mask = np.where(pcm < 0, 0x7F, 0xFF)
    pcm = np.minimum(np.abs(pcm), 8159) + 33          # CLIP + BIAS>>2
    seg = np.searchsorted(_SEG_UEND, pcm)
    uval = np.where(seg >= 8, 0x7F,
                    (seg << 4) | ((pcm >> (seg + 1)) & 0x0F))
    return ((uval ^ mask) & 0xFF).astype(np.uint8).tobytes()


def lin_a_alaw(x: np.ndarray) -> bytes:
    """Codifica float [-1,1] a A-law (G.711, algoritmo de referencia de 13 bits)."""
    pcm = ((np.clip(x, -1, 1) * 32767).astype(np.int32)) >> 3
    mask = np.where(pcm >= 0, 0xD5, 0x55)
    pcm = np.where(pcm >= 0, pcm, -pcm - 1)
    seg = np.searchsorted(_SEG_AEND, pcm)
    aval = np.where(
        seg >= 8, 0x7F,
        (seg << 4) | np.where(seg < 2, (pcm >> 1) & 0x0F,
                              (pcm >> seg) & 0x0F))
    return ((aval ^ mask) & 0xFF).astype(np.uint8).tobytes()


def rtp_packet(pt: int, seq: int, ts: int, ssrc: int, payload: bytes) -> bytes:
    return struct.pack("!BBHII", 0x80, pt & 0x7F, seq & 0xFFFF,
                       ts & 0xFFFFFFFF, ssrc) + payload


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--puerto-gestor", type=int, default=5004)
    ap.add_argument("--puerto-cliente", type=int, default=5006)
    ap.add_argument("--codec", choices=["ulaw", "alaw"], default="alaw",
                    help="A-law es el estándar en Uruguay")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="aceleración de la emisión (2.0 = doble velocidad)")
    ap.add_argument("--wav", default=os.path.join(ROOT, "data", "ejemplo_llamada.wav"))
    args = ap.parse_args()

    from kobra import voz
    if not os.path.exists(args.wav):
        from data.generate_audio_demo import generar
        generar()
    y, sr, canales = voz.cargar_audio(args.wav)
    if canales < 2:
        y = np.repeat(y, 2, axis=1)
    paso = max(int(sr // SR_RTP), 1)                 # 16 kHz → 8 kHz
    y8 = y[::paso, :]

    pt = 0 if args.codec == "ulaw" else 8
    enc = lin_a_ulaw if args.codec == "ulaw" else lin_a_alaw
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    destinos = {0: (args.host, args.puerto_gestor),
                1: (args.host, args.puerto_cliente)}
    ssrc = {0: 0x0B0B0001, 1: 0x0B0B0002}
    seq = {0: 0, 1: 0}

    n_frames = len(y8) // FRAME
    print(f"[simRTP] Emitiendo {n_frames} frames de 20 ms por pata "
          f"({args.codec.upper()}, x{args.speed}) → gestor:{args.puerto_gestor} "
          f"cliente:{args.puerto_cliente}")
    for i in range(n_frames):
        ts = i * FRAME
        for ch in (0, 1):
            frame = y8[i * FRAME:(i + 1) * FRAME, ch]
            sock.sendto(rtp_packet(pt, seq[ch], ts, ssrc[ch], enc(frame)),
                        destinos[ch])
            seq[ch] += 1
        await asyncio.sleep(0.020 / args.speed)
    print("[simRTP] Fin de la llamada simulada.")


if __name__ == "__main__":
    asyncio.run(main())
