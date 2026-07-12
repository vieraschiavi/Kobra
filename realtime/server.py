"""
MV Kobra AI · Copiloto en Vivo — backend de audio en tiempo real
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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import base64               # noqa: E402
from kobra import copiloto   # noqa: E402
from kobra import voz        # noqa: E402
from kobra import config as kconfig   # noqa: E402
from kobra import registro            # noqa: E402
from kobra import voz_tts             # noqa: E402
from kobra import auditoria as kauditoria   # noqa: E402
from kobra import campana             # noqa: E402
from realtime import connectors   # noqa: E402

kconfig.aplicar()   # carga API keys guardadas al entorno

app = FastAPI(title="MV Kobra AI · Copiloto en Vivo")
HERE = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "index.html"))


@app.get("/mv_icon.png")
def icono():
    return FileResponse(os.path.join(HERE, "mv_icon.png"))


@app.get("/health")
def health():
    return {"ok": True, "whisper": bool(os.getenv("OPENAI_API_KEY")),
            "claude": bool(os.getenv("ANTHROPIC_API_KEY")),
            "idioma": copiloto.idioma_configurado()}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcribe un chunk de audio con Whisper (si hay OPENAI_API_KEY)."""
    tmp = os.path.join("/tmp", audio.filename or "chunk.webm")
    with open(tmp, "wb") as f:
        f.write(await audio.read())
    texto = copiloto.transcribir_audio(tmp, idioma=copiloto.idioma_configurado())
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


@app.get("/brief/{id_deudor}")
def brief_deudor(id_deudor: str):
    """
    Briefing pre-llamada para el screen-pop del CTI (Avaya Workspaces, etc.):
    ProbPago, estrategia, descuento máx., plan, canal, guion y prioridad del
    deudor, calculados por el pipeline. El marcador/CTI lo consulta al asignar
    la llamada y se lo muestra al gestor ANTES de atender.
    """
    b = registro.brief(id_deudor)
    if b is None:
        return JSONResponse(
            {"error": f"Deudor {id_deudor} no encontrado (¿corriste kobra.pipeline?)"},
            status_code=404)
    return b


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
    return voz.copiloto_desde_audio(wav, transcript_turnos=tt, idioma=copiloto.idioma_configurado())


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
        return voz.copiloto_desde_audio(tmp, transcript_turnos=tt, idioma=copiloto.idioma_configurado())
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
                nombre_gestor="Gestor", idioma=copiloto.idioma_configurado())
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


