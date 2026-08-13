# © 2026 Martín Viera. Todos los derechos reservados.

"""Genera los cortes para redes sociales a partir de los videos de la landing.

Los videos maestros viven en `landing/video/` y duran ~69 s cada uno — bien
para la web, largos para un feed. Acá se producen las variantes que piden las
redes, sin tocar los maestros:

    MVKobraAI_Demo_Real.mp4      1280x800 horizontal, sin audio
      -> demo_x_linkedin.mp4     1.5x (~46 s), para X/LinkedIn
      -> demo_reels.mp4          1.5x sobre lienzo 1080x1920 con el propio
                                 video desenfocado de fondo, para IG/TikTok
    MVKobraAI_Copiloto_Demo.mp4  1080x1920 vertical, con audio (ya es 9:16)
      -> copiloto_reels.mp4      1.25x con el audio corregido (atempo), ~56 s

Uso:  python3 -m marketing.video_redes [carpeta_salida]
      (por defecto escribe en marketing/social/, que está fuera del deploy)

El binario de ffmpeg sale de `imageio-ffmpeg` (pip), así que no depende de
tener ffmpeg instalado en el sistema.
"""
import os
import subprocess
import sys

from kobra import rutas as krutas

VIDEOS = os.path.join(krutas.ROOT_REPO, "landing", "video")
DEMO = os.path.join(VIDEOS, "MVKobraAI_Demo_Real.mp4")
COPILOTO = os.path.join(VIDEOS, "MVKobraAI_Copiloto_Demo.mp4")

# CRF 23 + preset medium: nítido para pantalla de teléfono, liviano para subir.
CALIDAD = ["-c:v", "libx264", "-crf", "23", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _correr(args):
    subprocess.run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True)


def demo_x_linkedin(salida):
    """El demo real a 1.5x: de 69 s a ~46 s, el rango donde X y LinkedIn
    todavía reproducen completo. Sin audio de origen, no hay atempo que
    cuidar."""
    _correr(["-i", DEMO, "-vf", "setpts=PTS/1.5,fps=30", "-an",
             *CALIDAD, salida])


def demo_reels(salida):
    """El demo real en lienzo vertical 1080x1920: el video centrado y, de
    fondo, él mismo estirado y desenfocado — el tratamiento estándar para
    publicar una captura horizontal en Reels sin barras negras muertas."""
    filtro = (
        "[0:v]setpts=PTS/1.5,fps=30,split=2[fondo][frente];"
        "[fondo]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=28[bg];"
        "[frente]scale=1080:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    _correr(["-i", DEMO, "-filter_complex", filtro, "-an", *CALIDAD, salida])


def copiloto_reels(salida):
    """El copiloto ya es 9:16 con audio: solo se acelera a 1.25x (queda ~56 s,
    bajo el minuto) corrigiendo el tempo del audio para que la voz no cambie
    de tono."""
    _correr(["-i", COPILOTO,
             "-filter_complex", "[0:v]setpts=PTS/1.25[v];[0:a]atempo=1.25[a]",
             "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "128k",
             *CALIDAD, salida])


def main(destino=None):
    destino = destino or os.path.join(krutas.ROOT_REPO, "marketing", "social")
    os.makedirs(destino, exist_ok=True)
    trabajos = [
        (demo_x_linkedin, "demo_x_linkedin.mp4"),
        (demo_reels, "demo_reels.mp4"),
        (copiloto_reels, "copiloto_reels.mp4"),
    ]
    for fn, nombre in trabajos:
        ruta = os.path.join(destino, nombre)
        fn(ruta)
        kb = os.path.getsize(ruta) // 1024
        print(f"[OK] {ruta} ({kb} KB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
