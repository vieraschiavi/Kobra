# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Copiloto de Negociación en Vivo
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

from kobra import llm as kllm

# ---------------------------------------------------------------------------
# Léxico de sentimiento y emociones, por idioma (contexto cobranzas)
# ---------------------------------------------------------------------------
# "es" = español rioplatense (Fase 1 LATAM: mismo léxico sirve para Uruguay,
# Argentina, México, Chile, Colombia, Perú — validado en producción).
# "pt" = portugués brasileño (Fase 2): traducción y adaptación propia, NO
# validada aún por un profesional de cobranza nativo de Brasil. Tratarlo
# como primera versión — revisar con un experto local antes de producción.
IDIOMA_DEFAULT = "es"


def idioma_configurado() -> str:
    """Idioma del copiloto de voz en vivo para este despliegue.

    El servicio de tiempo real (`realtime/server.py`) no es multi-tenant
    (es un proceso de audio en vivo, no el panel web) — hoy un despliegue
    atiende un país/idioma a la vez, configurado por variable de entorno
    `KOBRA_IDIOMA_COPILOTO` ("es" por defecto, "pt" para Brasil)."""
    val = os.getenv("KOBRA_IDIOMA_COPILOTO", IDIOMA_DEFAULT).strip().lower()
    return val if val in POS_WORDS_POR_IDIOMA else IDIOMA_DEFAULT

POS_WORDS_POR_IDIOMA = {
    "es": {
        "gracias", "perfecto", "excelente", "bien", "buenísimo", "buenisimo",
        "genial", "acepto", "dale", "listo", "ok", "okey", "de acuerdo",
        "acuerdo", "puedo", "quiero", "pago", "pagar", "abonar", "abono",
        "solucion", "solución", "ayuda", "ayudar", "tranquilo", "tranquila",
        "conforme", "contento", "contenta", "agradezco", "dispuesto", "dispuesta",
        "dispongo", "coordinar", "coordinamos", "dinero", "dabuena", "dabuen",
        "dabuenagana", "dabuenaonda", "dabuenafe", "compromiso", "comprometo",
        "dabuenavoluntad", "cuota", "cuotas", "cerramos", "cerrar", "hecho",
    },
    "pt": {
        "obrigado", "obrigada", "perfeito", "excelente", "bom", "otimo", "ótimo",
        "aceito", "beleza", "combinado", "ok", "okay", "de acordo", "acordo",
        "posso", "quero", "pago", "pagar", "quitar", "solucao", "solução",
        "ajuda", "ajudar", "tranquilo", "tranquila", "conforme", "contente",
        "agradeco", "agradeço", "disposto", "disposta", "combinar", "combinamos",
        "dinheiro", "compromisso", "comprometo", "parcela", "parcelas",
        "fechado", "fechar", "feito", "boa vontade", "de boa",
    },
}
NEG_WORDS_POR_IDIOMA = {
    "es": {
        "no", "nunca", "imposible", "problema", "problemas", "molesto", "molesta",
        "cansado", "cansada", "harto", "harta", "mal", "peor", "pesimo", "pésimo",
        "reclamo", "queja", "enojado", "enojada", "bronca", "estafa", "mentira",
        "mienten", "vergüenza", "verguenza", "amenaza", "abogado", "denuncia",
        "denunciar", "no puedo", "sin plata", "sin dinero", "desocupado",
        "desempleado", "endeudado", "urgente", "grave", "encima", "basta", "dejen",
        "dejenme", "déjenme", "acoso", "hostigamiento", "presion", "presión",
        "cortame", "cortar", "colgar", "cuelgo", "nervioso", "nerviosa",
        "preocupado", "preocupada", "angustia", "angustiado", "difícil", "dificil",
    },
    "pt": {
        "nao", "não", "nunca", "impossivel", "impossível", "problema", "problemas",
        "chateado", "chateada", "cansado", "cansada", "farto", "farta", "mal",
        "pior", "pessimo", "péssimo", "reclamacao", "reclamação", "queixa",
        "irritado", "irritada", "raiva", "golpe", "mentira", "mentem",
        "vergonha", "ameaca", "ameaça", "advogado", "denuncia", "denúncia",
        "denunciar", "nao posso", "não posso", "sem dinheiro", "desempregado",
        "desempregada", "endividado", "endividada", "urgente", "grave", "chega",
        "basta", "parem", "me deixem", "assedio", "assédio", "pressao", "pressão",
        "cortar", "desligar", "desligo", "nervoso", "nervosa", "preocupado",
        "preocupada", "angustia", "angústia", "angustiado", "dificil", "difícil",
    },
}
# Intensificadores / atenuadores
BOOST_POR_IDIOMA = {
    "es": {"muy", "super", "súper", "recontra", "demasiado", "bastante", "tan"},
    "pt": {"muito", "super", "bastante", "tao", "tão", "demais"},
}
NEGATORS_POR_IDIOMA = {
    "es": {"no", "nunca", "jamas", "jamás", "tampoco", "ni"},
    "pt": {"nao", "não", "nunca", "jamais", "tampouco", "nem"},
}

