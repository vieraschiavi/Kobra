"""
Kobra · Copiloto de Negociación en Vivo
=======================================
Asistente IA para el gestor durante la negociación ONLINE (telefónica o
WhatsApp). Escucha/lee la conversación, analiza el **sentimiento** turno a
turno, detecta **técnicas de negociación**, puntúa la **calidad** de la gestión
y le sugiere al gestor la **próxima jugada** en tiempo real, conectando con la
propensión de pago (ProbPago) del deudor.

Adaptado y generalizado a partir del motor de evaluación de llamadas/WhatsApp
(ver `referencia_R/`), removiendo la marca original y pasando de una evaluación
*post-mortem* a una **asistencia en vivo**.

Funciona 100% offline (léxico de sentimiento en español + heurísticas). Si hay
API keys en el entorno se enriquece automáticamente:
    - OPENAI_API_KEY  → transcripción de audio con Whisper
    - ANTHROPIC_API_KEY → evaluación cualitativa con Claude

Sin nombres de clientes reales. Apto para demo comercial (Uruguay).
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# Léxico de sentimiento y emociones (español rioplatense, contexto cobranzas)
# ---------------------------------------------------------------------------
POS_WORDS = {
    "gracias", "perfecto", "excelente", "bien", "buenísimo", "buenisimo",
    "genial", "acepto", "acepto", "dale", "listo", "ok", "okey", "de acuerdo",
    "acuerdo", "puedo", "quiero", "pago", "pagar", "abonar", "abono",
    "solucion", "solución", "ayuda", "ayudar", "tranquilo", "tranquila",
    "conforme", "contento", "contenta", "agradezco", "dispuesto", "dispuesta",
    "dispongo", "coordinar", "coordinamos", "dinero", "dabuena", "dabuen",
    "dabuenagana", "dabuenaonda", "dabuenafe", "compromiso", "comprometo",
    "dabuenavoluntad", "cuota", "cuotas", "cerramos", "cerrar", "hecho",
}
NEG_WORDS = {
    "no", "nunca", "imposible", "problema", "problemas", "molesto", "molesta",
    "cansado", "cansada", "harto", "harta", "mal", "peor", "pesimo", "pésimo",
    "reclamo", "queja", "enojado", "enojada", "bronca", "estafa", "mentira",
    "mienten", "vergüenza", "verguenza", "amenaza", "abogado", "denuncia",
    "denunciar", "no puedo", "sin plata", "sin dinero", "desocupado",
    "desempleado", "endeudado", "urgente", "grave", "encima", "basta", "dejen",
    "dejenme", "déjenme", "acoso", "hostigamiento", "presion", "presión",
    "cortame", "cortar", "colgar", "cuelgo", "nervioso", "nerviosa",
    "preocupado", "preocupada", "angustia", "angustiado", "difícil", "dificil",
}
# Intensificadores / atenuadores
BOOST = {"muy", "super", "súper", "recontra", "demasiado", "bastante", "tan"}
NEGATORS = {"no", "nunca", "jamas", "jamás", "tampoco", "ni"}

# Señales de emoción (regex) → etiqueta
EMOCIONES = {
    "frustracion": r"\b(harto|harta|cansad|otra vez|siempre lo mismo|ya les dije|basta|hasta cuando)\b",
    "enojo": r"\b(enojad|bronca|indignad|estafa|mentira|verg[uü]enza|amenaz|denunci|abogad|acoso)\b",
    "ansiedad": r"\b(nervios|angustia|preocupad|no s[eé] qu[eé] hacer|desesperad|urgente|ayuda por favor)\b",
    "dificultad_economica": r"\b(sin (plata|dinero|trabajo)|desemplead|desocupad|no me alcanza|no llego|no tengo)\b",
    "satisfaccion": r"\b(gracias|perfecto|excelente|buen[ií]simo|genial|de acuerdo|me sirve|tranquil)\b",
    "intencion_pago": r"\b(quiero pagar|puedo pagar|voy a pagar|c[oó]mo (pago|abono)|acepto|dale|coordinamos|me sirve)\b",
    "objecion": r"\b(pero|el tema es|el problema es|no puedo|es mucho|no me alcanza|m[aá]s adelante|despu[eé]s)\b",
}

# Técnicas de negociación (del gestor) → regex
TECNICAS = {
    "Anclaje": r"\b(el total es|la deuda total|monto total|son \$?\s?\d)",
    "Fraccionamiento": r"\b(cuotas?|en partes|dividir|fraccionar|50%|mitad|una parte)\b",
    "Alternativas": r"\b(opci[oó]n|alternativa|o bien|otra posibilidad|le ofrezco|puede elegir|tambi[eé]n puede)\b",
    "Reciprocidad": r"\b(si (usted|hace|paga).*(yo|le|hacemos|bonific)|a cambio|por su parte)\b",
    "Urgencia": r"\b(hoy|ahora|antes de|v[aá]lid[ao] hasta|por tiempo limitado|vence|[uú]ltimo d[ií]a|solo por hoy)\b",
    "Escasez": r"\b(beneficio [uú]nico|oferta especial|solo (por hoy|esta semana)|no lo vamos a repetir|excepci[oó]n)\b",
    "Validacion": r"\b(entiendo|comprendo|me pongo en su lugar|s[eé] que|imagino que|tiene raz[oó]n)\b",
    "Prueba_social": r"\b(muchos clientes|la mayor[ií]a|otras personas|lo que suelen hacer)\b",
    "Cierre": r"\b(coordinamos|le env[ií]o el (link|qr)|queda acordado|entonces quedamos|confirmamos)\b",
}


def _strip(s: str) -> str:
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return s


# ---------------------------------------------------------------------------
# Parseo de conversaciones (WhatsApp export o transcripción de llamada)
# ---------------------------------------------------------------------------
WA_LINE = re.compile(
    r"^\[?(\d{1,2}/\d{1,2}/\d{2,4}),?\s*(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*-?\s*([^:]{1,40}):\s*(.+)$")
PLAIN_LINE = re.compile(r"^\s*([^:]{1,25}):\s*(.+)$")


@dataclass
class Turno:
    orden: int
    emisor: str          # "gestor" | "cliente"
    nombre: str
    texto: str
    ts: datetime | None = None


@dataclass
class Conversacion:
    turnos: list = field(default_factory=list)
    nombre_gestor: str = "Gestor"
    nombre_cliente: str = "Cliente"
    canal: str = "whatsapp"      # whatsapp | llamada
    tiempo_primera_respuesta_min: float | None = None
    duracion_total_horas: float | None = None

    @property
    def total_mensajes(self):
        return len(self.turnos)


def parsear_conversacion(texto: str, canal: str = "whatsapp",
                         nombre_gestor: str | None = None) -> Conversacion:
    """Parsea un export de WhatsApp o una transcripción con etiquetas de emisor."""
    raw = [l for l in texto.splitlines() if l.strip()]
    parsed = []   # (ts, nombre, mensaje)
    for line in raw:
        m = WA_LINE.match(line.strip())
        if m:
            fecha, hora, nombre, msg = m.groups()
            ts = _parse_ts(fecha, hora)
            parsed.append((ts, nombre.strip(), msg.strip()))
            continue
        m = PLAIN_LINE.match(line.strip())
        if m:
            nombre, msg = m.groups()
            parsed.append((None, nombre.strip(), msg.strip()))
        elif parsed:
            # continuación del mensaje anterior
            ts, nombre, msg = parsed[-1]
            parsed[-1] = (ts, nombre, msg + " " + line.strip())

    if not parsed:
        return Conversacion(canal=canal)

    # Detectar gestor: quien más mensajes envía, o el nombre indicado
    nombres = [p[1] for p in parsed]
    if nombre_gestor is None:
        conteo = {n: nombres.count(n) for n in set(nombres)}
        nombre_gestor = max(conteo, key=conteo.get)
    otros = [n for n in dict.fromkeys(nombres) if n != nombre_gestor]
    nombre_cliente = otros[0] if otros else "Cliente"

    turnos = []
    for i, (ts, nombre, msg) in enumerate(parsed):
        emisor = "gestor" if nombre == nombre_gestor else "cliente"
        turnos.append(Turno(i, emisor, nombre, msg, ts))

    conv = Conversacion(turnos=turnos, nombre_gestor=nombre_gestor,
                        nombre_cliente=nombre_cliente, canal=canal)
    _calcular_tiempos(conv)
    return conv


def _parse_ts(fecha, hora):
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M"):
        try:
            return datetime.strptime(f"{fecha} {hora}", fmt)
        except ValueError:
            continue
    return None


def _calcular_tiempos(conv: Conversacion):
    ts = [t.ts for t in conv.turnos if t.ts]
    if len(ts) >= 2:
        conv.duracion_total_horas = round((max(ts) - min(ts)).total_seconds() / 3600, 2)
    # tiempo primera respuesta del gestor tras el primer mensaje del cliente
    prim_cli = next((t for t in conv.turnos if t.emisor == "cliente" and t.ts), None)
    if prim_cli:
        resp = next((t for t in conv.turnos
                     if t.emisor == "gestor" and t.ts and t.orden > prim_cli.orden), None)
        if resp:
            conv.tiempo_primera_respuesta_min = round(
                (resp.ts - prim_cli.ts).total_seconds() / 60, 1)


# ---------------------------------------------------------------------------
# Análisis de sentimiento (por turno) — texto y, opcionalmente, señal de voz
# ---------------------------------------------------------------------------
@dataclass
class Sentimiento:
    score: float          # -1 (muy negativo) .. +1 (muy positivo)
    etiqueta: str         # "positivo" | "neutro" | "negativo"
    emociones: list = field(default_factory=list)


def analizar_sentimiento(texto: str, voz: dict | None = None) -> Sentimiento:
    """
    Sentimiento léxico en español con manejo de negación e intensificadores.
    `voz` (opcional): features acústicas normalizadas para negociación
    telefónica en vivo, p. ej. {"energia":0-1, "pitch_var":0-1, "ritmo":0-1}.
    En producción provienen de un modelo de speech-emotion; acá se combinan
    si están disponibles.
    """
    tokens = _strip(texto).split()
    score = 0.0
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        val = 0
        if tok in {_strip(w) for w in POS_WORDS}:
            val = 1
        elif tok in {_strip(w) for w in NEG_WORDS}:
            val = -1
        if val != 0:
            # intensificador previo
            if i > 0 and tokens[i - 1] in {_strip(w) for w in BOOST}:
                val *= 1.6
            # negación en ventana de 2 palabras previas
            if any(tokens[j] in {_strip(w) for w in NEGATORS}
                   for j in range(max(0, i - 2), i)):
                val *= -0.8
            score += val
        i += 1

    n = max(len(tokens), 1)
    norm = max(-1.0, min(1.0, score / (n ** 0.5)))

    # Combinar con señal de voz si existe (energía alta + variabilidad de pitch
    # suelen indicar tensión/negatividad en contexto de cobranza)
    if voz:
        tension = (voz.get("energia", 0.5) * 0.5 + voz.get("pitch_var", 0.5) * 0.5)
        norm = max(-1.0, min(1.0, norm - (tension - 0.5) * 0.6))

    etiqueta = "positivo" if norm > 0.15 else "negativo" if norm < -0.15 else "neutro"
    emo = [e for e, pat in EMOCIONES.items() if re.search(pat, _strip(texto))]
    return Sentimiento(round(norm, 3), etiqueta, emo)


# ---------------------------------------------------------------------------
# Detección de técnicas de negociación (del gestor)
# ---------------------------------------------------------------------------
def detectar_tecnicas(conv: Conversacion) -> dict:
    texto_gestor = " ".join(_strip(t.texto) for t in conv.turnos if t.emisor == "gestor")
    return {nombre: bool(re.search(pat, texto_gestor)) for nombre, pat in TECNICAS.items()}


# ---------------------------------------------------------------------------
# Scoring de calidad (heurístico, 16 criterios) — funciona sin LLM
# ---------------------------------------------------------------------------
CRITERIOS = [
    ("saludo_inicial", "Saludo Inicial", 5),
    ("identificacion", "Identificación", 5),
    ("validacion_datos", "Validación Datos", 10),
    ("empatia", "Empatía", 15),
    ("claridad", "Claridad", 10),
    ("solucion", "Solución", 15),
    ("objeciones", "Manejo Objeciones", 15),
    ("cierre", "Cierre", 15),
    ("registro", "Registro", 10),
]


def _busca(txt, pat):
    return bool(re.search(pat, txt))


def evaluar_calidad(conv: Conversacion) -> dict:
    g = [t.texto for t in conv.turnos if t.emisor == "gestor"]
    gtxt = _strip(" ".join(g))
    prim = _strip(g[0]) if g else ""

    checks = {
        "saludo_inicial": _busca(prim, r"\b(hola|buenos d[ií]as|buenas tardes|buen d[ií]a)\b"),
        "identificacion": _busca(gtxt, r"\b(soy|le habla|mi nombre|de parte de|del [aá]rea)\b"),
        "validacion_datos": _busca(gtxt, r"\b(confirm|verific|es usted|hablo con|su documento|sus datos)\b"),
        "empatia": _busca(gtxt, r"\b(entiendo|comprendo|me pongo en su lugar|tranquil|s[eé] que)\b"),
        "claridad": len(gtxt) > 0 and (sum(len(x) for x in g) / max(len(g), 1)) < 320,
        "solucion": _busca(gtxt, r"\b(le ofrezco|opci[oó]n|alternativa|plan|cuotas?|descuento|facilidad)\b"),
        "objeciones": _busca(gtxt, r"\b(entiendo (pero|que)|de todas formas|le propongo|podemos|qu[eé] le parece)\b"),
        "cierre": _busca(gtxt, r"\b(coordinamos|le env[ií]o|queda acordado|confirmamos|entonces quedamos|link|qr)\b"),
        "registro": _busca(gtxt, r"\b(le env[ií]o (el|un) (comprobante|resumen|detalle)|por escrito|le llega|confirmaci[oó]n)\b"),
    }
    detalle = {}
    total = 0.0
    for cid, nombre, peso in CRITERIOS:
        cumple = checks.get(cid, False)
        sc = 100 if cumple else 35
        total += sc * peso / 100
        detalle[cid] = {"nombre": nombre, "peso": peso, "score": sc, "cumple": cumple}
    total = total / sum(p for _, _, p in CRITERIOS) * 100
    return {"score_total": round(total, 1), "criterios": detalle}


# ---------------------------------------------------------------------------
# Copiloto en vivo: sugerencias para el gestor
# ---------------------------------------------------------------------------
def _clima(sentts):
    if not sentts:
        return 0.0
    # pondera más los turnos recientes
    w = [i + 1 for i in range(len(sentts))]
    return sum(s * wi for s, wi in zip(sentts, w)) / sum(w)


def sugerencias_en_vivo(conv: Conversacion, probpago: float | None = None,
                        estrategia: str | None = None) -> dict:
    """
    Analiza el estado actual de la negociación y devuelve recomendaciones
    accionables para el gestor, más el clima emocional y la próxima jugada.
    """
    sents = [analizar_sentimiento(t.texto) for t in conv.turnos]
    cli_idx = [i for i, t in enumerate(conv.turnos) if t.emisor == "cliente"]
    cli_sents = [sents[i].score for i in cli_idx]
    clima = _clima(cli_sents)
    ultima = conv.turnos[-1] if conv.turnos else None
    ult_sent = sents[-1] if sents else None

    emociones_cli = set()
    for i in cli_idx:
        emociones_cli.update(sents[i].emociones)

    tips = []
    # Reglas basadas en emoción del cliente
    if "enojo" in emociones_cli:
        tips.append(("🔴 Cliente enojado", "Bajá el ritmo, validá su malestar ANTES de ofrecer. "
                     "Evitá justificar; usá 'entiendo su molestia, resolvámoslo juntos'."))
    if "frustracion" in emociones_cli:
        tips.append(("🟠 Frustración", "Reconocé el historial: 'sé que ya hablamos otras veces'. "
                     "Ofrecé algo concreto y distinto a lo anterior."))
    if "ansiedad" in emociones_cli:
        tips.append(("🟠 Ansiedad", "Transmití calma y control. Dá pasos claros y cortos: "
                     "'hagamos una sola cosa hoy'."))
    if "dificultad_economica" in emociones_cli:
        tips.append(("💸 Dificultad económica", "Priorizá plan de cuotas o quita; no presiones el pago total. "
                     "Preguntá cuánto puede afrontar hoy."))
    if "intencion_pago" in emociones_cli or clima > 0.2:
        tips.append(("🟢 Señal de compra", "El clima es favorable: CERRÁ ahora con fecha y medio de pago. "
                     "Enviá el link/QR de inmediato."))
    if "objecion" in emociones_cli and clima <= 0.2:
        tips.append(("🟡 Objeción activa", "No rebatas de frente: '¿qué parte le complica?' y "
                     "ofrecé 2 alternativas para que elija."))

    # Ligar con ProbPago / estrategia recomendada
    if probpago is not None:
        if probpago >= 0.65:
            tips.append(("📈 Alta propensión", "Deudor con alta probabilidad de pago: apuntá a pago total o "
                         "cuota inicial fuerte; poca o nula quita."))
        elif probpago < 0.35:
            tips.append(("📉 Baja propensión", "Propensión baja: prioridad es asegurar CUALQUIER pago. "
                         "Habilitá quita/plan largo y compromiso escrito."))
    if estrategia:
        tips.append(("🎯 Estrategia sugerida", f"Guion recomendado por Kobra: «{estrategia}»."))

    # Próxima frase sugerida
    if clima > 0.2 or "intencion_pago" in emociones_cli:
        next_line = "Perfecto, coordinemos: le envío ahora el link de pago y le llega el comprobante. ¿Le queda cómodo?"
    elif emociones_cli & {"enojo", "frustracion"}:
        next_line = "Entiendo su molestia y quiero resolverlo hoy mismo. Le propongo una opción hecha a su medida, ¿la vemos?"
    elif "dificultad_economica" in emociones_cli:
        next_line = "Sin problema, busquemos algo acorde a su situación. ¿Cuánto podría afrontar este mes?"
    else:
        next_line = "¿Qué le parece si lo dividimos en cuotas cómodas y arrancamos con una hoy?"

    if not tips:
        tips.append(("🟢 Todo en orden", "Mantené el tono y avanzá hacia el cierre con una propuesta concreta."))

    return {
        "clima_emocional": round(clima, 3),
        "clima_etiqueta": ("positivo" if clima > 0.15 else "negativo" if clima < -0.15 else "neutro"),
        "emociones_cliente": sorted(emociones_cli),
        "ultimo_emisor": ultima.emisor if ultima else None,
        "ultimo_sentimiento": (ult_sent.etiqueta if ult_sent else None),
        "sugerencias": tips,
        "proxima_frase": next_line,
        "sentimientos_turnos": [
            {"orden": t.orden, "emisor": t.emisor, "texto": t.texto,
             "score": s.score, "etiqueta": s.etiqueta, "emociones": s.emociones}
            for t, s in zip(conv.turnos, sents)
        ],
    }


def analizar_conversacion(texto: str, canal: str = "whatsapp",
                          probpago: float | None = None,
                          estrategia: str | None = None,
                          nombre_gestor: str | None = None) -> dict:
    """Pipeline completo del copiloto sobre una conversación (texto/transcripción)."""
    conv = parsear_conversacion(texto, canal, nombre_gestor)
    calidad = evaluar_calidad(conv)
    tecnicas = detectar_tecnicas(conv)
    vivo = sugerencias_en_vivo(conv, probpago, estrategia)
    return {
        "meta": {
            "gestor": conv.nombre_gestor, "cliente": conv.nombre_cliente,
            "canal": conv.canal, "mensajes": conv.total_mensajes,
            "tiempo_primera_respuesta_min": conv.tiempo_primera_respuesta_min,
            "duracion_total_horas": conv.duracion_total_horas,
        },
        "calidad": calidad,
        "tecnicas": tecnicas,
        "copiloto": vivo,
    }


# ---------------------------------------------------------------------------
# Enriquecimiento opcional con APIs (Whisper / Claude) — solo si hay keys
# ---------------------------------------------------------------------------
def transcribir_audio(audio_path: str) -> str | None:
    """Transcribe audio con Whisper si OPENAI_API_KEY está disponible."""
    key = os.getenv("OPENAI_API_KEY", "")
    if len(key) < 10:
        return None
    try:
        import requests
        with open(audio_path, "rb") as f:
            r = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": f},
                data={"model": "whisper-1", "language": "es"}, timeout=120)
        r.raise_for_status()
        return r.json().get("text")
    except Exception:
        return None


def evaluar_con_claude(texto_conversacion: str) -> dict | None:
    """Evaluación cualitativa profunda con Claude si ANTHROPIC_API_KEY existe."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if len(key) < 10:
        return None
    prompt = (
        "Sos un supervisor experto en cobranzas. Evaluá esta conversación y "
        "devolvé SOLO JSON con: score_total (0-100), fortalezas (lista), "
        "areas_mejora (lista), tecnicas_identificadas (lista), "
        "velocidad_negociacion (rapida/moderada/lenta), "
        "efectividad_cierre (alta/media/baja), sentimiento_cliente (texto).\n\n"
        f"CONVERSACIÓN:\n{texto_conversacion}")
    try:
        import json
        import requests
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-5", "max_tokens": 1500,
                  "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        r.raise_for_status()
        txt = r.json()["content"][0]["text"]
        txt = re.sub(r"```json|```", "", txt).strip()
        return json.loads(txt)
    except Exception:
        return None