# ---------------------------------------------------------------------------
# Chatbot de WhatsApp con Gestor IA (para quien no quiere hablar por teléfono)
# ---------------------------------------------------------------------------
_SESIONES_WA: dict = {}


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(payload: dict):
    """
    Webhook del chatbot WhatsApp. El proxy del canal (WhatsApp Business
    Cloud API, Twilio WhatsApp, etc. — infraestructura del cliente) postea:

        {"sesion": "<telefono o id único>", "id_deudor": "KB-…", "mensaje": "…"}

    (en el primer mensaje puede omitirse "mensaje" → el Gestor IA saluda).
    Devuelve {"respuesta", "estado", "fin", "campos_erp"}. Al cerrar, la
    gestión queda registrada como canal WhatsApp del gestor IA.
    """
    from kobra.gestor_ia import SesionGestorIA
    sesion_id = str(payload.get("sesion") or payload.get("telefono") or "anon")
    ses = _SESIONES_WA.get(sesion_id)
    if ses is None:
        if not payload.get("id_deudor"):
            return JSONResponse({"error": "falta id_deudor para abrir la sesión"},
                                status_code=400)
        ses = SesionGestorIA(id_deudor=str(payload["id_deudor"]),
                             canal="WhatsApp",
                             gestor_id=str(payload.get("gestor_id", "IA01")))
        _SESIONES_WA[sesion_id] = ses
        r = ses.responder(None)                      # saludo inicial
        if payload.get("mensaje"):
            r = ses.responder(str(payload["mensaje"]))
    else:
        r = ses.responder(str(payload.get("mensaje", "")))
    if r["fin"]:
        gestion = ses.registrar()
        _SESIONES_WA.pop(sesion_id, None)
        return {"respuesta": r["texto"], "estado": r["estado"], "fin": True,
                "campos_erp": r["campos_erp"], "gestion": gestion}
    return {"respuesta": r["texto"], "estado": r["estado"], "fin": False}


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
                # Con id_deudor, el briefing (ProbPago/estrategia) se carga solo
                probpago, estrategia = m.get("probpago"), m.get("estrategia")
                b = registro.brief(m["id_deudor"]) if m.get("id_deudor") else None
                if b:
                    probpago = probpago if probpago is not None else b["probpago"]
                    estrategia = estrategia or b["estrategia"]
                sess = connectors.StreamSession(
                    sr=int(m.get("sr", 8000)), probpago=probpago,
                    estrategia=estrategia, id_deudor=m.get("id_deudor"),
                    gestor_id=m.get("gestor_id", "G01"))
                if b:
                    await sock.send_json({"tipo": "brief", "brief": b})
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
                # Persistir la negociación real → alimenta "Gestores & Evolución"
                fin = sess.resumen_final()
                gestion = None
                if fin and fin.get("id_deudor"):
                    gestion = registro.registrar_gestion(
                        id_deudor=fin["id_deudor"], gestor_id=fin["gestor_id"],
                        canal=m.get("canal", "Llamada"), calidad=fin["calidad"],
                        clima=fin["clima"], emociones=fin["emociones"],
                        tecnicas=fin["tecnicas"], resultado=m.get("resultado"))
                await sock.send_json({"tipo": "fin", "gestion": gestion})
                break
    except WebSocketDisconnect:
        return


# ---------------------------------------------------------------------------
# Llamada de VOZ autónoma con el Gestor IA (TwiML <Say>/<Gather>)
# ---------------------------------------------------------------------------
# El Gestor IA HABLA por teléfono usando el TTS y el reconocimiento de voz en
# español de Twilio — sin componentes locales ni streaming bidireccional.
#   1) Twilio llama al número y pide TwiML a  /voz/entrante
#   2) el bot saluda dentro de un <Gather input="speech">
#   3) Twilio transcribe lo que dice el cliente y lo postea a /voz/turno
#   4) el Gestor IA responde; se repite hasta cerrar (promesa / sin acuerdo)
import html as _html                                    # noqa: E402
import secrets                                          # noqa: E402
from collections import OrderedDict                     # noqa: E402
from urllib.parse import quote                          # noqa: E402
from fastapi import Request                              # noqa: E402
from fastapi.responses import Response, HTMLResponse    # noqa: E402

_SESIONES_VOZ: dict = {}
# Voz por defecto: Polly Lupe (neural, es-US) — la voz latina más natural
# incluida vía Twilio. Sin TWILIO_TTS_VOICE, Twilio usaba su voz estándar
# (robótica y con dejo peninsular), que es lo primero que un cliente
# rioplatense nota mal. OJO: no existe NINGUNA voz Polly rioplatense — el
# acento rioplatense real es la voz premium ElevenLabs (elegirla en
# ⚙️ Configuración). Las voces -Neural tienen un pequeño costo por carácter
# en Twilio (verificar el pricing de <Say> del plan).
# Prioridad: variable de entorno > lo elegido en ⚙️ Configuración > default.
# kconfig.aplicar() solo exporta valores no vacíos, así que "voz estándar"
# (guardada como "") se lee del extra, no del entorno.
_TTS_VOICE = os.getenv("TWILIO_TTS_VOICE",
                       kconfig.leer_extra("TWILIO_TTS_VOICE", "Polly.Lupe-Neural"))
_LANG_TTS = os.getenv("TWILIO_TTS_LANG",
                      kconfig.leer_extra("TWILIO_TTS_LANG", "es-US"))  # debe corresponder a la voz
# Reconocimiento del deudor en es-UY: entiende "vos", "plata", modismos
# locales mejor que es-MX (Twilio soporta los locales es-* de Google STT).
_LANG_ASR = os.getenv("TWILIO_ASR_LANG", "es-UY")

