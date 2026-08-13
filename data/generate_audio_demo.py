# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Generador de grabación de llamada (demo)
================================================
Sintetiza una llamada de cobranza en formato DUAL-CHANNEL (estéreo):
    - Canal 0 (izquierda): Gestor
    - Canal 1 (derecha):   Cliente
Cada turno se genera con prosodia distinta (tono, variación, energía, ritmo)
para reflejar la emoción, de modo que la diarización y la emoción acústica
tengan algo real que analizar. No es voz real (no dice palabras): es una señal
vocal sintética para demostrar el pipeline de audio de punta a punta.

Uso:
    python data/generate_audio_demo.py
"""
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 16000

# (canal, duración s, F0 base, variación F0, energía, ritmo sílabas/s, emoción)
#  canal 0 = Gestor, 1 = Cliente
TURNOS = [
    (0, 3.0, 120, 8,  0.10, 4.0, "gestor-calmo"),
    (1, 2.4, 190, 12, 0.09, 3.5, "cliente-neutro"),
    (0, 3.4, 120, 9,  0.10, 4.0, "gestor-empatico"),
    (1, 3.2, 210, 45, 0.16, 5.2, "cliente-frustrado"),   # cansado / sin trabajo
    (0, 3.0, 118, 8,  0.10, 3.8, "gestor-calmo"),
    (1, 2.6, 205, 38, 0.14, 4.8, "cliente-preocupado"),  # es mucha plata
    (0, 3.6, 122, 10, 0.11, 4.2, "gestor-propone"),
    (1, 1.8, 175, 14, 0.11, 3.6, "cliente-considera"),
    (0, 3.2, 120, 9,  0.10, 4.0, "gestor-cierra"),
    (1, 1.6, 165, 10, 0.12, 3.4, "cliente-acepta"),      # dale, gracias, acepto
]
GAP = 0.5   # silencio entre turnos


def _synth(dur, f0, f0_var, energy, rate, rng):
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Contorno de F0 (variación lenta)
    contour = f0 + f0_var * np.sin(2 * np.pi * 0.7 * t + rng.random() * 6) \
        + f0_var * 0.4 * rng.standard_normal(n).cumsum() / np.sqrt(n)
    phase = 2 * np.pi * np.cumsum(contour) / SR
    sig = np.zeros(n)
    for k, amp in enumerate([1.0, 0.5, 0.3, 0.15], start=1):   # armónicos
        sig += amp * np.sin(k * phase)
    # Envolvente silábica (onsets ~ ritmo) → da "velocidad de habla"
    env = 0.5 * (1 + np.sin(2 * np.pi * rate * t - np.pi / 2))
    env = np.clip(env, 0.05, 1) ** 1.5
    sig = sig * env
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * energy
    # Ruido de aliento leve
    sig += 0.004 * rng.standard_normal(n)
    return sig


def generar(seed=42, out=None):
    rng = np.random.default_rng(seed)
    total = sum(d for _, d, *_ in TURNOS) + GAP * len(TURNOS)
    n_total = int(total * SR)
    audio = np.zeros((n_total, 2))
    cursor = 0.0
    for canal, dur, f0, f0v, en, rate, _ in TURNOS:
        s = _synth(dur, f0, f0v, en, rate, rng)
        i0 = int(cursor * SR)
        audio[i0:i0 + len(s), canal] += s
        cursor += dur + GAP
    out = out or os.path.join(ROOT, "data", "ejemplo_llamada.wav")
    import soundfile as sf
    sf.write(out, audio, SR)
    return out, total


if __name__ == "__main__":
    out, dur = generar()
    print(f"[OK] Grabación demo (dual-channel) generada: {out}  ({dur:.1f}s, {SR} Hz)")
