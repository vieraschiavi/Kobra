# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Pre-renderizar la voz del chatvoice de la demo offline
=====================================================================
El demo offline (`dashboard_estatico/index.html`) reproducía la llamada con
el Web Speech API del navegador (sin backend, sin costo) — pero esa voz es la
del sistema operativo de cada prospecto: suena robótica y arranca con latencia
(carga asíncrona de voces, motor de síntesis en vivo). No es la voz premium
que se ve en el video de marketing ni la que el producto ofrece en producción
(ElevenLabs, `kobra/voz_tts.py` — la misma que usan las llamadas reales).

Este script sintetiza el guion de la demo UNA sola vez con ese mismo motor
premium y deja los MP3 listos en `dashboard_estatico/audio_demo/`, con un
manifest.js que el HTML consume. Así el chatvoice offline suena a la voz real
del producto — sin latencia (es un archivo, no síntesis en vivo) y sin costo
recurrente (se renderiza una vez, se distribuye muchas).

Requiere ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID_GESTOR (variables de
entorno). Si no están configuradas, no hace nada — el demo sigue funcionando
con el fallback de voz del navegador (comportamiento actual, no rompe nada).

Uso:
    ELEVENLABS_API_KEY=... ELEVENLABS_VOICE_ID_GESTOR=... \\
        python data/generar_audio_demo_voz.py
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD = os.path.join(ROOT, "dashboard_estatico")
AUDIO_DIR = os.path.join(DASHBOARD, "audio_demo")


IDIOMAS = ("es", "pt", "en")


def leer_guiones(ruta: str | None = None) -> dict:
    """Carga `dashboard_estatico/guiones.js` completo, con los tres idiomas.

    Es la misma fuente que consume el navegador: lo que se ve escrito en
    pantalla es exactamente lo que se sintetiza en audio, y no hay forma de que
    se desincronicen."""
    ruta = ruta or os.path.join(DASHBOARD, "guiones.js")
    with open(ruta, encoding="utf-8") as f:
        js = f.read()
    # Anclado a principio de línea a propósito: el encabezado del archivo
    # menciona el patrón `window.GUIONES = {...};` dentro de un comentario, y
    # sin ancla la búsqueda lo engancha a él en vez de a la asignación real.
    m = re.search(r"^window\.GUIONES\s*=\s*(\{.*?^\});", js, re.S | re.M)
    if not m:
        raise ValueError(f"No encontré window.GUIONES en {ruta}")
    return json.loads(m.group(1))


def leer_guion(idioma: str = "es", ruta: str | None = None) -> list[dict]:
    """Los turnos de la llamada en un idioma."""
    guiones = leer_guiones(ruta)
    if idioma not in guiones:
        raise ValueError(f"Idioma sin guion: {idioma!r} "
                         f"(hay {', '.join(sorted(guiones))})")
    return guiones[idioma]["llamada"]


def elegir_motor(api_key: str | None = None, voice_id_gestor: str | None = None,
                 forzar: str | None = None):
    """Decide con qué motor sintetizar. Prioridad:

      1. `forzar` / KOBRA_TTS_MOTOR ('local' | 'elevenlabs'), si se pide explícito.
      2. Clonado LOCAL si hay un motor instalado — es gratis y no manda datos afuera.
      3. ElevenLabs si hay API key y voice_id.

    Devuelve (modulo, nombre, detalle) o (None, '', motivo) si no hay ninguno.
    """
    from kobra import voz_clon_local as klocal
    from kobra import voz_tts as ktts

    forzar = (forzar or os.getenv("KOBRA_TTS_MOTOR", "")).strip().lower()
    local = klocal.motor_disponible()
    key = ktts.api_key_configurada(api_key)
    vid = voice_id_gestor or os.getenv("ELEVENLABS_VOICE_ID_GESTOR", "")

    if forzar == "local":
        # Pedido explícito de motor gratuito: si no está, se avisa y no se
        # genera. Caer a ElevenLabs acá le costaría plata a alguien que pidió
        # justamente lo contrario.
        if local:
            return klocal, "local", f"clonado local · {local} · sin costo"
        return None, "", ("Se pidió el clonador LOCAL pero no hay ninguno instalado "
                          "(pip install chatterbox-tts). No se usa ElevenLabs porque "
                          "tiene costo y no fue lo que se pidió.")
    if forzar == "elevenlabs":
        if key and vid:
            return ktts, "elevenlabs", "ElevenLabs (con costo por carácter)"
        return None, "", "Se pidió ElevenLabs pero falta ELEVENLABS_API_KEY o el voice_id."
    # Sin preferencia explícita: primero lo gratuito, después lo pago.
    if local:
        return klocal, "local", f"clonado local · {local} · sin costo"
    if key and vid:
        return ktts, "elevenlabs", "ElevenLabs (con costo por carácter)"
    return None, "", ("No hay motor de voz disponible: instalá el clonador local "
                      "(pip install chatterbox-tts) o configurá ELEVENLABS_API_KEY "
                      "+ ELEVENLABS_VOICE_ID_GESTOR.")