# --- Voz premium opcional (ElevenLabs) ---------------------------------
# Se activa con ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID configurados. Si
# falla o falta cualquiera, cae solo a <Say>/Polly — nunca corta la llamada.
_TTS_PROVIDER = os.getenv("TTS_PROVIDER", "twilio")     # "twilio" | "elevenlabs"
_ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
_AUDIO_CACHE_MAX = 200
_AUDIO_CACHE: "OrderedDict[str, bytes]" = OrderedDict()   # token -> audio mp3
# Frases repetidas (saludos, "no le entendí", despedidas) no se vuelven a
# sintetizar: hash del texto -> token ya cacheado. Ahorra la latencia de
# ElevenLabs Y el costo por carácter en cada frase repetida.
_TTS_TEXT_CACHE: "OrderedDict[str, str]" = OrderedDict()  # md5(voz+texto) -> token


def _cachear_audio(audio: bytes) -> str:
    token = secrets.token_urlsafe(12)
    _AUDIO_CACHE[token] = audio
    while len(_AUDIO_CACHE) > _AUDIO_CACHE_MAX:
        _AUDIO_CACHE.popitem(last=False)   # descarta el más viejo (FIFO)
    return token


def _say(texto: str, request: "Request | None" = None) -> str:
    if _TTS_PROVIDER == "elevenlabs" and _ELEVENLABS_VOICE_ID and request is not None:
        import hashlib
        clave = hashlib.md5(f"{_ELEVENLABS_VOICE_ID}|{texto}".encode()).hexdigest()
        token = _TTS_TEXT_CACHE.get(clave)
        if token and token in _AUDIO_CACHE:
            return f'<Play>{_public_base(request)}/voz/audio/{token}.mp3</Play>'
        # Modelo flash (~75 ms) en vez de multilingual v2 (cientos de ms):
        # es la diferencia entre una conversación fluida y una con "lag".
        r = voz_tts.sintetizar(texto, _ELEVENLABS_VOICE_ID, modelo=voz_tts.MODELO_LLAMADAS)
        if r["ok"]:
            token = _cachear_audio(r["audio"])
            _TTS_TEXT_CACHE[clave] = token
            while len(_TTS_TEXT_CACHE) > _AUDIO_CACHE_MAX:
                _TTS_TEXT_CACHE.popitem(last=False)
            kauditoria.registrar("tts_elevenlabs", {
                "caracteres": r["caracteres"], "costo_est_usd": r["costo_est_usd"]})
            base = _public_base(request)
            return f'<Play>{base}/voz/audio/{token}.mp3</Play>'
        # ElevenLabs falló (sin key, sin crédito, error de red…): sigue con Polly abajo.
    v = f' voice="{_TTS_VOICE}"' if _TTS_VOICE else ""
    return f'<Say{v} language="{_LANG_TTS}">{_html.escape(texto or "", quote=True)}</Say>'


def _gather(action: str, prompt: str, request: "Request | None" = None) -> str:
    return (f'<Gather input="speech" language="{_LANG_ASR}" speechTimeout="auto" '
            f'action="{action}" method="POST">{_say(prompt, request)}</Gather>')


def _twiml(*cuerpo: str) -> Response:
    xml = ('<?xml version="1.0" encoding="UTF-8"?><Response>'
           + "".join(cuerpo) + "</Response>")
    return Response(content=xml, media_type="application/xml")


def _brief_para_voz(id_deudor: str, monto) -> dict:
    """Brief para la llamada: del pipeline si el deudor existe; si no, uno
    armado con el monto que se pasa (perfil medio)."""
    b = registro.brief(id_deudor) if id_deudor else None
    if b:
        return b
    from kobra import negociador
    try:
        monto = float(monto or 0)
    except (TypeError, ValueError):
        monto = 0.0
    est, desc, cuotas = negociador._estrategia(0.5, 60, monto)
    return {"id_deudor": id_deudor or "TEL", "monto_deuda": monto, "probpago": 0.5,
            "estrategia": est, "descuento_recomendado": desc, "plan_cuotas": cuotas,
            "segmento_propension": "Media"}


