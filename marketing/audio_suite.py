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

# Las dos voces de piper, con su licencia al lado — que es el dato que decide,
# no cómo suenan. Cambiar de voz sin mirar esta columna es el error que
# `tests/test_audio_suite.py` frena.
VOCES = {
    # Rioplatense (dataset argentino, OpenSLR 61), voz femenina. Es la que
    # suena como el mercado del producto.
    #
    # OJO CON LA LICENCIA: CC BY-SA 4.0. Permite uso comercial, pero el
    # "ShareAlike" pretende que lo derivado se publique bajo la misma
    # licencia. Si el audio generado cuenta o no como obra derivada del
    # modelo es discutido y no está saldado. Para una pieza comercial es un
    # riesgo real: elegila a sabiendas.
    "es_AR-daniela-high": {"licencia": "CC BY-SA 4.0", "region": "rioplatense",
                           "copyleft": True, "idioma": "es"},
    # Latinoamericana neutra. Licencia permisiva, sin copyleft: es la opción
    # sin letra chica.
    "es_MX-claude-high": {"licencia": "Apache-2.0", "region": "latam-neutra",
                          "copyleft": False, "idioma": "es"},
    # Portugués de Brasil. Dataset CC0 (OHF Voice): dominio público efectivo,
    # sin atribución ni ShareAlike — la licencia más limpia de las tres. Voz
    # masculina: el catálogo de piper no tiene una femenina en pt_BR con
    # calidad media o alta, y la licencia manda sobre la preferencia de timbre.
    "pt_BR-faber-medium": {"licencia": "CC0", "region": "brasil",
                           "copyleft": False, "idioma": "pt"},
    # Inglés de EE.UU., femenina. Dataset LJ Speech: dominio público (grabado
    # sobre textos de LibriVox, también de dominio público).
    "en_US-ljspeech-high": {"licencia": "dominio público", "region": "us",
                            "copyleft": False, "idioma": "en"},
}

# Qué voz narra cada idioma. La del castellano es la rioplatense elegida a
# sabiendas (ver el aviso de licencia); las otras dos se eligieron por
# licencia limpia entre las disponibles.
VOZ_POR_IDIOMA = {"es": "es_AR-daniela-high", "pt": "pt_BR-faber-medium",
                  "en": "en_US-ljspeech-high"}
PIPER_VOZ = "es_AR-daniela-high"
PIPER_DIR = os.environ.get("PIPER_VOICES_DIR",
                           os.path.join(tempfile.gettempdir(), "piper_voices"))

# Aire después de la última palabra: cortar en seco el video apenas termina la
# voz se siente abrupto.
COLA_S = 0.6

# --- Ritmo -----------------------------------------------------------------
# El ritmo NO se elige de oído, que es justo lo que no se puede hacer desde
# acá: se apunta a una medida.
#
# Una locución explicativa clara va entre 140 y 160 palabras por minuto (por
# debajo se arrastra, por encima el que escucha pierde el hilo mientras además
# mira una pantalla). Medida sobre los cues, la voz rioplatense sale de fábrica
# a ~203 pal/min: no es un problema del sintetizador, habla rápido. A esa
# velocidad la frase termina mucho antes que su pantalla y quedan pozos de
# silencio de hasta 3,4 s — el sube y baja entre atropello y silencio es lo que
# se escucha como narración entrecortada.
#
# Así que se apunta al régimen de locución y se llega ahí MIDIENDO: se
# sintetiza, se cuenta, y se corrige la velocidad hasta caer en el objetivo.
# Sirve para cualquier voz —cada una tiene su velocidad de fábrica— sin
# constantes calibradas a mano para una en particular.
WPM_OBJETIVO = 155
# Tolerancia para cortar la corrección: afinar más no se escucha.
WPM_TOLERANCIA = 0.05
CORRECCIONES_MAX = 3
# Techo duro: la frase nunca puede ocupar más que su ventana, o pisa la
# siguiente pantalla. Manda sobre el objetivo de ritmo.
RELLENO_MAX = 0.97
# Y los topes de velocidad, que evitan el remedio peor que la enfermedad. Solo
# se afloja, nunca se acelera: apurar una frase para que entre suena peor que
# medio segundo de solape.
ESCALA_MIN, ESCALA_MAX = 1.0, 1.6


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


