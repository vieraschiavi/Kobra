# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Voz del video de la suite, en los tres idiomas
=============================================================
Sintetiza la narración de `MVKobraAI_Suite_Demo.webm` con la MISMA voz premium
del producto (`kobra/voz_tts.py`, ElevenLabs) — la que usan las llamadas
reales y el chatvoice de la demo. El guion NO vive acá: son los `SUITE_CUES`
de `marketing/subtitulos.py`, así que narración y subtítulos no se pueden
desincronizar.

Por qué esto no corre en CI ni deja MP3 pregrabados por defecto: requiere
`ELEVENLABS_API_KEY`, que no se guarda en el repositorio, y cada renderizado
cuesta plata (ElevenLabs cobra por carácter). Se corre UNA vez, con la clave
del dueño, y los MP3 quedan en `landing/video/voz_suite/<idioma>/` para
mezclarlos sobre el webm con cualquier editor (o servirlos junto al video).

Uso:
    ELEVENLABS_API_KEY=... ELEVENLABS_VOICE_ID_GESTOR=... \\
        python3 -m marketing.voz_suite
"""
from __future__ import annotations

import os
import sys

from marketing.subtitulos import IDIOMAS, ROOT, SUITE_CUES

DESTINO = os.path.join(ROOT, "landing", "video", "voz_suite")


def renderizar() -> int:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID_GESTOR")
    if not api_key or not voice_id:
        print("Faltan ELEVENLABS_API_KEY y/o ELEVENLABS_VOICE_ID_GESTOR: la",
              "voz se renderiza con la clave del dueño, una sola vez. Los",
              "subtítulos y el guion ya están listos",
              "(marketing/subtitulos.py::SUITE_CUES).")
        return 1

    from kobra import voz_tts

    total = 0
    for idioma in IDIOMAS:
        carpeta = os.path.join(DESTINO, idioma)
        os.makedirs(carpeta, exist_ok=True)
        for n, (_ini, _fin, textos) in enumerate(SUITE_CUES):
            ruta = os.path.join(carpeta, f"cue_{n:02d}.mp3")
            # El modelo multilingüe de ElevenLabs detecta el idioma del texto:
            # la misma voz narra los tres, igual que en las llamadas reales.
            res = voz_tts.sintetizar(textos[idioma].replace("\n", " "),
                                     voice_id=voice_id, api_key=api_key)
            if not res.get("ok"):
                print(f"[FALLA] {idioma} cue {n:02d}: {res.get('error')}")
                return 1
            with open(ruta, "wb") as f:
                f.write(res["audio"])
            total += 1
            print(f"[OK] {idioma} cue {n:02d} "
                  f"(US${res.get('costo_est_usd', 0):.4f}) -> "
                  f"{os.path.relpath(ruta, ROOT)}")
    print(f"{total} audios renderizados en {os.path.relpath(DESTINO, ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(renderizar())
