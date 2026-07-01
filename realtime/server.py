"""
Kobra · Copiloto en Vivo — backend de audio en tiempo real
==========================================================
Servidor FastAPI + WebSocket que asiste al gestor DURANTE la llamada.

Flujo:
    1. El navegador captura el audio (micrófono / línea telefónica) y lo
       transcribe en vivo:
         - En el navegador con Web Speech API (español, sin API key), o
         - En el servidor con Whisper (POST /transcribe) si hay OPENAI_API_KEY.
    2. Cada turno transcrito ("gestor" / "cliente") se envía por WebSocket.
    3. El servidor corre el motor Copiloto (kobra/copiloto.py) sobre la
       conversación acumulada y devuelve, en milisegundos:
         - sentimiento y emoción del cliente
         - técnicas detectadas del gestor
         - calidad de la gestión
         - sugerencias accionables + próxima frase sugerida
    4. El navegador muestra la asesoría en tiempo real.

Ejecutar:
    python -m realtime.server           # http://localhost:8000
"""
import os
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import base64               # noqa: E402
from kobra import copiloto   # noqa: E402
from kobra import voz        # noqa: E402
from realtime import connectors   # noqa: E402

app = FastAPI(title="Kobra · Copiloto en Vivo")
HERE = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "index.html"))


