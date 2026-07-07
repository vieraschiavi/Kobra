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
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Qué documentación alimenta al asistente (rutas relativas a la raíz del repo).
FUENTES_DOCS = [
    "README.md",
    "docs/GUIA_LLAMADA_REAL_TWILIO.md",
    "docs/MODELO_COMERCIAL.md",
    "docs/WHITEPAPER_SEGURIDAD.md",
    "docs/GUIA_REGISTRO_LEGAL_URUGUAY.md",
    "docs/BACKEND_VENTA.md",
    "docs/PLANTILLA_SLA.md",
    "docs/PLANTILLA_DPA.md",
]

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


def construir_base(root: str | None = None) -> list[dict]:
    root = root or ROOT
    fichas = []
    for rel in FUENTES_DOCS:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            fichas.extend(_trocear_markdown(f.read(), rel))
    return fichas


_BASE_CACHE: list[dict] | None = None


def _base() -> list[dict]:
    global _BASE_CACHE
    if _BASE_CACHE is None:
        _BASE_CACHE = construir_base()
    return _BASE_CACHE


# ---------------------------------------------------------------------------
# 2) Retrieval local (TF-IDF, sin red)
# ---------------------------------------------------------------------------
def buscar(pregunta: str, k: int = 4, fichas: list[dict] | None = None) -> list[dict]:
    fichas = fichas if fichas is not None else _base()
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
def responder(pregunta: str, api_key: str | None = None, k: int = 4) -> dict:
    """
    Devuelve {"respuesta": str, "fuentes": [str], "modo": "ia"|"docs"|"vacio"}.
    Nunca lanza por falta de API key — degrada a mostrar la documentación.
    """
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return {"respuesta": "Escribí una pregunta sobre el programa.", "fuentes": [], "modo": "vacio"}

    relevantes = buscar(pregunta, k=k)
    if not relevantes:
        return {"respuesta": ("No encontré nada en la documentación sobre eso. "
                              "Probá reformular la pregunta, o escribinos por el "
                              "buzón de contacto de esta misma pestaña."),
                "fuentes": [], "modo": "vacio"}

    fuentes = sorted({f["fuente"] for f in relevantes})
    key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if len(key) < 10:
        cuerpo = "\n\n---\n\n".join(
            f"**{f['titulo']}** · _{f['fuente']}_\n\n{f['texto']}" for f in relevantes[:2])
        return {"respuesta": ("Sin `ANTHROPIC_API_KEY` configurada te muestro lo que dice la "
                              "documentación (cargá la key en ⚙️ Configuración para respuestas "
                              "redactadas):\n\n" + cuerpo),
                "fuentes": fuentes, "modo": "docs"}

    import requests
    contexto = "\n\n---\n\n".join(f"[{f['fuente']} · {f['titulo']}]\n{f['texto']}" for f in relevantes)
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-5", "max_tokens": 600,
              "system": SYSTEM_PROMPT.format(contexto=contexto),
              "messages": [{"role": "user", "content": pregunta}]},
        timeout=60)
    r.raise_for_status()
    texto = r.json()["content"][0]["text"].strip()
    return {"respuesta": texto, "fuentes": fuentes, "modo": "ia"}
