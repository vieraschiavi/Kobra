"""
Kobra · Conectores de telefonía en vivo (streaming)
===================================================
Núcleo compartido para ingerir **audio en streaming** desde la central y
asesorar al gestor mientras la llamada ocurre.

Fuentes soportadas (mismo pipeline, distinto "adaptador" de entrada):
  - Twilio Media Streams  → WebSocket con audio μ-law 8 kHz (track inbound/outbound).
  - SIPREC (Avaya/Genesys/Cisco) → el SBC/grabador forkea el media (RTP) a un
    media server que reenvía PCM por WebSocket a /ws_audio.
  - Avaya DMCC/AES → el SDK entrega el audio del canal; se reenvía a /ws_audio.

`StreamSession` acumula audio por hablante, y al cerrar cada turno (silencio o
fin de utterance) transcribe (Whisper si hay OPENAI_API_KEY), calcula la emoción
acústica del tramo, fusiona voz+texto y corre el copiloto sobre la conversación
acumulada. Devuelve la asesoría lista para empujar a la pantalla del gestor.
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import copiloto, voz   # noqa: E402


def _ulaw_tabla() -> np.ndarray:
    """Tabla de decodificación μ-law (G.711) en numpy puro.
    `audioop` fue eliminado en Python 3.13, así que no dependemos de él."""
    u = np.arange(256, dtype=np.uint8)
    u = ~u
    sign = np.where(u & 0x80, -1, 1).astype(np.int32)
    exponente = (u >> 4) & 0x07
    mantisa = (u & 0x0F).astype(np.int32)
    magnitud = ((mantisa << 3) + 0x84) << exponente
    return (sign * (magnitud - 0x84)).astype(np.int16)


_ULAW = _ulaw_tabla()


def ulaw_to_float(payload: bytes) -> np.ndarray:
    """Decodifica μ-law (G.711, 8 kHz) a float [-1,1]. Usado por Twilio."""
    if not payload:
        return np.zeros(0, dtype=np.float32)
    idx = np.frombuffer(payload, dtype=np.uint8)
    return _ULAW[idx].astype(np.float32) / 32768.0


def pcm16_to_float(payload: bytes) -> np.ndarray:
    """Decodifica PCM16 little-endian a float [-1,1]. Usado por SIPREC/genérico."""
    return np.frombuffer(payload, dtype=np.int16).astype(np.float32) / 32768.0


class StreamSession:
    """Estado de una llamada en vivo (acumula por hablante y asesora por turno)."""

    def __init__(self, sr=8000, probpago=None, estrategia=None, min_seg=0.6,
                 id_deudor=None, gestor_id="G01"):
        self.sr = sr
        self.probpago = probpago
        self.estrategia = estrategia
        self.min_muestras = int(min_seg * sr)
        self.buffers = {"gestor": [], "cliente": []}
        self.turnos = []          # líneas "Gestor: …" / "Cliente: …"
        self.id_deudor = id_deudor
        self.gestor_id = gestor_id
        self.ultimo_estado = None   # último resultado del copiloto (para el cierre)

    def agregar(self, canal: str, samples: np.ndarray):
        if canal not in self.buffers:
            canal = "cliente"
        if samples.size:
            self.buffers[canal].append(samples)

    def _transcribir(self, samples: np.ndarray, texto_hint: str | None):
        """Whisper sobre el chunk si hay key; si no, usa el texto provisto."""
        texto = None
        if os.getenv("OPENAI_API_KEY"):
            import soundfile as sf
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                sf.write(tmp.name, samples, self.sr)
                path = tmp.name
            texto = copiloto.transcribir_audio(path)
            try:
                os.remove(path)
            except OSError:
                pass
        return texto or (texto_hint or "")

    def cerrar_turno(self, canal: str, texto_hint: str | None = None) -> dict | None:
        """Cierra el turno del hablante: transcribe, mide emoción y asesora."""
        if canal not in self.buffers or not self.buffers[canal]:
            if not texto_hint:
                return None
            samples = np.zeros(self.min_muestras, dtype=np.float32)
        else:
            samples = np.concatenate(self.buffers[canal])
        self.buffers[canal] = []
        if samples.size < self.min_muestras and not texto_hint:
            return None

        texto = self._transcribir(samples, texto_hint)
        feat = voz.extraer_features(samples, self.sr)
        emo = voz.emocion_acustica(feat)
        vozc = voz.voz_para_copiloto(feat)
        sent_fusion = (copiloto.analizar_sentimiento(texto, voz=vozc).score
                       if texto else None)

        if texto:
            etiqueta = "Gestor" if canal == "gestor" else "Cliente"
            self.turnos.append(f"{etiqueta}: {texto}")

        cop = cal = tec = None
        if self.turnos:
            res = copiloto.analizar_conversacion(
                "\n".join(self.turnos), canal="llamada",
                probpago=self.probpago, estrategia=self.estrategia,
                nombre_gestor="Gestor")
            cop, cal, tec = res["copiloto"], res["calidad"], res["tecnicas"]

        resultado = {
            "turno": {
                "canal": canal, "texto": texto,
                "emocion_voz": emo.emocion, "arousal": emo.arousal,
                "valencia": emo.valencia, "sent_fusion": sent_fusion,
            },
            "clima": cop["clima_emocional"] if cop else None,
            "clima_etiqueta": cop["clima_etiqueta"] if cop else None,
            "emociones_cliente": cop["emociones_cliente"] if cop else [],
            "tecnicas": [k for k, v in tec.items() if v] if tec else [],
            "calidad": cal["score_total"] if cal else None,
            "sugerencias": cop["sugerencias"] if cop else [],
            "proxima_frase": cop["proxima_frase"] if cop else None,
        }
        self.ultimo_estado = resultado
        return resultado

    def resumen_final(self) -> dict | None:
        """Estado final de la negociación, para persistir al colgar."""
        if not self.ultimo_estado:
            return None
        u = self.ultimo_estado
        return {
            "id_deudor": self.id_deudor,
            "gestor_id": self.gestor_id,
            "calidad": u["calidad"],
            "clima": u["clima"],
            "emociones": u["emociones_cliente"],
            "tecnicas": u["tecnicas"],
            "turnos": len(self.turnos),
        }


# Mapeo de tracks de Twilio → hablante
TWILIO_TRACK = {"inbound": "cliente", "outbound": "gestor"}