# Señales de emoción (regex) → etiqueta. Las claves son las mismas en los dos
# idiomas (son códigos internos, no texto mostrado); solo cambia el patrón.
EMOCIONES_POR_IDIOMA = {
    "es": {
        "frustracion": r"\b(harto|harta|cansad|otra vez|siempre lo mismo|ya les dije|basta|hasta cuando)\b",
        "enojo": r"\b(enojad|bronca|indignad|estafa|mentira|verg[uü]enza|amenaz|denunci|abogad|acoso)\b",
        "ansiedad": r"\b(nervios|angustia|preocupad|no s[eé] qu[eé] hacer|desesperad|urgente|ayuda por favor)\b",
        "dificultad_economica": r"\b(sin (plata|dinero|trabajo)|desemplead|desocupad|no me alcanza|no llego|no tengo)\b",
        "satisfaccion": r"\b(gracias|perfecto|excelente|buen[ií]simo|genial|de acuerdo|me sirve|tranquil)\b",
        "intencion_pago": r"\b(quiero pagar|puedo pagar|voy a pagar|c[oó]mo (pago|abono)|acepto|dale|coordinamos|me sirve)\b",
        "objecion": r"\b(pero|el tema es|el problema es|no puedo|es mucho|no me alcanza|m[aá]s adelante|despu[eé]s)\b",
    },
    "pt": {
        "frustracion": r"\b(fart|cansad|de novo|sempre a mesma coisa|j[aá] disse|chega|at[eé] quando)\b",
        "enojo": r"\b(irritad|raiva|indignad|golpe|mentira|vergonha|amea[cç]|denunci|advogad|ass[eé]dio)\b",
        "ansiedad": r"\b(nervos|ang[uú]stia|preocupad|n[aã]o sei o que fazer|desesperad|urgente|ajuda por favor)\b",
        "dificultad_economica": r"\b(sem (dinheiro|trabalho|grana)|desempregad|n[aã]o d[aá]|n[aã]o consigo|n[aã]o tenho)\b",
        "satisfaccion": r"\b(obrigad|perfeito|excelente|[oó]timo|de acordo|me ajuda|tranquil)\b",
        "intencion_pago": r"\b(quero pagar|posso pagar|vou pagar|como (pago|quito)|aceito|combinamos|me ajuda)\b",
        "objecion": r"\b(mas|o problema [eé]|n[aã]o posso|[eé] muito|n[aã]o d[aá]|mais pra frente|depois)\b",
    },
}