def _wav_piper(texto: str, escala: float | None = None, voz: str | None = None) -> bytes:
    from piper import PiperVoice, SynthesisConfig
    voz = voz or PIPER_VOZ
    if _PIPER_CACHE.get("nombre") != voz:
        modelo = os.path.join(PIPER_DIR, f"{voz}.onnx")
        if not os.path.exists(modelo):
            raise RuntimeError(
                f"falta el modelo de voz {modelo}.\n"
                f"Bajalo con:  python3 -m piper.download_voices {voz} "
                f"--data-dir {PIPER_DIR}")
        _PIPER_CACHE["voz"] = PiperVoice.load(modelo)
        _PIPER_CACHE["nombre"] = voz
    buf = io.BytesIO()
    cfg = SynthesisConfig(length_scale=escala) if escala else None
    with wave.open(buf, "wb") as w:
        _PIPER_CACHE["voz"].synthesize_wav(texto, w, syn_config=cfg)
    return buf.getvalue()


def sintetizar_cue(texto: str, motor: str, escala: float | None = None,
                   voz: str | None = None) -> bytes:
    """Un cue → bytes de audio. El salto de línea del subtítulo es corte
    visual, no una pausa: se lee de corrido."""
    texto = texto.replace("\n", " ").strip()
    if motor == "elevenlabs":
        return _wav_elevenlabs(texto)
    return _wav_piper(texto, escala=escala, voz=voz)


def palabras(texto: str) -> int:
    return len([p for p in texto.replace("\n", " ").split() if p.strip()])


def duracion_objetivo(texto: str, ventana: float) -> float:
    """Cuánto DEBERÍA durar esta frase para sonar a locución, sin pisar la
    pantalla siguiente.

    El ritmo manda, pero la ventana tiene la última palabra: una frase larga
    en una pantalla corta se dice al ritmo que entre, no al ideal.
    """
    n = palabras(texto)
    if n == 0:
        return 0.0
    ideal = n / WPM_OBJETIVO * 60.0
    return min(ideal, ventana * RELLENO_MAX) if ventana > 0 else ideal


def _a_ritmo(texto: str, ventana: float, motor: str, voz: str | None):
    """Sintetiza la frase corrigiendo la velocidad hasta dar con el ritmo.

    Devuelve `(audio, duración, escala)`. Cada pasada mide lo que salió y
    ajusta; se corta al caer dentro de la tolerancia, al agotar los intentos o
    al topear la escala. Converge aunque el sintetizador no responda de forma
    lineal a `length_scale` —y no lo hace: medido, subirla de 1,0 a 1,5 alarga
    un 32%, no un 50%— porque cada intento parte de lo MEDIDO y no de lo
    supuesto.
    """
    audio = sintetizar_cue(texto, motor, voz=voz)
    dur = _dur_wav(audio)
    objetivo = duracion_objetivo(texto, ventana)
    if motor != "piper" or objetivo <= 0 or dur <= 0:
        return audio, dur, 1.0

    escala = 1.0
    for _ in range(CORRECCIONES_MAX):
        if dur >= objetivo or abs(dur - objetivo) / objetivo <= WPM_TOLERANCIA:
            break
        nueva = max(ESCALA_MIN, min(ESCALA_MAX, escala * (objetivo / dur)))
        if abs(nueva - escala) < 0.01:      # ya está en el tope: no insistir
            break
        escala = nueva
        audio = sintetizar_cue(texto, motor, escala=escala, voz=voz)
        dur = _dur_wav(audio)
    return audio, dur, escala


def _dur_wav(crudo: bytes) -> float:
    """Duración de un WAV en memoria, sin escribirlo a disco."""
    try:
        with wave.open(io.BytesIO(crudo)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError):
        return 0.0                          # ElevenLabs devuelve MP3, no WAV