def generar(voice_id_gestor: str | None = None, voice_id_cliente: str | None = None,
           api_key: str | None = None, out_dir: str | None = None,
           referencia: str | None = None, motor: str | None = None,
           idioma: str = "es", referencia_cliente: str | None = None) -> dict:
    """Sintetiza cada turno del guion con la voz del video y guarda los MP3 +
    manifest.js en `out_dir` (default: dashboard_estatico/audio_demo).

    Usa el clonador LOCAL si está instalado (gratis, sin mandar datos afuera) y
    cae a ElevenLabs si no. `referencia` es el clip de voz a imitar por el
    GESTOR; por defecto la locución del video oficial. `referencia_cliente` es
    la del CLIENTE; por defecto una versión grave de la misma muestra, porque
    el cliente del guion es varón ("Juan Pérez") y la locución oficial es de
    mujer. Devuelve {generados, omitidos, costo_est_usd, motor}. Si no hay
    ningún motor, no genera nada y el demo sigue con la voz del navegador —
    nunca rompe el build."""
    mod, nombre_motor, detalle = elegir_motor(api_key, voice_id_gestor, motor)
    if mod is None:
        return {"generados": 0, "omitidos": 0, "costo_est_usd": 0.0,
                "motor": "", "motivo": detalle}

    from kobra import voz_tts as ktts
    api_key = ktts.api_key_configurada(api_key)
    voice_id_gestor = voice_id_gestor or os.getenv("ELEVENLABS_VOICE_ID_GESTOR", "")
    voice_id_cliente = voice_id_cliente or os.getenv("ELEVENLABS_VOICE_ID_CLIENTE", "") or voice_id_gestor
    # Cada idioma en su carpeta: los MP3 se llaman igual y se pisarían.
    out_dir = out_dir or os.path.join(AUDIO_DIR, idioma)

    turnos = leer_guion(idioma)
    os.makedirs(out_dir, exist_ok=True)
    manifest, costo_total, generados, omitidos = [], 0.0, 0, 0
    for i, turno in enumerate(turnos):
        voice_id = voice_id_gestor if turno["who"] == "ia" else voice_id_cliente
        if nombre_motor == "local":
            # El GESTOR habla con la voz clonada del video (es la voz de la
            # marca); el CLIENTE con una voz masculina distinta. Con la misma
            # voz en ambos roles la llamada suena a una persona hablando sola,
            # y encima "Juan Pérez" quedaba con voz de mujer.
            # El idioma va explícito: con el modelo multilingüe define la
            # pronunciación. Pasarle español a un modelo cargado en inglés
            # produce fonética inglesa sobre texto castellano.
            from kobra import voz_clon_local as _kl
            if turno["who"] == "ia":
                ref_turno = referencia
            else:
                ref_turno = referencia_cliente or _kl.referencia_grave(referencia)
            res = mod.sintetizar(turno["text"], referencia=ref_turno, idioma=idioma)
        else:
            res = mod.sintetizar(turno["text"], voice_id, api_key=api_key,
                                 modelo=ktts.MODELO_LLAMADAS)
        entrada = {"i": i, "who": turno["who"], "archivo": None}
        if res["ok"]:
            nombre = f"turno_{i:02d}.mp3"
            with open(os.path.join(out_dir, nombre), "wb") as f:
                f.write(res["audio"])
            entrada["archivo"] = nombre
            costo_total += res["costo_est_usd"]
            generados += 1
        else:
            omitidos += 1
        manifest.append(entrada)

    return {"generados": generados, "omitidos": omitidos,
            "costo_est_usd": round(costo_total, 4), "idioma": idioma,
            "manifest": manifest,
            "motor": nombre_motor, "detalle_motor": detalle}


def escribir_manifest(por_idioma: dict, destino: str | None = None) -> str:
    """Un único `manifest.js` con los tres idiomas.

    El HTML lo carga con un `<script src>` fijo — no puede pedir uno distinto
    por idioma sin recargar la página, y el demo offline corre sobre file://,
    donde `fetch` está bloqueado. Así que el manifest trae todo y el navegador
    elige la rama que corresponde."""
    destino = destino or AUDIO_DIR
    os.makedirs(destino, exist_ok=True)
    ruta = os.path.join(destino, "manifest.js")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("// Generado por data/generar_audio_demo_voz.py — no editar a mano.\n"
                "window.AUDIO_DEMO_MANIFEST = "
                + json.dumps(por_idioma, ensure_ascii=False) + ";\n")
    return ruta


def generar_todos(idiomas=None, **kw) -> dict:
    """Sintetiza la llamada en cada idioma y escribe un manifest común.

    Elegir portugués o inglés en el sitio no cambiaba el audio: estaba
    pre-renderizado solo en castellano. Ahora hay una tanda por idioma."""
    idiomas = tuple(idiomas or IDIOMAS)
    por_idioma, resumen = {}, {}
    for idioma in idiomas:
        r = generar(idioma=idioma, **kw)
        por_idioma[idioma] = r.get("manifest", [])
        resumen[idioma] = {k: v for k, v in r.items() if k != "manifest"}
    escribir_manifest(por_idioma)
    return resumen


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--idiomas", default=",".join(IDIOMAS),
                    help="idiomas a sintetizar, separados por coma")
    args = ap.parse_args()

    resumen = generar_todos(idiomas=[i.strip() for i in args.idiomas.split(",") if i.strip()])
    total = sum(r["generados"] for r in resumen.values())
    if not total:
        primero = next(iter(resumen.values()), {})
        print(f"[SKIP] {primero.get('motivo', 'nada que generar')}")
    else:
        for idioma, r in resumen.items():
            estado = f"{r['generados']} audio(s)"
            if r["omitidos"]:
                estado += f", {r['omitidos']} omitido(s) → voz del navegador"
            print(f"[{idioma}] {estado}  ({r.get('detalle_motor', '')})")
        costo = sum(r["costo_est_usd"] for r in resumen.values())
        print(f"[OK] {total} audio(s) en dashboard_estatico/audio_demo/ "
              f"(costo est. USD {round(costo, 4)}).")