@app.api_route("/voz/entrante", methods=["GET", "POST"])
async def voz_entrante(request: Request):
    """TwiML inicial: el Gestor IA saluda y abre el <Gather> de voz."""
    from kobra.gestor_ia import SesionGestorIA
    qp = dict(request.query_params)
    form = dict(await request.form()) if request.method == "POST" else {}
    call_sid = form.get("CallSid") or qp.get("CallSid") or qp.get("call") or "sin-sid"
    id_deudor = qp.get("id_deudor", "") or form.get("id_deudor", "")
    gestor = qp.get("gestor", "IA01")
    brief = _brief_para_voz(id_deudor, qp.get("monto"))
    ses = SesionGestorIA(id_deudor=id_deudor or "TEL", canal="Llamada",
                         gestor_id=gestor, brief=brief,
                         usar_claude=bool(os.getenv("ANTHROPIC_API_KEY")))
    _SESIONES_VOZ[call_sid] = ses
    r = ses.responder(None)                              # saludo
    action = f"/voz/turno?call={quote(call_sid)}"
    return _twiml(_gather(action, r["texto"], request),
                  _say("No lo escuché. Lo llamaremos en otro momento. Hasta luego.", request))


@app.post("/voz/turno")
async def voz_turno(request: Request):
    """Cada turno: recibe lo que dijo el cliente (SpeechResult) y responde."""
    form = dict(await request.form())
    call_sid = request.query_params.get("call") or form.get("CallSid") or "sin-sid"
    ses = _SESIONES_VOZ.get(call_sid)
    if ses is None:
        return _twiml(_say("Disculpe, se interrumpió la comunicación. Hasta luego.", request))
    speech = (form.get("SpeechResult") or "").strip()
    r = ses.responder(speech)
    if r["fin"]:
        try:
            ses.registrar()                              # persiste la gestión real
        except Exception:
            pass
        _SESIONES_VOZ.pop(call_sid, None)
        return _twiml(_say(r["texto"], request))
    action = f"/voz/turno?call={quote(call_sid)}"
    return _twiml(_gather(action, r["texto"], request),
                  _say("Si sigue en línea, dígame. Si no, hasta luego.", request))


def _public_base(request: Request) -> str:
    env = os.getenv("PUBLIC_BASE_URL")
    if env:
        return env.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme or "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