@app.get("/health")
def health():
    return {"ok": True, "whisper": bool(os.getenv("OPENAI_API_KEY")),
            "claude": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcribe un chunk de audio con Whisper (si hay OPENAI_API_KEY)."""
    tmp = os.path.join("/tmp", audio.filename or "chunk.webm")
    with open(tmp, "wb") as f:
        f.write(await audio.read())
    texto = copiloto.transcribir_audio(tmp)
    try:
        os.remove(tmp)
    except OSError:
        pass
    if texto is None:
        return JSONResponse(
            {"error": "Transcripción no disponible (configurá OPENAI_API_KEY)"},
            status_code=503)
    return {"texto": texto}


@app.post("/analizar_audio")
async def analizar_audio(audio: UploadFile = File(...)):
    """Diarización + emoción acústica de una grabación (.wav)."""
    tmp = os.path.join("/tmp", audio.filename or "call.wav")
    with open(tmp, "wb") as f:
        f.write(await audio.read())
    try:
        return voz.analizar_llamada(tmp)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.get("/copiloto_demo")
def copiloto_demo():
    """Corre el pipeline sobre la grabación demo dual-channel del repo."""
    wav = os.path.join(ROOT, "data", "ejemplo_llamada.wav")
    if not os.path.exists(wav):
        from data.generate_audio_demo import generar
        generar()
    tt = None
    txt_path = os.path.join(ROOT, "data", "ejemplo_whatsapp.txt")
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            conv = copiloto.parsear_conversacion(f.read(), nombre_gestor="Gestor")
        tt = [{"emisor": t.emisor, "texto": t.texto} for t in conv.turnos]
    return voz.copiloto_desde_audio(wav, transcript_turnos=tt)


@app.post("/copiloto_audio")
async def copiloto_audio(audio: UploadFile = File(...), transcript: str = Form("")):
    """
    Ingesta de grabación (Avaya/PBX dual-channel o cualquier .wav):
    diarización + transcripción por hablante (Whisper si hay key, o alineación
    del texto provisto) + emoción acústica + asesoría del copiloto.
    """
    tmp = os.path.join("/tmp", audio.filename or "call.wav")
    with open(tmp, "wb") as f:
        f.write(await audio.read())
    tt = None
    if transcript.strip():
        conv = copiloto.parsear_conversacion(transcript, nombre_gestor="Gestor")
        tt = [{"emisor": t.emisor, "texto": t.texto} for t in conv.turnos]
    try:
        return voz.copiloto_desde_audio(tmp, transcript_turnos=tt)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.websocket("/ws")
async def ws(sock: WebSocket):
    """Recibe turnos y devuelve la asesoría del copiloto en vivo."""
    await sock.accept()
    turnos = []          # líneas "emisor: texto"
    probpago = None
    estrategia = None
    try:
        while True:
            data = await sock.receive_json()
            if data.get("tipo") == "config":
                probpago = data.get("probpago")
                estrategia = data.get("estrategia")
                continue
            if data.get("tipo") == "reset":
                turnos = []
                continue

            emisor = data.get("emisor", "cliente")
            texto = (data.get("texto") or "").strip()
            if not texto:
                continue
            etiqueta = "Gestor" if emisor == "gestor" else "Cliente"
            turnos.append(f"{etiqueta}: {texto}")

            res = copiloto.analizar_conversacion(
                "\n".join(turnos), canal="llamada",
                probpago=probpago, estrategia=estrategia,
                nombre_gestor="Gestor")
            cop = res["copiloto"]
            ult = cop["sentimientos_turnos"][-1] if cop["sentimientos_turnos"] else {}
            await sock.send_json({
                "emisor": emisor,
                "texto": texto,
                "sentimiento_turno": ult.get("score"),
                "clima": cop["clima_emocional"],
                "clima_etiqueta": cop["clima_etiqueta"],
                "emociones_cliente": cop["emociones_cliente"],
                "tecnicas": [k for k, v in res["tecnicas"].items() if v],
                "calidad": res["calidad"]["score_total"],
                "sugerencias": cop["sugerencias"],
                "proxima_frase": cop["proxima_frase"],
            })
    except WebSocketDisconnect:
        return


@app.websocket("/ws_audio")
async def ws_audio(sock: WebSocket):
    """
    Streaming genérico (SIPREC / Avaya DMCC / media server → PCM16).
    Mensajes JSON:
      {"tipo":"start","sr":8000,"probpago":0.7,"estrategia":"..."}
      {"tipo":"media","canal":"gestor|cliente","pcm_b64":"<PCM16 LE base64>","texto":"(opcional)","fin_turno":false}
      {"tipo":"flush","canal":"gestor|cliente","texto":"(opcional)"}
      {"tipo":"stop"}
    Responde, al cerrar cada turno, con la asesoría del copiloto en vivo.
    """
    await sock.accept()
    sess = connectors.StreamSession()
    try:
        while True:
            m = await sock.receive_json()
            t = m.get("tipo")
            if t == "start":
                sess = connectors.StreamSession(
                    sr=int(m.get("sr", 8000)), probpago=m.get("probpago"),
                    estrategia=m.get("estrategia"))
            elif t == "media":
                canal = m.get("canal", "cliente")
                if m.get("pcm_b64"):
                    sess.agregar(canal, connectors.pcm16_to_float(
                        base64.b64decode(m["pcm_b64"])))
                if m.get("fin_turno"):
                    r = sess.cerrar_turno(canal, m.get("texto"))
                    if r:
                        await sock.send_json(r)
            elif t == "flush":
                r = sess.cerrar_turno(m.get("canal", "cliente"), m.get("texto"))
                if r:
                    await sock.send_json(r)
            elif t == "stop":
                await sock.send_json({"tipo": "fin"})
                break
    except WebSocketDisconnect:
        return


@app.websocket("/twilio")
async def twilio_media(sock: WebSocket):
    """
    Twilio Media Streams (μ-law 8 kHz). Protocolo real de Twilio:
      event: connected / start / media / stop
      media.payload = base64 μ-law; media.track = inbound(cliente)/outbound(gestor)
    Cierra el turno de un track cuando el otro empieza a hablar (turn-taking).
    La asesoría se emite por este socket (en producción se enruta a la pantalla
    del gestor vía /ws).
    """
    await sock.accept()
    sess = connectors.StreamSession(sr=8000)
    ultimo = None
    try:
        while True:
            m = await sock.receive_json()
            ev = m.get("event")
            if ev == "media":
                track = m["media"].get("track", "inbound")
                canal = connectors.TWILIO_TRACK.get(track, "cliente")
                sess.agregar(canal, connectors.ulaw_to_float(
                    base64.b64decode(m["media"]["payload"])))
                if ultimo and ultimo != canal:      # cambió quien habla → cerrar turno previo
                    r = sess.cerrar_turno(ultimo)
                    if r:
                        await sock.send_json(r)
                ultimo = canal
            elif ev == "stop":
                if ultimo:
                    r = sess.cerrar_turno(ultimo)
                    if r:
                        await sock.send_json(r)
                break
    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"[Kobra] Copiloto en Vivo → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
