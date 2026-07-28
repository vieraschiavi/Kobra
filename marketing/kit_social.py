"""
MV Kobra AI · Definición del kit de contenido para redes
========================================================
Fuente única de verdad del material de marketing: formatos de banner, copy por
red y storyboards de reels. Separado del renderizador (`generar_kit_social.py`)
para que se pueda editar el mensaje sin tocar el motor de render, y para que
los tests validen el contenido sin levantar un navegador.

Reglas del material (no son estéticas, son restricciones de negocio):

* **Sin precios.** Ninguna pieza publicada muestra importes ni planes. El
  precio se conversa en la demo, no en el feed.
* **Sin cifras de impacto presentadas como resultados reales.** El producto es
  una demo sobre datos sintéticos y el README lo dice explícitamente; decir
  "+30% de recupero" en un banner sería vender un resultado que nadie midió.
* **Un solo dominio.** `mvkobranzaia.com` es el nombre canónico del producto
  (aparece en docs, backend, i18n y checkout). Las URLs de preview de Vercel
  no van en material publicado: cambian con cada deploy.
"""
from __future__ import annotations

# Dominio canónico del producto. Cualquier otra URL en material publicado es
# un error: las de Vercel son de preview y mueren con el deploy.
DOMINIO = "mvkobranzaia.com"

# Llamada a la acción única en todas las piezas. Un solo CTA por campaña hace
# medible qué pieza trajo la reunión.
CTA = "Agendá una demo"

# Bajada de la marca, en el logotipo de cada pieza. Ningún antetítulo puede
# repetirla: quedaría la misma frase dos veces, una debajo de la otra.
BAJADA = "Cobranzas inteligentes"

# Paleta: desde `marca.py`, la fuente única. Antes estaba copiada acá.
from marketing.marca import MARCA as COLORES  # noqa: E402

# Términos que no pueden aparecer en una pieza publicada. Se chequean en el
# texto renderizado, no en el código: lo que importa es lo que se ve.
PROHIBIDO = [
    "usd", "u$s", "us$", "eur", "€", "$",
    "precio", "precios", "mensual", "/mes", "por mes",
    "plan básico", "plan starter", "plan pro", "enterprise €",
    "vercel.app", "localhost",
]


# --------------------------------------------------------------------------
# Banners
# --------------------------------------------------------------------------
# `layout` elige la composición; el renderizador la implementa con CSS grid
# (nunca posicionamiento absoluto: el absoluto es lo que hacía que el texto
# pisara el mockup cuando la tipografía real no era la del diseño).
BANNERS = [
    {
        "id": "linkedin_feed",
        "titulo": "LinkedIn · imagen destacada",
        "ancho": 1200, "alto": 627,
        "layout": "split",           # texto izquierda | mockup derecha
        "eyebrow": "ProbPago · Agente IA · Copiloto",
        "headline": "Cobrá <b>más</b>, con menos esfuerzo.",
        "sub": "Predicción de pago, negociación automática y priorización "
               "por valor esperado de recupero. En un solo tablero.",
        "cta": True,
        "chips": [],
        "captura": "dashboard_overview.png",
        "recorte": 0.20,
    },
    {
        "id": "x_post",
        "titulo": "X (Twitter) · tarjeta de post",
        "ancho": 1600, "alto": 900,
        "layout": "split",
        "eyebrow": "Demo comercial · datos sintéticos",
        "headline": "El agente que <b>negocia</b> tu cartera 24/7.",
        "sub": "Voz y WhatsApp, con copiloto de calidad en vivo y análisis "
               "de sentimiento.",
        "cta": False,
        "chips": ["Voz + WhatsApp", "Copiloto en vivo", "IA vs Humano"],
        "captura": "dashboard_negociador.png",
        "recorte": 0.20,
    },
    {
        "id": "instagram_feed",
        "titulo": "Instagram · feed",
        "ancho": 1080, "alto": 1080,
        "layout": "stack",           # texto arriba | mockup abajo
        "eyebrow": "ProbPago · priorización de cartera",
        "headline": "Llamá a quien <b>sí</b> va a pagar.",
        "sub": "ProbPago ordena la cartera por probabilidad de pago.",
        "cta": True,
        "chips": [],
        "captura": "dashboard_modelo.png",
        "recorte": 0.20,
        # El cuadrado es el formato con menos aire: el mockup se lleva algo
        # menos para que el texto entre sin achicarse hasta ser ilegible.
        "mockup": 0.30,
    },
    {
        "id": "story_reel",
        "titulo": "Story / Reel / TikTok",
        "ancho": 1080, "alto": 1920,
        "layout": "stack",
        # No repetir "MV Kobra AI": el logotipo ya está arriba en la pieza.
        "eyebrow": "ProbPago · Agente IA · Copiloto",
        "headline": "Tu cartera,<br>en <b>orden</b>.",
        "sub": "Predicción de pago, agente negociador y control de calidad "
               "de cada gestión.",
        "cta": True,
        "chips": [],
        "captura": "dashboard_copiloto.png",
        "recorte": 0.20,
    },
    {
        # Tarjeta de previsualización al compartir el link (Open Graph /
        # Twitter Card). 1200×630 es el tamaño que esperan LinkedIn, X,
        # WhatsApp y Facebook; no es el mismo que la imagen destacada del
        # feed de LinkedIn (1200×627), así que va como pieza aparte.
        "id": "og_card",
        "titulo": "Tarjeta de previsualización al compartir (Open Graph)",
        "ancho": 1200, "alto": 630,
        "layout": "split",
        "eyebrow": "ProbPago · Agente IA · Copiloto",
        "headline": "Cobranzas <b>inteligentes</b>.",
        "sub": "Predicción de pago, agente negociador y control de calidad "
               "de cada gestión.",
        "cta": False,
        "chips": [],
        "captura": "dashboard_overview.png",
        "recorte": 0.20,
    },
    {
        "id": "mail_header",
        "titulo": "Cabecera de mail corporativo",
        "ancho": 1200, "alto": 420,
        "layout": "banda",           # solo marca + titular, sin mockup
        "eyebrow": "ProbPago · Agente IA · Copiloto",
        "headline": "Menos mora. Más recupero.",
        "sub": "",
        "cta": False,
        "chips": [],
        "captura": None,
    },
]


