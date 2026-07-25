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


def leer_guion(html_path: str | None = None) -> list[dict]:
    """Extrae el guion CALL_SCRIPT del HTML del demo (fuente única de verdad:
    lo que se ve escrito en pantalla es lo mismo que se sintetiza en audio)."""
    html_path = html_path or os.path.join(DASHBOARD, "index.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"var CALL_SCRIPT\s*=\s*(\[.*?\]);", html, re.S)
    if not m:
        raise ValueError("No encontré CALL_SCRIPT en dashboard_estatico/index.html")
    bruto = m.group(1)
    turnos = []
    for who, text in re.findall(r"\{who:'(\w+)',text:'((?:[^'\\]|\\.)*)'\}", bruto):
        turnos.append({"who": who, "text": text.replace("\\'", "'")})
    return turnos


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
           idioma: str = "es") -> dict:
    """Sintetiza cada turno del guion con la voz del video y guarda los MP3 +
    manifest.js en `out_dir` (default: dashboard_estatico/audio_demo).

    Usa el clonador LOCAL si está instalado (gratis, sin mandar datos afuera) y
    cae a ElevenLabs si no. `referencia` es el clip de voz a imitar; por defecto
    la locución del video oficial. Devuelve {generados, omitidos, costo_est_usd,
    motor}. Si no hay ningún motor, no genera nada y el demo sigue con la voz
    del navegador — nunca rompe el build."""
    mod, nombre_motor, detalle = elegir_motor(api_key, voice_id_gestor, motor)
    if mod is None:
        return {"generados": 0, "omitidos": 0, "costo_est_usd": 0.0,
                "motor": "", "motivo": detalle}

    from kobra import voz_tts as ktts
    api_key = ktts.api_key_configurada(api_key)
    voice_id_gestor = voice_id_gestor or os.getenv("ELEVENLABS_VOICE_ID_GESTOR", "")
    voice_id_cliente = voice_id_cliente or os.getenv("ELEVENLABS_VOICE_ID_CLIENTE", "") or voice_id_gestor
    out_dir = out_dir or AUDIO_DIR

    turnos = leer_guion()
    os.makedirs(out_dir, exist_ok=True)
    manifest, costo_total, generados, omitidos = [], 0.0, 0, 0
    for i, turno in enumerate(turnos):
        voice_id = voice_id_gestor if turno["who"] == "ia" else voice_id_cliente
        if nombre_motor == "local":
            # El GESTOR habla con la voz clonada del video (es la voz de la
            # marca); el CLIENTE con la voz propia del modelo, para que se
            # distingan. Con la misma voz en ambos roles, la llamada suena a
            # una persona hablando sola.
            # El idioma va explícito: con el modelo multilingüe define la
            # pronunciación. Pasarle español a un modelo cargado en inglés
            # produce fonética inglesa sobre texto castellano.
            from kobra import voz_clon_local as _kl
            ref_turno = referencia if turno["who"] == "ia" else _kl.SIN_CLONAR
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

    with open(os.path.join(out_dir, "manifest.js"), "w", encoding="utf-8") as f:
        f.write("// Generado por data/generar_audio_demo_voz.py — no editar a mano.\n"
                "window.AUDIO_DEMO_MANIFEST = " + json.dumps(manifest, ensure_ascii=False) + ";\n")

    return {"generados": generados, "omitidos": omitidos,
            "costo_est_usd": round(costo_total, 4),
            "motor": nombre_motor, "detalle_motor": detalle}


if __name__ == "__main__":
    r = generar()
    if r["generados"]:
        print(f"[{r.get('detalle_motor', '')}]")
        print(f"[OK] {r['generados']} audio(s) premium generados en "
              f"dashboard_estatico/audio_demo/ (costo est. USD {r['costo_est_usd']}).")
        if r["omitidos"]:
            print(f"[AVISO] {r['omitidos']} turno(s) no se pudieron sintetizar "
                  "(fallback a voz del navegador para esos).")
    else:
        print(f"[SKIP] {r.get('motivo', 'nada que generar')}")