# Técnicas de negociación (del gestor) → regex. Mismas claves, distinto patrón.
TECNICAS_POR_IDIOMA = {
    "es": {
        "Anclaje": r"\b(el total es|la deuda total|monto total|son \$?\s?\d)",
        "Fraccionamiento": r"\b(cuotas?|en partes|dividir|fraccionar|50%|mitad|una parte)\b",
        "Alternativas": r"\b(opci[oó]n|alternativa|o bien|otra posibilidad|le ofrezco|puede elegir|tambi[eé]n puede)\b",
        "Reciprocidad": r"\b(si (usted|hace|paga).*(yo|le|hacemos|bonific)|a cambio|por su parte)\b",
        "Urgencia": r"\b(hoy|ahora|antes de|v[aá]lid[ao] hasta|por tiempo limitado|vence|[uú]ltimo d[ií]a|solo por hoy)\b",
        "Escasez": r"\b(beneficio [uú]nico|oferta especial|solo (por hoy|esta semana)|no lo vamos a repetir|excepci[oó]n)\b",
        "Validacion": r"\b(entiendo|comprendo|me pongo en su lugar|s[eé] que|imagino que|tiene raz[oó]n)\b",
        "Prueba_social": r"\b(muchos clientes|la mayor[ií]a|otras personas|lo que suelen hacer)\b",
        "Cierre": r"\b(coordinamos|le env[ií]o el (link|qr)|queda acordado|entonces quedamos|confirmamos)\b",
    },
    "pt": {
        "Anclaje": r"\b(o total [eé]|a d[ií]vida total|valor total|s[aã]o \$?\s?\d)",
        "Fraccionamiento": r"\b(parcelas?|em partes|dividir|parcelar|50%|metade|uma parte)\b",
        "Alternativas": r"\b(op[cç][aã]o|alternativa|ou ent[aã]o|outra possibilidade|ofere[cç]o|pode escolher|tamb[eé]m pode)\b",
        "Reciprocidad": r"\b(se (voc[eê]|fizer|pagar).*(eu|lhe|fazemos|bonific)|em troca|por sua vez)\b",
        "Urgencia": r"\b(hoje|agora|antes de|v[aá]lido at[eé]|por tempo limitado|vence|[uú]ltimo dia|s[oó] hoje)\b",
        "Escasez": r"\b(benef[ií]cio [uú]nico|oferta especial|s[oó] (hoje|esta semana)|n[aã]o vamos repetir|exce[cç][aã]o)\b",
        "Validacion": r"\b(entendo|compreendo|me coloco no seu lugar|sei que|imagino que|voc[eê] tem raz[aã]o)\b",
        "Prueba_social": r"\b(muitos clientes|a maioria|outras pessoas|o que costumam fazer)\b",
        "Cierre": r"\b(combinamos|envio o (link|qr)|fica combinado|ent[aã]o ficamos|confirmamos)\b",
    },
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
    raw = [ln for ln in texto.splitlines() if ln.strip()]
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


def analizar_sentimiento(texto: str, voz: dict | None = None,
                         idioma: str = IDIOMA_DEFAULT) -> Sentimiento:
    """
    Sentimiento léxico (español o portugués, ver `idioma`) con manejo de
    negación e intensificadores.
    `voz` (opcional): features acústicas normalizadas para negociación
    telefónica en vivo, p. ej. {"energia":0-1, "pitch_var":0-1, "ritmo":0-1}.
    En producción provienen de un modelo de speech-emotion; acá se combinan
    si están disponibles.
    """
    idioma = idioma if idioma in POS_WORDS_POR_IDIOMA else IDIOMA_DEFAULT
    pos = {_strip(w) for w in POS_WORDS_POR_IDIOMA[idioma]}
    neg = {_strip(w) for w in NEG_WORDS_POR_IDIOMA[idioma]}
    boost = {_strip(w) for w in BOOST_POR_IDIOMA[idioma]}
    negators = {_strip(w) for w in NEGATORS_POR_IDIOMA[idioma]}

    tokens = _strip(texto).split()
    score = 0.0
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        val = 0
        if tok in pos:
            val = 1
        elif tok in neg:
            val = -1
        if val != 0:
            # intensificador previo
            if i > 0 and tokens[i - 1] in boost:
                val *= 1.6
            # negación en ventana de 2 palabras previas
            if any(tokens[j] in negators for j in range(max(0, i - 2), i)):
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
    emo = [e for e, pat in EMOCIONES_POR_IDIOMA[idioma].items()
           if re.search(pat, _strip(texto))]
    return Sentimiento(round(norm, 3), etiqueta, emo)


# ---------------------------------------------------------------------------
# Detección de técnicas de negociación (del gestor)
# ---------------------------------------------------------------------------
def detectar_tecnicas(conv: Conversacion, idioma: str = IDIOMA_DEFAULT) -> dict:
    idioma = idioma if idioma in TECNICAS_POR_IDIOMA else IDIOMA_DEFAULT
    texto_gestor = " ".join(_strip(t.texto) for t in conv.turnos if t.emisor == "gestor")
    return {nombre: bool(re.search(pat, texto_gestor))
            for nombre, pat in TECNICAS_POR_IDIOMA[idioma].items()}


# ---------------------------------------------------------------------------
# Scoring de calidad (heurístico, 16 criterios) — funciona sin LLM
# ---------------------------------------------------------------------------
# ids y pesos son iguales en todos los idiomas; solo cambia el nombre mostrado.
_CRITERIOS_IDS = [
    ("saludo_inicial", 5), ("identificacion", 5), ("validacion_datos", 10),
    ("empatia", 15), ("claridad", 10), ("solucion", 15),
    ("objeciones", 15), ("cierre", 15), ("registro", 10),
]
NOMBRES_CRITERIOS_POR_IDIOMA = {
    "es": {
        "saludo_inicial": "Saludo Inicial", "identificacion": "Identificación",
        "validacion_datos": "Validación Datos", "empatia": "Empatía",
        "claridad": "Claridad", "solucion": "Solución",
        "objeciones": "Manejo Objeciones", "cierre": "Cierre", "registro": "Registro",
    },
    "pt": {
        "saludo_inicial": "Saudação Inicial", "identificacion": "Identificação",
        "validacion_datos": "Validação de Dados", "empatia": "Empatia",
        "claridad": "Clareza", "solucion": "Solução",
        "objeciones": "Tratamento de Objeções", "cierre": "Fechamento",
        "registro": "Registro",
    },
}
CRITERIOS = [(cid, NOMBRES_CRITERIOS_POR_IDIOMA[IDIOMA_DEFAULT][cid], peso)
             for cid, peso in _CRITERIOS_IDS]

_CHECKS_PATRONES_POR_IDIOMA = {
    "es": {
        "saludo_inicial": r"\b(hola|buenos d[ií]as|buenas tardes|buen d[ií]a)\b",
        "identificacion": r"\b(soy|le habla|mi nombre|de parte de|del [aá]rea)\b",
        "validacion_datos": r"\b(confirm|verific|es usted|hablo con|su documento|sus datos)\b",
        "empatia": r"\b(entiendo|comprendo|me pongo en su lugar|tranquil|s[eé] que)\b",
        "solucion": r"\b(le ofrezco|opci[oó]n|alternativa|plan|cuotas?|descuento|facilidad)\b",
        "objeciones": r"\b(entiendo (pero|que)|de todas formas|le propongo|podemos|qu[eé] le parece)\b",
        "cierre": r"\b(coordinamos|le env[ií]o|queda acordado|confirmamos|entonces quedamos|link|qr)\b",
        "registro": r"\b(le env[ií]o (el|un) (comprobante|resumen|detalle)|por escrito|le llega|confirmaci[oó]n)\b",
    },
    "pt": {
        "saludo_inicial": r"\b(ol[aá]|bom dia|boa tarde|boa noite)\b",
        "identificacion": r"\b(sou|aqui [eé]|meu nome [eé]|da [aá]rea|falando)\b",
        "validacion_datos": r"\b(confirm|verific|[eé] voc[eê]|falo com|seu documento|seus dados)\b",
        "empatia": r"\b(entendo|compreendo|me coloco no seu lugar|tranquil|sei que)\b",
        "solucion": r"\b(ofere[cç]o|op[cç][aã]o|alternativa|plano|parcelas?|desconto|facilidade)\b",
        "objeciones": r"\b(entendo (mas|que)|de qualquer forma|proponho|podemos|o que acha)\b",
        "cierre": r"\b(combinamos|envio|fica combinado|confirmamos|ent[aã]o ficamos|link|qr)\b",
        "registro": r"\b(envio o (comprovante|resumo|detalhe)|por escrito|chega pra voc[eê]|confirma[cç][aã]o)\b",
    },
}


def _busca(txt, pat):
    return bool(re.search(pat, txt))


def evaluar_calidad(conv: Conversacion, idioma: str = IDIOMA_DEFAULT) -> dict:
    idioma = idioma if idioma in _CHECKS_PATRONES_POR_IDIOMA else IDIOMA_DEFAULT
    pat = _CHECKS_PATRONES_POR_IDIOMA[idioma]
    nombres = NOMBRES_CRITERIOS_POR_IDIOMA[idioma]
    criterios = [(cid, nombres[cid], peso) for cid, peso in _CRITERIOS_IDS]

    g = [t.texto for t in conv.turnos if t.emisor == "gestor"]
    gtxt = _strip(" ".join(g))
    prim = _strip(g[0]) if g else ""

    checks = {
        "saludo_inicial": _busca(prim, pat["saludo_inicial"]),
        "identificacion": _busca(gtxt, pat["identificacion"]),
        "validacion_datos": _busca(gtxt, pat["validacion_datos"]),
        "empatia": _busca(gtxt, pat["empatia"]),
        "claridad": len(gtxt) > 0 and (sum(len(x) for x in g) / max(len(g), 1)) < 320,
        "solucion": _busca(gtxt, pat["solucion"]),
        "objeciones": _busca(gtxt, pat["objeciones"]),
        "cierre": _busca(gtxt, pat["cierre"]),
        "registro": _busca(gtxt, pat["registro"]),
    }
    detalle = {}
    total = 0.0
    for cid, nombre, peso in criterios:
        cumple = checks.get(cid, False)
        sc = 100 if cumple else 35
        total += sc * peso / 100
        detalle[cid] = {"nombre": nombre, "peso": peso, "score": sc, "cumple": cumple}
    total = total / sum(p for _, _, p in criterios) * 100
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


_TIPS_POR_IDIOMA = {
    "es": {
        "enojo": ("🔴 Cliente enojado", "Bajá el ritmo, validá su malestar ANTES de ofrecer. "
                  "Evitá justificar; usá 'entiendo su molestia, resolvámoslo juntos'."),
        "frustracion": ("🟠 Frustración", "Reconocé el historial: 'sé que ya hablamos otras veces'. "
                        "Ofrecé algo concreto y distinto a lo anterior."),
        "ansiedad": ("🟠 Ansiedad", "Transmití calma y control. Dá pasos claros y cortos: "
                     "'hagamos una sola cosa hoy'."),
        "dificultad_economica": ("💸 Dificultad económica", "Priorizá plan de cuotas o quita; no presiones el "
                                 "pago total. Preguntá cuánto puede afrontar hoy."),
        "intencion_pago": ("🟢 Señal de compra", "El clima es favorable: CERRÁ ahora con fecha y medio de pago. "
                           "Enviá el link/QR de inmediato."),
        "objecion": ("🟡 Objeción activa", "No rebatas de frente: '¿qué parte le complica?' y "
                     "ofrecé 2 alternativas para que elija."),
        "propension_alta": ("📈 Alta propensión", "Deudor con alta probabilidad de pago: apuntá a pago total o "
                            "cuota inicial fuerte; poca o nula quita."),
        "propension_baja": ("📉 Baja propensión", "Propensión baja: prioridad es asegurar CUALQUIER pago. "
                            "Habilitá quita/plan largo y compromiso escrito."),
        "estrategia": "🎯 Estrategia sugerida",
        "estrategia_texto": "Guion recomendado por MV Kobra AI: «{estrategia}».",
        "todo_en_orden": ("🟢 Todo en orden", "Mantené el tono y avanzá hacia el cierre con una propuesta concreta."),
        "next_cierre": "Perfecto, coordinemos: le envío ahora el link de pago y le llega el comprobante. ¿Le queda cómodo?",
        "next_enojo": "Entiendo su molestia y quiero resolverlo hoy mismo. Le propongo una opción hecha a su medida, ¿la vemos?",
        "next_dificultad": "Sin problema, busquemos algo acorde a su situación. ¿Cuánto podría afrontar este mes?",
        "next_default": "¿Qué le parece si lo dividimos en cuotas cómodas y arrancamos con una hoy?",
    },
    "pt": {
        "enojo": ("🔴 Cliente irritado", "Diminua o ritmo, valide o incômodo ANTES de oferecer. "
                  "Evite se justificar; use 'entendo seu incômodo, vamos resolver juntos'."),
        "frustracion": ("🟠 Frustração", "Reconheça o histórico: 'sei que já conversamos outras vezes'. "
                        "Ofereça algo concreto e diferente do anterior."),
        "ansiedad": ("🟠 Ansiedade", "Transmita calma e controle. Dê passos claros e curtos: "
                     "'vamos resolver uma coisa só hoje'."),
        "dificultad_economica": ("💸 Dificuldade financeira", "Priorize plano de parcelas ou desconto; não "
                                 "pressione o pagamento total. Pergunte quanto consegue pagar hoje."),
        "intencion_pago": ("🟢 Sinal de compra", "O clima está favorável: FECHE agora com data e forma de "
                           "pagamento. Envie o link/QR imediatamente."),
        "objecion": ("🟡 Objeção ativa", "Não rebata de frente: 'o que está complicando?' e "
                     "ofereça 2 alternativas para ele escolher."),
        "propension_alta": ("📈 Alta propensão", "Devedor com alta probabilidade de pagamento: mire no pagamento "
                            "total ou numa entrada forte; pouco ou nenhum desconto."),
        "propension_baja": ("📉 Baixa propensão", "Propensão baixa: prioridade é garantir QUALQUER pagamento. "
                            "Habilite desconto/plano longo e compromisso por escrito."),
        "estrategia": "🎯 Estratégia sugerida",
        "estrategia_texto": "Roteiro recomendado pela MV Kobra AI: «{estrategia}».",
        "todo_en_orden": ("🟢 Tudo em ordem", "Mantenha o tom e avance para o fechamento com uma proposta concreta."),
        "next_cierre": "Perfeito, vamos combinar: envio agora o link de pagamento e o comprovante chega em seguida. Fica bom assim?",
        "next_enojo": "Entendo seu incômodo e quero resolver isso hoje mesmo. Vou propor uma opção feita sob medida, vamos ver?",
        "next_dificultad": "Sem problema, vamos buscar algo de acordo com sua situação. Quanto conseguiria pagar este mês?",
        "next_default": "O que acha de dividirmos em parcelas confortáveis e começarmos com uma hoje?",
    },
}


def sugerencias_en_vivo(conv: Conversacion, probpago: float | None = None,
                        estrategia: str | None = None,
                        idioma: str = IDIOMA_DEFAULT) -> dict:
    """
    Analiza el estado actual de la negociación y devuelve recomendaciones
    accionables para el gestor, más el clima emocional y la próxima jugada.
    """
    idioma = idioma if idioma in _TIPS_POR_IDIOMA else IDIOMA_DEFAULT
    t = _TIPS_POR_IDIOMA[idioma]
    sents = [analizar_sentimiento(x.texto, idioma=idioma) for x in conv.turnos]
    cli_idx = [i for i, x in enumerate(conv.turnos) if x.emisor == "cliente"]
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
        tips.append(t["enojo"])
    if "frustracion" in emociones_cli:
        tips.append(t["frustracion"])
    if "ansiedad" in emociones_cli:
        tips.append(t["ansiedad"])
    if "dificultad_economica" in emociones_cli:
        tips.append(t["dificultad_economica"])
    if "intencion_pago" in emociones_cli or clima > 0.2:
        tips.append(t["intencion_pago"])
    if "objecion" in emociones_cli and clima <= 0.2:
        tips.append(t["objecion"])

    # Ligar con ProbPago / estrategia recomendada
    if probpago is not None:
        if probpago >= 0.65:
            tips.append(t["propension_alta"])
        elif probpago < 0.35:
            tips.append(t["propension_baja"])
    if estrategia:
        tips.append((t["estrategia"], t["estrategia_texto"].format(estrategia=estrategia)))

    # Próxima frase sugerida
    if clima > 0.2 or "intencion_pago" in emociones_cli:
        next_line = t["next_cierre"]
    elif emociones_cli & {"enojo", "frustracion"}:
        next_line = t["next_enojo"]
    elif "dificultad_economica" in emociones_cli:
        next_line = t["next_dificultad"]
    else:
        next_line = t["next_default"]

    if not tips:
        tips.append(t["todo_en_orden"])

    return {
        "clima_emocional": round(clima, 3),
        "clima_etiqueta": ("positivo" if clima > 0.15 else "negativo" if clima < -0.15 else "neutro"),
        "emociones_cliente": sorted(emociones_cli),
        "ultimo_emisor": ultima.emisor if ultima else None,
        "ultimo_sentimiento": (ult_sent.etiqueta if ult_sent else None),
        "sugerencias": tips,
        "proxima_frase": next_line,
        "sentimientos_turnos": [
            {"orden": x.orden, "emisor": x.emisor, "texto": x.texto,
             "score": s.score, "etiqueta": s.etiqueta, "emociones": s.emociones}
            for x, s in zip(conv.turnos, sents)
        ],
    }


def analizar_conversacion(texto: str, canal: str = "whatsapp",
                          probpago: float | None = None,
                          estrategia: str | None = None,
                          nombre_gestor: str | None = None,
                          idioma: str = IDIOMA_DEFAULT) -> dict:
    """Pipeline completo del copiloto sobre una conversación (texto/transcripción)."""
    conv = parsear_conversacion(texto, canal, nombre_gestor)
    calidad = evaluar_calidad(conv, idioma=idioma)
    tecnicas = detectar_tecnicas(conv, idioma=idioma)
    vivo = sugerencias_en_vivo(conv, probpago, estrategia, idioma=idioma)
    return {
        "meta": {
            "gestor": conv.nombre_gestor, "cliente": conv.nombre_cliente,
            "canal": conv.canal, "mensajes": conv.total_mensajes,
            "tiempo_primera_respuesta_min": conv.tiempo_primera_respuesta_min,
            "duracion_total_horas": conv.duracion_total_horas,
            "idioma": idioma if idioma in _TIPS_POR_IDIOMA else IDIOMA_DEFAULT,
        },
        "calidad": calidad,
        "tecnicas": tecnicas,
        "copiloto": vivo,
    }


# ---------------------------------------------------------------------------
# Enriquecimiento opcional con APIs (Whisper / Claude) — solo si hay keys
# ---------------------------------------------------------------------------
def transcribir_audio(audio_path: str, idioma: str = IDIOMA_DEFAULT) -> str | None:
    """Transcribe audio con Whisper si OPENAI_API_KEY está disponible.
    `idioma`: código ISO 639-1 de 2 letras para Whisper ("es" o "pt")."""
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
                data={"model": "whisper-1", "language": idioma}, timeout=120)
        r.raise_for_status()
        return r.json().get("text")
    except Exception:
        return None


def evaluar_con_claude(texto_conversacion: str) -> dict | None:
    """Evaluación cualitativa profunda con el proveedor de IA configurado
    (Claude por default; Gemini/OpenAI si el cliente eligió otro en
    Configuración) — el nombre de la función queda por compatibilidad."""
    if not kllm.disponible():
        return None
    prompt = (
        "Sos un supervisor experto en cobranzas. Evaluá esta conversación y "
        "devolvé SOLO JSON con: score_total (0-100), fortalezas (lista), "
        "areas_mejora (lista), tecnicas_identificadas (lista), "
        "velocidad_negociacion (rapida/moderada/lenta), "
        "efectividad_cierre (alta/media/baja), sentimiento_cliente (texto).\n\n"
        f"CONVERSACIÓN:\n{texto_conversacion}")
    txt = kllm.generar(prompt, max_tokens=1500, timeout=120)
    if not txt:
        return None
    try:
        import json
        txt = re.sub(r"```json|```", "", txt).strip()
        return json.loads(txt)
    except Exception:
        return None