# --------------------------------------------------------------------------
# Copy por red
# --------------------------------------------------------------------------
COPY = [
    {
        "id": "linkedin",
        "red": "LinkedIn",
        "formato": "post · tono profesional",
        "texto": """El 80% del esfuerzo de cobranzas se va en la cartera equivocada.

MV Kobra AI le da vuelta la ecuación:

• ProbPago predice quién va a pagar y prioriza por valor esperado de recupero.
• El Agente IA negocia por voz y WhatsApp, con un copiloto que evalúa la calidad en vivo.
• Un tablero gerencial que compara al Gestor IA contra el humano, ítem por ítem.

Todo sobre un pipeline real, con datos sintéticos. Te lo muestro en una demo de 15 minutos.

👉 {cta} — {dominio}""",
    },
    {
        "id": "x",
        "red": "X (Twitter)",
        "formato": "hilo · hook",
        "texto": """Tu equipo de cobranzas no tiene un problema de esfuerzo.
Tiene un problema de orden.

MV Kobra AI prioriza la cartera por probabilidad de pago y deja que un agente de IA negocie el resto. 🧵""",
    },
    {
        "id": "instagram",
        "red": "Instagram",
        "formato": "caption",
        "texto": """Cobrar mejor no es llamar más. Es llamar a quien corresponde. ⚡

MV Kobra AI: ProbPago + Agente IA Negociador + Copiloto de calidad en vivo.

Demo con datos 100% sintéticos → link en bio.
#cobranzas #IA #fintech #datascience""",
    },
    {
        "id": "tiktok",
        "red": "TikTok",
        "formato": "guion · hook de 3 s",
        "texto": """(Texto en pantalla) "Le pedí a una IA que cobrara mi cartera."

(Voz) Subís las llamadas y te dice qué gestor cobra mejor, y por qué.

CTA: Guardá esto para tu próxima reunión de cobranzas.""",
    },
    {
        "id": "mail",
        "red": "Mail corporativo",
        "formato": "asunto + cuerpo",
        "texto": """Asunto: Menos mora, más recupero — te lo muestro en 15 min

Hola {{nombre}},

Armé una demo de MV Kobra AI pensando en {{empresa}}: predice qué deudores van a pagar, prioriza la cartera por valor esperado de recupero y deja que un agente de IA negocie por voz y WhatsApp — con un tablero que mide la calidad de cada gestión.

¿Tenés 15 minutos esta semana para verla en vivo?

Saludos,
{{firma}}""",
    },
]


# --------------------------------------------------------------------------
# Storyboards de reels
# --------------------------------------------------------------------------
REELS = [
    {
        "id": "probpago",
        "titulo": "ProbPago — a quién llamar primero",
        "cuadros": [
            ("0-3 s", "3.000 deudores.\n¿A quién llamás?",
             "Hook: el problema que todos tienen."),
            ("3-8 s", "El modelo ordena\npor probabilidad de pago",
             "Se ve la cartera reordenándose en el tablero."),
            ("8-14 s", "Y por valor esperado\nde recupero",
             "No es solo quién paga: es cuánto se recupera."),
            ("14-20 s", "Mismo equipo.\nOtra lista.",
             "Cierre: el cambio es de orden, no de esfuerzo."),
        ],
    },
    {
        "id": "negociador",
        "titulo": "Agente IA — negociación por WhatsApp",
        "cuadros": [
            ("0-3 s", "Esta conversación\nno la escribió nadie",
             "Hook sobre el chat real de la demo."),
            ("3-9 s", "El agente ofrece\ncuotas y descuentos",
             "Se ve la negociación avanzando turno a turno."),
            ("9-15 s", "Y respeta los límites\nque vos definís",
             "Cumplimiento: horarios, tope de descuento, feriados."),
            ("15-20 s", "Acuerdo cerrado,\nregistrado y auditable",
             "Cierre con la traza de auditoría."),
        ],
    },
    {
        "id": "copiloto",
        "titulo": "Copiloto — calidad de cada gestión",
        "cuadros": [
            ("0-3 s", "¿Tu mejor gestor\nes el que más cobra?",
             "Hook contraintuitivo."),
            ("3-9 s", "Subís las llamadas\ny se evalúan solas",
             "Upload de audio y transcripción con roles separados."),
            ("9-15 s", "14 criterios,\nficha por gestor y por mes",
             "Se ve la evolución mensual de un gestor."),
            ("15-20 s", "Sabés qué entrenar,\ny en quién",
             "Cierre accionable."),
        ],
    },
]
