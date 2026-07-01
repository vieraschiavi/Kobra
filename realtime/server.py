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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import copiloto   # noqa: E402
from kobra import voz        # noqa: E402

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"[Kobra] Copiloto en Vivo → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
