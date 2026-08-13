# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Asistente de ayuda del producto (IA)
===================================================
Responde dudas sobre CÓMO USAR el programa, dentro del propio programa:
"¿cómo cargo mi cartera?", "¿qué necesito para llamar de verdad?",
"¿dónde configuro WhatsApp?", "¿qué es ProbPago?".

Cómo funciona:

  1. **Base de conocimiento local**: se construye desde el README y los
     docs/*.md del propio producto, troceados por sección. La búsqueda de
     secciones relevantes es TF-IDF local (scikit-learn) — la documentación
     completa nunca se sube a ningún lado.
  2. **Con ANTHROPIC_API_KEY**: la pregunta + las secciones relevantes van a
     Claude, que redacta la respuesta usando SOLO ese contexto (sin inventar
     funciones que el producto no tiene).
  3. **Sin API key**: no se rompe — devuelve las secciones de documentación
     más relevantes con su fuente, que suele alcanzar para evacuar la duda.

Mismo criterio de "cero inventos" que kobra/consulta_bd.py: si la respuesta
no está en la documentación, el asistente lo dice.

Fase 2 LATAM (Brasil): `idioma="pt"` usa el corpus traducido en
`docs/*_pt.md` (hoy solo el README — traducción propia, no validada por un
hablante nativo, ver la nota al pie de esos archivos). En modo docs, si el
tema preguntado no está todavía traducido, se muestra el fragmento en
español con un aviso. En modo IA no hace falta traducir toda la
documentación: el system prompt le pide a Claude que lea contexto en
español si hace falta pero responda siempre en portugués.
"""
from __future__ import annotations

import os
import re

from kobra import llm as kllm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDIOMA_DEFAULT = "es"

# Qué documentación alimenta al asistente, por idioma (rutas relativas a la
# raíz del repo). "pt" es un corpus parcial (Fase 2) — los archivos que no
# existan todavía se saltean solos (ver `construir_base`).
FUENTES_DOCS = [
    "README.md",
    "docs/GUIA_LLAMADA_REAL_TWILIO.md",
    "docs/MODELO_COMERCIAL.md",
    "docs/WHITEPAPER_SEGURIDAD.md",
    "docs/GUIA_REGISTRO_LEGAL_URUGUAY.md",
    "docs/BACKEND_VENTA.md",
    "docs/PLANTILLA_SLA.md",
    "docs/PLANTILLA_DPA.md",
    "docs/GUIA_REGISTRO_LEGAL_BRASIL.md",
]
FUENTES_DOCS_PT = [
    "docs/README_pt.md",
    "docs/GUIA_LLAMADA_REAL_TWILIO_pt.md",
]
FUENTES_DOCS_POR_IDIOMA = {"es": FUENTES_DOCS, "pt": FUENTES_DOCS_PT}

SYSTEM_PROMPT = """Sos el asistente de ayuda de MV Kobra AI, una plataforma de cobranzas
inteligentes. Respondés dudas de usuarios (gerentes de cobranza, gestores,
administradores) sobre cómo usar el programa.

Reglas estrictas:
- Respondé SOLO con información del contexto de documentación provisto abajo.
- Si la respuesta no está en el contexto, decilo con honestidad ("eso no está
  en la documentación que tengo — escribí al buzón de contacto") en vez de
  inventar. NUNCA inventes funciones, precios ni pasos que no figuren.
- Español rioplatense, claro y directo, sin tecnicismos innecesarios.
- Respuestas cortas: 2 a 6 oraciones, o una lista breve de pasos.
- Si la duda es sobre un paso concreto, nombrá la pestaña o el archivo exacto
  (ej.: "pestaña ⚙️ Configuración", "docs/GUIA_LLAMADA_REAL_TWILIO.md").

CONTEXTO DE DOCUMENTACIÓN:
{contexto}
"""

SYSTEM_PROMPT_PT = """Você é o assistente de ajuda da MV Kobra AI, uma plataforma de cobrança
inteligente. Você responde dúvidas de usuários (gerentes de cobrança,
operadores, administradores) sobre como usar o programa.

Regras estritas:
- Responda SOMENTE com informações do contexto de documentação fornecido abaixo.
- Se a resposta não estiver no contexto, diga isso com honestidade ("isso não
  está na documentação que tenho — escreva para a caixa de contato") em vez
  de inventar. NUNCA invente funções, preços ou passos que não estejam descritos.
- Alguns trechos do contexto abaixo podem estar em espanhol (parte da
  documentação ainda não foi traduzida) — leia-os normalmente, mas responda
  SEMPRE em português do Brasil, claro e direto, sem tecnicismos desnecessários.
- Respostas curtas: 2 a 6 frases, ou uma lista breve de passos.
- Se a dúvida for sobre um passo concreto, cite a aba ou o arquivo exato
  (ex.: "aba ⚙️ Configuração", "docs/GUIA_LLAMADA_REAL_TWILIO.md").

CONTEXTO DE DOCUMENTAÇÃO:
{contexto}
"""
SYSTEM_PROMPT_POR_IDIOMA = {"es": SYSTEM_PROMPT, "pt": SYSTEM_PROMPT_PT}

_TEXTOS_POR_IDIOMA = {
    "es": {
        "vacia": "Escribí una pregunta sobre el programa.",
        "sin_resultados": ("No encontré nada en la documentación sobre eso. "
                           "Probá reformular la pregunta, o escribinos por el "
                           "buzón de contacto de esta misma pestaña."),
        "docs_intro": ("Sin un proveedor de IA configurado te muestro lo que dice la "
                      "documentación (elegí Claude, Gemini o ChatGPT y cargá su clave en "
                      "⚙️ Configuración para respuestas redactadas):\n\n"),
        "fallback_es": ("_Esta parte de la documentación todavía no está traducida al "
                        "portugués — te muestro el original en español:_\n\n"),
        "ia_fallo": ("⚠️ El proveedor de IA no respondió ({motivo}). Revisá la clave en "
                     "⚙️ Configuración. Mientras tanto, esto dice la documentación:\n\n"),
    },
    "pt": {
        "vacia": "Escreva uma pergunta sobre o programa.",
        "sin_resultados": ("Não encontrei nada na documentação sobre isso. "
                           "Tente reformular a pergunta, ou escreva para nós pela "
                           "caixa de contato desta mesma aba."),
        "docs_intro": ("Sem um provedor de IA configurado, mostro o que diz a "
                      "documentação (escolha Claude, Gemini ou ChatGPT e configure a "
                      "chave em ⚙️ Configuração para respostas redigidas):\n\n"),
        "fallback_es": ("_Esta parte da documentação ainda não foi traduzida para o "
                        "português — mostro o original em espanhol:_\n\n"),
        "ia_fallo": ("⚠️ O provedor de IA não respondeu ({motivo}). Verifique a chave em "
                     "⚙️ Configuração. Enquanto isso, isto diz a documentação:\n\n"),
    },
}


# ---------------------------------------------------------------------------
# 1) Base de conocimiento: trocear la documentación por secciones
# ---------------------------------------------------------------------------
def _trocear_markdown(texto: str, fuente: str, max_chars: int = 1800) -> list[dict]:
    """Corta un .md por encabezados (## / ###); secciones muy largas se
    subdividen por párrafos para que cada ficha quepa en contexto."""
    fichas = []
    bloques = re.split(r"\n(?=#{1,3} )", texto)
    for bloque in bloques:
        bloque = bloque.strip()
        if len(bloque) < 40:
            continue
        titulo = bloque.splitlines()[0].lstrip("# ").strip()
        while len(bloque) > max_chars:
            corte = bloque.rfind("\n\n", 0, max_chars)
            if corte < 200:
                corte = max_chars
            fichas.append({"fuente": fuente, "titulo": titulo, "texto": bloque[:corte].strip()})
            bloque = bloque[corte:].strip()
        if bloque:
            fichas.append({"fuente": fuente, "titulo": titulo, "texto": bloque})
    return fichas


def construir_base(root: str | None = None, idioma: str = IDIOMA_DEFAULT) -> list[dict]:
    root = root or ROOT
    idioma = idioma if idioma in FUENTES_DOCS_POR_IDIOMA else IDIOMA_DEFAULT
    fichas = []
    for rel in FUENTES_DOCS_POR_IDIOMA[idioma]:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            fichas.extend(_trocear_markdown(f.read(), rel))
    return fichas


_BASE_CACHE: dict[str, list[dict]] = {}


def _base(idioma: str = IDIOMA_DEFAULT) -> list[dict]:
    idioma = idioma if idioma in FUENTES_DOCS_POR_IDIOMA else IDIOMA_DEFAULT
    if idioma not in _BASE_CACHE:
        _BASE_CACHE[idioma] = construir_base(idioma=idioma)
    return _BASE_CACHE[idioma]


# ---------------------------------------------------------------------------
# 2) Retrieval local (TF-IDF, sin red)
# ---------------------------------------------------------------------------
def buscar(pregunta: str, k: int = 4, fichas: list[dict] | None = None,
          idioma: str = IDIOMA_DEFAULT) -> list[dict]:
    fichas = fichas if fichas is not None else _base(idioma)
    if not fichas or not pregunta.strip():
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [f["titulo"] + "\n" + f["texto"] for f in fichas]
    vec = TfidfVectorizer(lowercase=True, strip_accents="unicode")
    matriz = vec.fit_transform(corpus + [pregunta])
    sims = cosine_similarity(matriz[-1], matriz[:-1]).ravel()
    orden = sims.argsort()[::-1][:k]
    return [fichas[i] | {"score": float(sims[i])} for i in orden if sims[i] > 0.01]


# ---------------------------------------------------------------------------
# 3) Respuesta: Claude si hay key, docs crudos si no
# ---------------------------------------------------------------------------
def responder(pregunta: str, api_key: str | None = None, k: int = 4,
             idioma: str = IDIOMA_DEFAULT) -> dict:
    """
    Devuelve {"respuesta": str, "fuentes": [str], "modo": "ia"|"docs"|"vacio"}.
    Nunca lanza por falta de API key — degrada a mostrar la documentación.

    `idioma`: "es" (default) o "pt" (Fase 2 LATAM). En modo docs, si el
    corpus en portugués (parcial: hoy solo el README, ver FUENTES_DOCS_PT)
    no tiene nada relevante, cae a español con un aviso — nunca se rompe.
    """
    idioma = idioma if idioma in FUENTES_DOCS_POR_IDIOMA else IDIOMA_DEFAULT
    textos = _TEXTOS_POR_IDIOMA[idioma]
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return {"respuesta": textos["vacia"], "fuentes": [], "modo": "vacio"}

    relevantes = buscar(pregunta, k=k, idioma=idioma)
    fallback_es = False
    if not relevantes and idioma != IDIOMA_DEFAULT:
        relevantes = buscar(pregunta, k=k, idioma=IDIOMA_DEFAULT)
        fallback_es = bool(relevantes)
    if not relevantes:
        return {"respuesta": textos["sin_resultados"], "fuentes": [], "modo": "vacio"}

    fuentes = sorted({f["fuente"] for f in relevantes})
    if not kllm.disponible(api_key=api_key):
        cuerpo = "\n\n---\n\n".join(
            f"**{f['titulo']}** · _{f['fuente']}_\n\n{f['texto']}" for f in relevantes[:2])
        prefijo = textos["docs_intro"] + (textos["fallback_es"] if fallback_es else "")
        return {"respuesta": prefijo + cuerpo, "fuentes": fuentes, "modo": "docs"}

    contexto = "\n\n---\n\n".join(f"[{f['fuente']} · {f['titulo']}]\n{f['texto']}" for f in relevantes)
    try:
        texto = kllm.generar(pregunta, system=SYSTEM_PROMPT_POR_IDIOMA[idioma].format(contexto=contexto),
                            max_tokens=600, api_key=api_key, timeout=60, lanzar=True)
    except Exception as e:
        # El proveedor de IA falló (key inválida/vencida, sin saldo, red/proxy,
        # timeout, error de la API…). NUNCA romper con 500: caemos a mostrar la
        # documentación, avisando que la IA no respondió (mismo modo "docs").
        cuerpo = "\n\n---\n\n".join(
            f"**{f['titulo']}** · _{f['fuente']}_\n\n{f['texto']}" for f in relevantes[:2])
        aviso = textos["ia_fallo"].format(motivo=str(e)[:120])
        return {"respuesta": aviso + cuerpo, "fuentes": fuentes, "modo": "docs_fallback"}
    return {"respuesta": texto, "fuentes": fuentes, "modo": "ia"}
