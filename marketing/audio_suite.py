# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Narración montada sobre el screencast de la suite
================================================================
`screencast_suite.py` graba la pantalla (sin audio) y `subtitulos.py` escribe
los .vtt. Faltaba el paso del medio: **poner la voz encima del video**. Hasta
acá `voz_suite.py` dejaba los MP3 sueltos en una carpeta y el docstring decía
"mezclalos con cualquier editor" — o sea, a mano, cada vez que se regrabe el
screencast. Este módulo cierra ese hueco.

Qué hace, en orden:

1. Sintetiza cada cue de `SUITE_CUES` (el MISMO texto que los subtítulos: no
   hay un guion aparte que se pueda desincronizar).
2. Lo coloca en la línea de tiempo en el segundo exacto en que arranca su
   subtítulo, con `adelay`.
3. **Estira el video si la narración no entra.** El screencast dura 52,84 s y
   la narración termina cerca del minuto: sin esto, el cierre —el que dice el
   dominio, o sea el único llamado a la acción del video— se reproducía sobre
   una pantalla que ya no existía. Se congela el último cuadro (`tpad`) el
   tiempo que falte. La duración se MIDE del audio real, no se asume: cambiar
   de motor de voz cambia los tiempos y el video se acomoda solo.
4. Mezcla y exporta.

Por qué la narración va solo en castellano
------------------------------------------
Misma decisión que el video del Copiloto, y por el mismo motivo que explica
`subtitulos.py`: la interfaz que se ve DENTRO del video está en castellano.
Una voz en inglés sobre pantallas en español confunde más de lo que ayuda. Los
tres idiomas viajan por los subtítulos, que es el estándar y además suma
accesibilidad.

Los dos motores de voz
----------------------
`elevenlabs` — la voz del producto, la misma de las llamadas reales y del
video del Copiloto. Requiere `ELEVENLABS_API_KEY` y cuesta por carácter. **Es
la que hay que usar para publicar**: que el video de la suite hable con otra
voz que el resto del material es una inconsistencia que se nota.

`piper` — sintetizador offline (MIT), voz `es_MX-claude-high` (Apache-2.0,
latinoamericana). No necesita clave ni conexión ni gasta un peso. Sirve para
armar el corte y revisar tiempos sin quemar créditos; la licencia permite uso
comercial, pero la voz no es la del producto.

Se elige solo: si hay `ELEVENLABS_API_KEY`, usa esa; si no, cae a piper.

Uso:
    python3 -m marketing.audio_suite                 # elige motor solo
    python3 -m marketing.audio_suite --motor piper   # forzar uno
    python3 -m marketing.audio_suite --salida /tmp/prueba.webm
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import wave

from marketing.subtitulos import ROOT, SUITE_CUES

VIDEO_DIR = os.path.join(ROOT, "landing", "video")
ENTRADA = os.path.join(VIDEO_DIR, "MVKobraAI_Suite_Demo.webm")
SALIDA = ENTRADA  # se reemplaza en el lugar

# Voz de piper: Apache-2.0 (permisiva, sin copyleft que contamine el video).
# `es_AR-daniela-high` suena más rioplatense pero es CC BY-SA 4.0, y el
# "ShareAlike" sobre una pieza comercial es una discusión que no vale la pena
# tener por una voz de respaldo.
PIPER_VOZ = "es_MX-claude-high"
PIPER_DIR = os.environ.get("PIPER_VOICES_DIR",
                           os.path.join(tempfile.gettempdir(), "piper_voices"))

# Aire después de la última palabra: cortar en seco el video apenas termina la
# voz se siente abrupto.
COLA_S = 0.6


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _correr(args: list[str]) -> None:
    subprocess.run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True)


def duracion(ruta: str) -> float:
    """Duración en segundos de un archivo de audio o video, según ffmpeg."""
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-i", ruta],
                       capture_output=True, text=True)
    for linea in r.stderr.splitlines():
        if "Duration:" in linea:
            reloj = linea.split("Duration:")[1].split(",")[0].strip()
            h, m, s = reloj.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"ffmpeg no informó duración de {ruta}")


# --------------------------------------------------------------------------
#  Motores de voz
# --------------------------------------------------------------------------
def motor_disponible() -> str:
    """`elevenlabs` si hay clave configurada, si no `piper`."""
    from kobra import voz_tts
    return "elevenlabs" if voz_tts.api_key_configurada() else "piper"


def _wav_elevenlabs(texto: str) -> bytes:
    from kobra import voz_tts
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID_GESTOR")
    if not voice_id:
        raise RuntimeError(
            "falta ELEVENLABS_VOICE_ID_GESTOR: sin la voz elegida no se puede "
            "narrar con la voz del producto (ver kobra/voz_tts.py)")
    res = voz_tts.sintetizar(texto, voice_id=voice_id)
    if not res.get("ok"):
        raise RuntimeError(f"ElevenLabs falló: {res.get('error')}")
    return res["audio"]


_PIPER_CACHE: dict[str, object] = {}


def _wav_piper(texto: str) -> bytes:
    from piper import PiperVoice
    if "voz" not in _PIPER_CACHE:
        modelo = os.path.join(PIPER_DIR, f"{PIPER_VOZ}.onnx")
        if not os.path.exists(modelo):
            raise RuntimeError(
                f"falta el modelo de voz {modelo}.\n"
                f"Bajalo con:  python3 -m piper.download_voices {PIPER_VOZ} "
                f"--data-dir {PIPER_DIR}")
        _PIPER_CACHE["voz"] = PiperVoice.load(modelo)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        _PIPER_CACHE["voz"].synthesize_wav(texto, w)
    return buf.getvalue()


