"""
MV Kobra AI · Clonado de voz LOCAL y gratuito
==============================================
Alternativa sin costo a `kobra/voz_tts.py` (ElevenLabs, que cobra por carácter):
sintetiza texto imitando una voz de referencia, corriendo el modelo en la
propia máquina. Cero costo por uso y los datos nunca salen del equipo — que
para un producto que vende cumplimiento no es un detalle menor.

Se apoya en modelos open source de clonado *zero-shot*: alcanza un clip corto
de la voz a imitar, sin entrenar nada. Se prueban en orden de calidad y se usa
el primero disponible:

  1. Chatterbox (Resemble AI, MIT) — multilingüe, buena prosodia.
  2. XTTS-v2 (Coqui) — clásico, soporta español, más pesado.

Ambos corren en CPU (lento pero suficiente: la demo son 9 frases que se
generan UNA vez en build time) y aprovechan GPU si la hay.

Este módulo es la misma interfaz que `voz_tts.sintetizar`, así que el
generador del chatvoice puede usar cualquiera de los dos motores sin cambios.

Instalación (solo hace falta en la máquina que arma el paquete):
    pip install chatterbox-tts        # opción 1
    pip install TTS                   # opción 2 (XTTS-v2)
"""
from __future__ import annotations

import io
import os

# Muestra de voz de referencia por defecto: la locución del video oficial.
REFERENCIA_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "video", "MVKobraAI_Copiloto_Demo.mp4")

_MOTOR = None      # cache del modelo cargado (cargarlo cuesta segundos)
_MOTOR_NOMBRE = None


def motor_disponible() -> str:
    """Devuelve el nombre del motor de clonado instalado ('chatterbox',
    'xtts') o '' si no hay ninguno. No carga el modelo: solo comprueba el
    import, para poder decidir barato si vale la pena seguir."""
    import importlib.util
    if importlib.util.find_spec("chatterbox") is not None:
        return "chatterbox"
    if importlib.util.find_spec("TTS") is not None:
        return "xtts"
    return ""


def _referencia_wav(referencia: str | None) -> str:
    """Normaliza la muestra de referencia a un WAV mono 24 kHz en un temporal.
    Acepta un MP4/MP3/WAV — si viene un video, extrae el audio."""
    import subprocess
    import tempfile
    ref = referencia or REFERENCIA_DEFAULT
    if not os.path.exists(ref):
        raise FileNotFoundError(f"No encuentro la muestra de voz: {ref}")
    destino = os.path.join(tempfile.mkdtemp(), "referencia.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", ref,
                    "-vn", "-ac", "1", "-ar", "24000", destino], check=True)
    return destino


def _cargar(nombre: str):
    global _MOTOR, _MOTOR_NOMBRE
    if _MOTOR is not None and _MOTOR_NOMBRE == nombre:
        return _MOTOR
    if nombre == "chatterbox":
        from chatterbox.tts import ChatterboxTTS
        _MOTOR = ChatterboxTTS.from_pretrained(device="cpu")
    else:
        from TTS.api import TTS as CoquiTTS
        _MOTOR = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2")
    _MOTOR_NOMBRE = nombre
    return _MOTOR


def sintetizar(texto: str, voice_id: str | None = None, api_key: str | None = None,
               modelo: str | None = None, referencia: str | None = None,
               idioma: str = "es") -> dict:
    """Sintetiza `texto` clonando la voz de `referencia`.

    Misma firma y mismo dict de retorno que `voz_tts.sintetizar`, para que sea
    intercambiable: {"ok", "audio" (bytes MP3), "caracteres", "costo_est_usd",
    "error"}. `voice_id`/`api_key`/`modelo` se aceptan y se ignoran — existen
    solo para que el llamador no tenga que saber qué motor está usando.
    El costo siempre es 0: corre local.

    Nunca levanta excepción: ante cualquier fallo devuelve ok=False con el
    motivo, para no cortar un build por un problema de audio.
    """
    caracteres = len(texto or "")
    vacio = {"ok": False, "audio": None, "caracteres": caracteres,
             "costo_est_usd": 0.0}
    if not texto:
        return {**vacio, "error": "Falta el texto a sintetizar."}
    nombre = motor_disponible()
    if not nombre:
        return {**vacio, "error": "No hay motor de clonado local instalado "
                                  "(pip install chatterbox-tts)."}
    try:
        import numpy as np
        import soundfile as sf
        ref = _referencia_wav(referencia)
        motor = _cargar(nombre)

        if nombre == "chatterbox":
            wav = motor.generate(texto, audio_prompt_path=ref)
            audio = wav.squeeze(0).cpu().numpy() if hasattr(wav, "cpu") else np.asarray(wav)
            sr = motor.sr
        else:
            audio = np.asarray(motor.tts(text=texto, speaker_wav=ref, language=idioma))
            sr = 24000

        # A MP3 (lo que consume el dashboard estático), vía ffmpeg por stdin.
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV")
        import subprocess
        mp3 = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
             "-codec:a", "libmp3lame", "-q:a", "3", "-f", "mp3", "pipe:1"],
            input=buf.getvalue(), capture_output=True, check=True).stdout
        return {"ok": True, "audio": mp3, "caracteres": caracteres,
                "costo_est_usd": 0.0, "error": None}
    except Exception as e:
        return {**vacio, "error": f"{type(e).__name__}: {str(e)[:250]}"}
