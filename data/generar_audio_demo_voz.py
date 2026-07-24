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


def generar(voice_id_gestor: str | None = None, voice_id_cliente: str | None = None,
           api_key: str | None = None, out_dir: str | None = None) -> dict:
    """Sintetiza cada turno del guion con la voz premium (ElevenLabs) y guarda
    los MP3 + manifest.js en `out_dir` (default: dashboard_estatico/audio_demo).
    Devuelve un resumen {generados, omitidos, costo_est_usd}. Si falta la key
    o el voice_id del gestor, no genera nada (demo sigue con voz de navegador)."""
    from kobra import voz_tts as ktts

    api_key = ktts.api_key_configurada(api_key)
    voice_id_gestor = voice_id_gestor or os.getenv("ELEVENLABS_VOICE_ID_GESTOR", "")
    voice_id_cliente = voice_id_cliente or os.getenv("ELEVENLABS_VOICE_ID_CLIENTE", "") or voice_id_gestor
    out_dir = out_dir or AUDIO_DIR
    if not api_key or not voice_id_gestor:
        return {"generados": 0, "omitidos": 0, "costo_est_usd": 0.0,
                "motivo": "Falta ELEVENLABS_API_KEY o ELEVENLABS_VOICE_ID_GESTOR — "
                         "se omite el pre-render (el demo usa la voz del navegador)."}

    turnos = leer_guion()
    os.makedirs(out_dir, exist_ok=True)
    manifest, costo_total, generados, omitidos = [], 0.0, 0, 0
    for i, turno in enumerate(turnos):
        voice_id = voice_id_gestor if turno["who"] == "ia" else voice_id_cliente
        res = ktts.sintetizar(turno["text"], voice_id, api_key=api_key,
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
            "costo_est_usd": round(costo_total, 4)}


if __name__ == "__main__":
    r = generar()
    if r["generados"]:
        print(f"[OK] {r['generados']} audio(s) premium generados en "
              f"dashboard_estatico/audio_demo/ (costo est. USD {r['costo_est_usd']}).")
        if r["omitidos"]:
            print(f"[AVISO] {r['omitidos']} turno(s) no se pudieron sintetizar "
                  "(fallback a voz del navegador para esos).")
    else:
        print(f"[SKIP] {r.get('motivo', 'nada que generar')}")