@app.get("/voz/audio/{token}.mp3")
def voz_audio(token: str):
    """Sirve el audio de ElevenLabs generado para un turno de `<Play>`."""
    audio = _AUDIO_CACHE.get(token)
    if audio is None:
        raise HTTPException(404, "Audio no encontrado (venció el caché o el token es inválido).")
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/voz/llamar")
async def voz_llamar(request: Request):
    """Dispara una llamada saliente real vía la API de Twilio."""
    form = dict(await request.form())
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = form.get("from") or os.getenv("TWILIO_FROM")
    to = (form.get("telefono") or form.get("to") or "").strip()
    if not (sid and token and from_ and to):
        return JSONResponse(
            {"error": "Faltan credenciales de Twilio (cargalas en Configuración) "
                      "o el número de destino."}, status_code=400)
    base = _public_base(request)
    url = (f"{base}/voz/entrante?id_deudor={quote(form.get('id_deudor', ''))}"
           f"&monto={quote(str(form.get('monto', '')))}&gestor=IA01")
    try:
        import requests
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
            data={"To": to, "From": from_, "Url": url}, auth=(sid, token), timeout=30)
        ok = resp.status_code in (200, 201)
        cuerpo = resp.json() if ok else {}
        return JSONResponse(
            {"ok": ok, "status": resp.status_code, "sid": cuerpo.get("sid"),
             "detalle": None if ok else resp.text[:400]},
            status_code=200 if ok else 400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/llamar")
def pagina_llamar():
    """Página con formulario para disparar una llamada real (sin consola)."""
    return HTMLResponse(_HTML_LLAMAR)


_HTML_LLAMAR = """<!doctype html><html lang=es><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>MV Kobra AI · Llamar</title>
<style>
 body{font-family:Segoe UI,system-ui,sans-serif;background:#0E1117;color:#e9edf5;
   margin:0;padding:32px;display:flex;justify-content:center}
 .card{background:#161c2b;border:1px solid #26304a;border-radius:16px;max-width:460px;
   width:100%;padding:26px 26px 30px;box-shadow:0 8px 30px rgba(0,0,0,.4)}
 h1{font-size:1.25rem;margin:0 0 4px} p.sub{color:#93a0b5;margin:0 0 18px;font-size:.9rem}
 label{display:block;font-size:.8rem;color:#aeb7c7;margin:12px 0 4px}
 input{width:100%;box-sizing:border-box;background:#0f1523;border:1px solid #2b3550;
   border-radius:9px;color:#eef2f8;padding:10px 12px;font-size:.95rem}
 button{margin-top:20px;width:100%;background:#00C896;color:#062018;font-weight:700;
   border:0;border-radius:10px;padding:13px;font-size:1rem;cursor:pointer}
 button:disabled{opacity:.5;cursor:default}
 .out{margin-top:16px;font-size:.9rem;white-space:pre-wrap;padding:12px;border-radius:9px}
 .ok{background:#0d2a20;border:1px solid #1f6d51;color:#7ff0c6}
 .err{background:#2a1414;border:1px solid #7a2b2b;color:#ffb3b3}
 .note{color:#7f8aa0;font-size:.78rem;margin-top:16px;line-height:1.4}
</style>
<div class=card>
 <h1>📞 Llamar con el Gestor IA</h1>
 <p class=sub>El bot llama, negocia y registra la gestión. Requiere Twilio configurado.</p>
 <label>Teléfono a llamar (formato internacional, ej. +59809…)</label>
 <input id=tel placeholder="+59809XXXXXXX">
 <label>Nombre / referencia (opcional)</label>
 <input id=idd placeholder="Wendy">
 <label>Monto de la deuda (UYU)</label>
 <input id=monto type=number placeholder="10000">
 <label>Número emisor Twilio (dejalo vacío para usar el de Configuración)</label>
 <input id=from placeholder="+1XXXXXXXXXX">
 <button id=btn onclick=llamar()>📞 Llamar ahora</button>
 <div id=out></div>
 <p class=note>⚠️ Necesitás consentimiento de la persona. Empezá probando con tu
   propio celular. Cargá Account SID / Auth Token / número Twilio en la pestaña
   Configuración del dashboard. El servidor debe ser accesible desde internet
   (ngrok o despliegue).</p>
</div>
<script>
async function llamar(){
 const b=document.getElementById('btn'),o=document.getElementById('out');
 b.disabled=true;o.className='';o.textContent='Llamando…';
 const d=new FormData();
 d.append('telefono',document.getElementById('tel').value);
 d.append('id_deudor',document.getElementById('idd').value);
 d.append('monto',document.getElementById('monto').value);
 d.append('from',document.getElementById('from').value);
 try{
  const r=await fetch('/voz/llamar',{method:'POST',body:d});
  const j=await r.json();
  if(j.ok){o.className='out ok';o.textContent='✅ Llamada iniciada. SID: '+j.sid;}
  else{o.className='out err';o.textContent='⛔ '+(j.error||j.detalle||('HTTP '+j.status));}
 }catch(e){o.className='out err';o.textContent='⛔ '+e;}
 b.disabled=false;
}
</script></html>"""


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


# ---------------------------------------------------------------------------
# Campaña automática de contacto (opcional, "Automático sin intervención")
# ---------------------------------------------------------------------------
# Corre en segundo plano mientras este servicio esté vivo — activarla exige
# que este proceso quede corriendo 24/7 (Docker/servidor real, no un
# `streamlit run` que solo vive mientras alguien tiene el dashboard abierto).
# Se apaga/enciende sin reiniciar el proceso: revisa CAMPANA_ACTIVA en cada
# corrida. Requiere PUBLIC_BASE_URL (para el callback de Twilio) y el CSV de
# contactos reales del cliente (CAMPANA_CONTACTOS_CSV: id_deudor,telefono,email).
CAMPANA_INTERVALO_MIN = int(os.getenv("CAMPANA_INTERVALO_MIN", "60"))


def _job_campana():
    if not kconfig.leer_extra("CAMPANA_ACTIVA"):
        return
    base_url = os.getenv("PUBLIC_BASE_URL")
    contactos_csv = kconfig.leer_extra("CAMPANA_CONTACTOS_CSV", "")
    if not base_url or not contactos_csv:
        return   # sin URL pública o sin cartera de contactos reales, no hay a dónde llamar/escribir

    gestiones_csv = os.path.join(ROOT, "data", "kobra_gestiones.csv")
    if not os.path.exists(gestiones_csv):
        return
    import pandas as pd
    gestiones = pd.read_csv(gestiones_csv)

    excluir = campana.contactados_hoy_por_campana()
    max_por_corrida = int(kconfig.leer_extra("CAMPANA_MAX_POR_CORRIDA", 50) or 50)
    plan = campana.plan_contacto_hoy(gestiones, max_contactos=max_por_corrida, excluir=excluir)
    if plan.empty:
        return
    telefonos, emails = campana.cargar_contactos(contactos_csv)
    campana.ejecutar_plan(plan, base_url, telefonos, emails)


def _job_informe_semanal():
    """Manda el Informe Ejecutivo en PDF por email (lunes de mañana). Se
    activa desde ⚙️ Configuración de la webapp (INFORME_EMAIL_ACTIVO +
    INFORME_EMAIL_DESTINO); usa el SMTP corporativo ya configurado."""
    if not kconfig.leer_extra("INFORME_EMAIL_ACTIVO"):
        return
    destino = (kconfig.leer_extra("INFORME_EMAIL_DESTINO", "") or "").strip()
    scored_csv = os.path.join(ROOT, "outputs", "kobra_scored.csv")
    if not destino or not os.path.exists(scored_csv):
        return
    import pandas as pd
    from kobra import informe_ejecutivo as kinforme
    from kobra import paises as kpaises_mod
    scored = pd.read_csv(scored_csv)
    gestiones_csv = os.path.join(ROOT, "data", "kobra_gestiones.csv")
    gestiones = pd.read_csv(gestiones_csv) if os.path.exists(gestiones_csv) else None
    pais_json = os.path.join(ROOT, "data", "pais.json")
    codigo = kpaises_mod.PAIS_DEFAULT
    if os.path.exists(pais_json):
        import json as _json
        try:
            with open(pais_json, encoding="utf-8") as f:
                codigo = _json.load(f).get("codigo", codigo)
        except (OSError, ValueError):
            pass
    r = kinforme.enviar_por_email(destino, scored, gestiones,
                                  empresa="principal", codigo_pais=codigo)
    kauditoria.registrar("informe_semanal_enviado" if r["ok"] else "informe_semanal_error",
                        {"destino": destino, "detalle": r["detalle"]})


# Día/hora del envío semanal (default: lunes 08:00 hora del servidor).
INFORME_EMAIL_DIA = os.getenv("INFORME_EMAIL_DIA", "mon")
INFORME_EMAIL_HORA = int(os.getenv("INFORME_EMAIL_HORA", "8"))

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_job_campana, "interval", minutes=CAMPANA_INTERVALO_MIN,
                       id="campana_automatica")
    _scheduler.add_job(_job_informe_semanal, "cron",
                       day_of_week=INFORME_EMAIL_DIA, hour=INFORME_EMAIL_HORA,
                       id="informe_semanal")
    _scheduler.start()
    import atexit
    atexit.register(lambda: _scheduler.shutdown(wait=False))
except ImportError:
    pass   # apscheduler no instalado: la campaña automática queda desactivada, el resto del servicio funciona igual


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"[MV Kobra AI] Copiloto en Vivo → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