# --------------------------------------------------------------------------
#  Montaje
# --------------------------------------------------------------------------
def construir(salida: str = SALIDA, motor: str | None = None,
              entrada: str = ENTRADA, idioma: str = "es",
              voz: str | None = None, cues=None) -> dict:
    """Monta la narración sobre el screencast. Devuelve un informe.

    `cues` es la lista de (inicio, fin, textos) a narrar — por defecto la de
    la suite; la película (marketing/pelicula_demo.py) pasa la suya. El
    montaje es idéntico: mismo ritmo medido, misma mezcla, mismo estirado.
    """
    cues = SUITE_CUES if cues is None else cues
    motor = motor or motor_disponible()
    if motor not in ("elevenlabs", "piper"):
        raise ValueError(f"motor desconocido: {motor!r}")
    voz = voz or PIPER_VOZ
    if motor == "piper" and voz not in VOCES:
        raise ValueError(f"voz desconocida: {voz!r} (hay {sorted(VOCES)})")
    if not os.path.exists(entrada):
        raise FileNotFoundError(
            f"falta el screencast {entrada} — generalo con "
            "`python3 -m marketing.screencast_suite`")

    dur_video = duracion(entrada)
    tmp = tempfile.mkdtemp(prefix="audio_suite_")
    pistas, avisos, fin_audio = [], [], 0.0
    huecos = []

    ritmos = []
    for n, (ini, _fin, textos) in enumerate(cues):
        ruta = os.path.join(tmp, f"cue_{n:02d}.wav")
        # El ritmo se corrige acá, midiendo. Con ElevenLabs no: re-sintetizar
        # cuesta por carácter y ahí la velocidad se ajusta desde la voz.
        audio, d, _esc = _a_ritmo(textos[idioma], _fin - ini, motor, voz)
        with open(ruta, "wb") as f:
            f.write(audio)
        if d <= 0:                          # motor que no devuelve WAV
            d = duracion(ruta)
        ritmos.append(round(palabras(textos[idioma]) / d * 60, 1) if d else 0.0)

        pistas.append((ruta, ini))
        fin_audio = max(fin_audio, ini + d)
        huecos.append(round((_fin - ini) - d, 2))

        # Un cue que se pasa de su ventana pisa el subtítulo siguiente. Medio
        # segundo de solape es normal en locución; más que eso se avisa.
        sobra = (ini + d) - _fin
        if sobra > 0.5:
            avisos.append(
                f"cue {n}: la voz dura {d:.1f}s y su subtítulo cierra a los "
                f"{_fin:.1f}s ({sobra:.1f}s de más)")

    inf = montar(entrada, salida, pistas, dur_video=dur_video, fin_audio=fin_audio)
    return {
        **inf, "motor": motor,
        "voz": voz if motor == "piper" else "elevenlabs",
        "licencia": VOCES[voz]["licencia"] if motor == "piper" else "-",
        "cues": len(pistas), "avisos": avisos,
        "hueco_max_s": max(huecos) if huecos else 0.0,
        "wpm": ritmos,
        "wpm_promedio": round(sum(ritmos) / len(ritmos), 1) if ritmos else 0.0,
    }


def montar(entrada: str, salida: str, pistas: list[tuple[str, float]],
           dur_video: float | None = None,
           fin_audio: float | None = None) -> dict:
    """Pega las pistas de voz sobre el video, cada una en su segundo.

    Está separado de `construir` porque la película sintetiza y MIDE la
    narración antes de grabar (de ahí salen las duraciones de las escenas) y
    después monta esos MISMOS wav: re-sintetizarlos acá gastaría el doble de
    tiempo y, peor, podría dar un audio apenas distinto del que definió los
    tiempos.
    """
    if dur_video is None:
        dur_video = duracion(entrada)
    if fin_audio is None:
        fin_audio = max((ini + _dur_wav(open(r, "rb").read())
                         for r, ini in pistas), default=0.0)
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
             # `deadline good` + `cpu-used 3`: VP9 en su modo más lento tarda
             # más de diez minutos por película y hay que rendir tres, una por
             # idioma. Medido, esta combinación baja el encode a un tercio con
             # una diferencia de calidad que no se ve en un screencast de
             # interfaz (texto plano sobre fondo liso, sin grano ni cámara).
             "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", "-row-mt", "1",
             "-deadline", "good", "-cpu-used", "3",
             "-c:a", "libopus", "-b:a", "96k",
             "-t", f"{dur_final:.3f}", salida])

    return {
        "salida": salida,
        "duracion_video_original": round(dur_video, 2),
        "duracion_final": round(duracion(salida), 2),
        "congelado_s": round(max(congelar, 0), 2),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--motor", choices=("elevenlabs", "piper"), default=None)
    p.add_argument("--voz", choices=sorted(VOCES), default=None,
                   help="voz de piper (por defecto la rioplatense)")
    p.add_argument("--salida", default=SALIDA)
    p.add_argument("--entrada", default=ENTRADA)
    a = p.parse_args(argv)

    inf = construir(salida=a.salida, motor=a.motor, entrada=a.entrada, voz=a.voz)
    print(f"[OK] {inf['salida']}")
    print(f"     motor={inf['motor']} voz={inf['voz']} cues={inf['cues']}")
    print(f"     video {inf['duracion_video_original']}s -> "
          f"{inf['duracion_final']}s (congelado {inf['congelado_s']}s)")
    print(f"     ritmo {inf['wpm_promedio']} pal/min "
          f"(objetivo {WPM_OBJETIVO}) · silencio máximo "
          f"entre frases {inf['hueco_max_s']}s")
    for av in inf["avisos"]:
        print(f"     [aviso] {av}")
    if inf["motor"] == "piper":
        print("     OJO: voz de respaldo, NO la del producto. Para publicar, "
              "corré con ELEVENLABS_API_KEY.")
        if VOCES[inf["voz"]]["copyleft"]:
            print(f"     OJO LICENCIA: {inf['voz']} es {inf['licencia']} — el "
                  "ShareAlike sobre una pieza comercial es un riesgo real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