def sintetizar_cue(texto: str, motor: str) -> bytes:
    """Un cue → bytes de audio. El salto de línea del subtítulo es corte
    visual, no una pausa: se lee de corrido."""
    texto = texto.replace("\n", " ").strip()
    return _wav_elevenlabs(texto) if motor == "elevenlabs" else _wav_piper(texto)


# --------------------------------------------------------------------------
#  Montaje
# --------------------------------------------------------------------------
def construir(salida: str = SALIDA, motor: str | None = None,
              entrada: str = ENTRADA, idioma: str = "es") -> dict:
    """Monta la narración sobre el screencast. Devuelve un informe."""
    motor = motor or motor_disponible()
    if motor not in ("elevenlabs", "piper"):
        raise ValueError(f"motor desconocido: {motor!r}")
    if not os.path.exists(entrada):
        raise FileNotFoundError(
            f"falta el screencast {entrada} — generalo con "
            "`python3 -m marketing.screencast_suite`")

    dur_video = duracion(entrada)
    tmp = tempfile.mkdtemp(prefix="audio_suite_")
    pistas, avisos, fin_audio = [], [], 0.0

    for n, (ini, _fin, textos) in enumerate(SUITE_CUES):
        ruta = os.path.join(tmp, f"cue_{n:02d}.wav")
        with open(ruta, "wb") as f:
            f.write(sintetizar_cue(textos[idioma], motor))
        d = duracion(ruta)
        pistas.append((ruta, ini))
        fin_audio = max(fin_audio, ini + d)

        # Un cue que se pasa de su ventana pisa el subtítulo siguiente. Medio
        # segundo de solape es normal en locución; más que eso se avisa.
        sobra = (ini + d) - _fin
        if sobra > 0.5:
            avisos.append(
                f"cue {n}: la voz dura {d:.1f}s y su subtítulo cierra a los "
                f"{_fin:.1f}s ({sobra:.1f}s de más)")

    dur_final = max(dur_video, fin_audio + COLA_S)
    congelar = dur_final - dur_video

    # Cada cue arranca en su segundo (adelay) y todos se suman sin normalizar
    # —no se pisan entre sí, así que normalizar solo bajaría el volumen.
    entradas: list[str] = []
    filtros: list[str] = []
    for i, (ruta, ini) in enumerate(pistas):
        entradas += ["-i", ruta]
        ms = int(round(ini * 1000))
        filtros.append(f"[{i + 1}:a]adelay={ms}|{ms},aresample=44100[a{i}]")
    mezcla = "".join(f"[a{i}]" for i in range(len(pistas)))
    # `normalize=0` porque los cues no se pisan: normalizar solo bajaría el
    # volumen a la mitad sin necesidad.
    #
    # Y después `loudnorm`, que no es cosmético: sin él la mezcla salía con
    # picos clavados en 0 dBFS (486 muestras al tope, medido con volumedetect)
    # — o sea recortando, que es el chasquido áspero que se escucha en las
    # eses. Se normaliza al estándar de locución (EBU R128, -16 LUFS con techo
    # en -1,5 dBTP), que además deja el volumen parejo con el video del
    # Copiloto en vez de que uno suene el doble que el otro.
    filtros.append(f"{mezcla}amix=inputs={len(pistas)}:normalize=0,"
                   "loudnorm=I=-16:TP=-1.5:LRA=11[voz]")

    # `tpad` clona el último cuadro: el cierre necesita pantalla sobre la cual
    # sonar. Si el video ya alcanza, `congelar` es 0 y tpad no hace nada.
    filtros.append(
        f"[0:v]tpad=stop_mode=clone:stop_duration={max(congelar, 0):.3f}[v]")

    _correr([*["-i", entrada], *entradas,
             "-filter_complex", ";".join(filtros),
             "-map", "[v]", "-map", "[voz]",
             "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", "-row-mt", "1",
             "-c:a", "libopus", "-b:a", "96k",
             "-t", f"{dur_final:.3f}", salida])

    return {
        "salida": salida, "motor": motor, "voz": PIPER_VOZ if motor == "piper" else "elevenlabs",
        "duracion_video_original": round(dur_video, 2),
        "duracion_final": round(duracion(salida), 2),
        "congelado_s": round(max(congelar, 0), 2),
        "cues": len(pistas), "avisos": avisos,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--motor", choices=("elevenlabs", "piper"), default=None)
    p.add_argument("--salida", default=SALIDA)
    p.add_argument("--entrada", default=ENTRADA)
    a = p.parse_args(argv)

    inf = construir(salida=a.salida, motor=a.motor, entrada=a.entrada)
    print(f"[OK] {inf['salida']}")
    print(f"     motor={inf['motor']} voz={inf['voz']} cues={inf['cues']}")
    print(f"     video {inf['duracion_video_original']}s -> "
          f"{inf['duracion_final']}s (congelado {inf['congelado_s']}s)")
    for av in inf["avisos"]:
        print(f"     [aviso] {av}")
    if inf["motor"] == "piper":
        print("     OJO: voz de respaldo, NO la del producto. Para publicar, "
              "corré con ELEVENLABS_API_KEY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
