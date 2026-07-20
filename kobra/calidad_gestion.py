"""
MV Kobra AI · Evaluación de Calidad de Gestión
==============================================
Motor de evaluación de calidad de gestiones de cobranza (llamada / WhatsApp),
portado y generalizado a Python desde el evaluador CASH-IA V24 (rúbrica de 14
criterios calibrada contra evaluaciones humanas reales, promedio ~83/100).
Genérico: sin marca, logo ni datos de ninguna empresa puntual.

Dos usos:
  1. `evaluar(transcripcion, canal)` — puntúa una gestión contra la rúbrica de
     14 criterios (100 pts), con fortalezas y oportunidades de mejora. Núcleo
     100% offline (keywords + estructura de la conversación); si hay un
     proveedor de IA configurado, recalibra los puntajes con Claude/GPT/Gemini.
  2. `comparativa(gestiones)` — Gestor IA vs Gestor Humano (calidad, conversión,
     recupero) para el dashboard de performance.

Mejoras sobre el original R:
  - Insensible a acentos y bilingüe (es/pt).
  - Combina keywords + estructura real de la charla (turnos, preguntas del
    gestor, quién cerró) en vez de solo keywords.
  - No penaliza criterios que "no aplican" (dato ya correcto, cliente cortó…).
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Rúbrica (14 criterios · 100 pts) — nombres/pesos/críticos del evaluador V24,
# con las señales (keywords) generalizadas es/pt para el puntaje offline.
# `piso`: crédito parcial cuando no se detectan señales (filosofía del original:
# ser generoso como un supervisor real; penalizar solo fallas evidentes).
# `no_aplica_max`: criterios donde "no aplicaba" debe dar el máximo, no penalizar.
# ---------------------------------------------------------------------------
RUBRICA = [
    {"id": 1, "nombre": "Escucha activa", "max": 15, "critico": True, "piso": 0.55,
     "señales": ["entiendo", "comprendo", "cuenteme", "que paso", "por que", "como esta",
                 "usted menciona", "correcto", "o sea que", "dejeme confirmar", "me dice que",
                 "entendo", "conte", "o que aconteceu"]},
    {"id": 2, "nombre": "Registro de datos", "max": 10, "critico": True, "piso": 0.6,
     "no_aplica_max": True,
     "señales": ["voy a registrar", "anoto", "dejo nota", "queda registrado", "en el sistema",
                 "actualizo", "confirmo sus datos", "vou registrar", "anotar", "no sistema"]},
    {"id": 3, "nombre": "Negociación deuda total", "max": 5, "critico": False, "piso": 0.5,
     "señales": ["deuda total", "cancelar", "totalidad", "saldo completo", "todo el saldo",
                 "cancelacion", "divida total", "quitar todo", "cerrar la cuenta"]},
    {"id": 4, "nombre": "Cierre del estado / formulario", "max": 15, "critico": True, "piso": 0.6,
     "no_aplica_max": True,
     "señales": ["queda como", "tipifico", "estado", "resultado de la gestion", "marco",
                 "dejo agendado", "proximo contacto", "estado final"]},
    {"id": 5, "nombre": "Apertura y saludo", "max": 5, "critico": False, "piso": 0.5,
     "señales": ["buenos dias", "buenas tardes", "buenas noches", "hola", "le hablo de",
                 "llamo de", "mi nombre es", "me comunico", "bom dia", "boa tarde", "meu nome"]},
    {"id": 6, "nombre": "Identificación del cliente", "max": 5, "critico": True, "piso": 0.5,
     "señales": ["hablo con", "es usted", "el titular", "confirmar su nombre", "documento",
                 "cedula", "verificar identidad", "com quem falo", "titular"]},
    {"id": 7, "nombre": "Explicación de la deuda", "max": 5, "critico": False, "piso": 0.5,
     "señales": ["saldo", "monto", "debe", "vencimiento", "vence", "capital", "intereses",
                 "cuota", "concepto", "valor", "divida", "montante"]},
    {"id": 8, "nombre": "Ofrecimiento de soluciones", "max": 10, "critico": False, "piso": 0.45,
     "señales": ["podemos", "opciones", "alternativas", "facilidades", "descuento", "plan",
                 "cuotas", "arreglo", "refinanciar", "beneficio", "parcelar", "desconto"]},
    {"id": 9, "nombre": "Manejo de objeciones", "max": 10, "critico": False, "piso": 0.45,
     "señales": ["entiendo su situacion", "busquemos", "comprendo que", "sin problema",
                 "veamos como", "le propongo", "que le parece", "podemos ajustar", "comprendo"]},
    {"id": 10, "nombre": "Cierre efectivo", "max": 5, "critico": False, "piso": 0.5,
     "señales": ["quedamos en", "entonces vas a", "fecha", "el dia", "para el", "confirmo el",
                 "coordinamos", "link de pago", "comprobante", "fica combinado"]},
    {"id": 11, "nombre": "Lenguaje y tono", "max": 5, "critico": False, "piso": 0.7,
     "no_aplica_max": True,
     "señales": ["por favor", "gracias", "senor", "senora", "con gusto", "disculpe",
                 "muy amable", "obrigado", "por favor"]},
    {"id": 12, "nombre": "Cumplimiento normativo", "max": 5, "critico": True, "piso": 0.75,
     "no_aplica_max": True,
     "señales": ["esta llamada", "grabada", "horario", "respeto su decision", "si usted prefiere",
                 "no contactar", "sus derechos", "gravacao"]},
    {"id": 13, "nombre": "Gestión del tiempo", "max": 3, "critico": False, "piso": 0.7,
     "no_aplica_max": True, "señales": []},
    {"id": 14, "nombre": "Seguimiento post-contacto", "max": 2, "critico": False, "piso": 0.55,
     "señales": ["le recuerdo", "recordatorio", "le vuelvo a", "proximo", "le escribo",
                 "cualquier cosa", "quedo a disposicion", "lembrete", "qualquer coisa"]},
]
TOTAL_PUNTOS = 100
PROMEDIO_HUMANO_REF = 83   # calibración del evaluador original (supervisores reales)

_RES_POSITIVO = {"Pago", "Promesa", "Arreglo de pago", "Promesa de pago", "Arreglo"}


def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower())


def _turnos_gestor(transcripcion: str) -> tuple[str, int, int]:
    """Separa lo que dijo el GESTOR (para no puntuarle señales del cliente) y
    cuenta turnos/preguntas. Si no hay marcas de hablante, usa todo el texto."""
    lineas = [l.strip() for l in str(transcripcion).splitlines() if l.strip()]
    gestor, n_gestor, n_cliente = [], 0, 0
    marcado = False
    for l in lineas:
        m = re.match(r"^\s*(gestor|agente|operador|cobrador|asesor)\s*[:\-]", l, re.I)
        c = re.match(r"^\s*(cliente|deudor|titular|socio)\s*[:\-]", l, re.I)
        if m:
            marcado = True; n_gestor += 1; gestor.append(l.split(":", 1)[-1])
        elif c:
            marcado = True; n_cliente += 1
    if not marcado:
        return str(transcripcion), 1, 0
    return "\n".join(gestor), n_gestor, n_cliente


def evaluar(transcripcion: str, canal: str = "Llamada",
            api_key: str | None = None, usar_ia: bool = True) -> dict:
    """Puntúa una gestión contra la rúbrica de 14 criterios (100 pts).

    Devuelve {puntaje_total, categoria, canal, criterios:[{...}],
    fortalezas:[...], oportunidades:[...], modo:'local'|'ia'}.
    """
    texto_gestor, n_gestor, n_cliente = _turnos_gestor(transcripcion)
    ng = _norm(texto_gestor)
    # Señal de escucha: que haya ida y vuelta y preguntas del gestor.
    preguntas = ng.count("?") + len(re.findall(r"\b(que|como|cuando|cuanto|por que|cual)\b", ng))
    hay_dialogo = n_cliente > 0

    criterios = []
    for c in RUBRICA:
        señales = c["señales"]
        hits = sum(1 for s in señales if s in ng) if señales else 0
        umbral = max(1, min(2, len(señales)))
        cobertura = min(1.0, hits / umbral) if señales else None

        if c["id"] == 1:   # escucha activa: pondera diálogo + preguntas
            base = min(1.0, (hits / 2) * 0.6 + min(preguntas, 4) / 4 * 0.3 + (0.1 if hay_dialogo else 0))
            frac = c["piso"] + (1 - c["piso"]) * base
        elif c["id"] == 13:  # gestión del tiempo: bien salvo charla muy corta
            frac = 1.0 if n_gestor >= 2 else 0.7
        elif cobertura is None:
            frac = c["piso"]
        elif c.get("no_aplica_max") and hits == 0:
            # No se detectó, pero es un criterio que "puede no aplicar": no penalizar fuerte.
            frac = max(c["piso"], 0.7)
        else:
            frac = c["piso"] + (1 - c["piso"]) * cobertura

        pts = round(c["max"] * frac, 1)
        criterios.append({
            "id": c["id"], "nombre": c["nombre"], "max": c["max"],
            "puntaje": pts, "critico": c["critico"],
            "cumplido": frac >= 0.8, "parcial": 0.5 <= frac < 0.8,
        })

    total = round(sum(c["puntaje"] for c in criterios), 1)
    resultado = {
        "puntaje_total": total,
        "categoria": categoria(total),
        "canal": canal,
        "criterios": criterios,
        "fortalezas": [c["nombre"] for c in criterios if c["cumplido"]][:5],
        "oportunidades": [c["nombre"] for c in criterios
                          if not c["cumplido"] and not c["parcial"]][:5],
        "referencia_humano": PROMEDIO_HUMANO_REF,
        "modo": "local",
    }
    if usar_ia:
        mejor = _recalibrar_con_ia(transcripcion, canal, resultado, api_key)
        if mejor:
            return mejor
    return resultado


def categoria(total: float) -> str:
    if total >= 90:
        return "Excelente"
    if total >= 80:
        return "Muy buena"
    if total >= 70:
        return "Aceptable"
    if total >= 60:
        return "A mejorar"
    return "Deficiente"


def _recalibrar_con_ia(transcripcion, canal, base, api_key):
    """Si hay proveedor de IA, recalibra los puntajes como un supervisor real
    (rango típico 78-95, generoso, penaliza solo fallas graves). Si no hay key
    o la respuesta no parsea, se queda con el puntaje local — nunca rompe."""
    from kobra import llm as kllm
    if not kllm.disponible(api_key=api_key):
        return None
    import json
    rubrica = "\n".join(f'{c["id"]}. {c["nombre"]} (max {c["max"]}, '
                        f'{"CRÍTICO" if c["critico"] else "normal"})' for c in RUBRICA)
    system = (
        "Sos un supervisor de calidad de cobranzas. Evaluás la gestión contra "
        "la rúbrica y devolvés SOLO un JSON, sin texto extra. Sé generoso como "
        "un supervisor real (una gestión decente ronda 80-90); penalizá fuerte "
        "solo fallas graves. NUNCA penalices un criterio que no aplicaba en el "
        "contexto (dato ya correcto, cliente cortó primero): dale el máximo.")
    prompt = (
        f"RÚBRICA (canal {canal}):\n{rubrica}\n\nTRANSCRIPCIÓN:\n{transcripcion}\n\n"
        'Devolvé: {"criterios":[{"id":N,"puntaje":X}...], '
        '"fortalezas":["..."], "oportunidades":["..."]}')
    raw = kllm.generar(prompt, system=system, max_tokens=700, api_key=api_key, timeout=45)
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0))
        por_id = {c["id"]: float(c["puntaje"]) for c in data["criterios"]}
    except Exception:
        return None
    crit = []
    for c in RUBRICA:
        pts = round(max(0.0, min(c["max"], por_id.get(c["id"], c["max"] * 0.8))), 1)
        crit.append({"id": c["id"], "nombre": c["nombre"], "max": c["max"], "puntaje": pts,
                     "critico": c["critico"], "cumplido": pts >= c["max"] * 0.8,
                     "parcial": c["max"] * 0.5 <= pts < c["max"] * 0.8})
    total = round(sum(c["puntaje"] for c in crit), 1)
    return {"puntaje_total": total, "categoria": categoria(total), "canal": canal,
            "criterios": crit,
            "fortalezas": data.get("fortalezas") or [c["nombre"] for c in crit if c["cumplido"]][:5],
            "oportunidades": data.get("oportunidades") or
                             [c["nombre"] for c in crit if not c["cumplido"]][:5],
            "referencia_humano": PROMEDIO_HUMANO_REF, "modo": "ia"}


# ---------------------------------------------------------------------------
# Comparativa Gestor IA vs Gestor Humano (performance)
# ---------------------------------------------------------------------------
def _tasa_conversion(sub) -> float:
    if sub.empty:
        return 0.0
    pos = sub["resultado"].isin(_RES_POSITIVO).sum() if "resultado" in sub.columns else 0
    return round(100 * pos / len(sub), 1)


def comparativa(gestiones, canal: str | None = None, tipo: str | None = None) -> dict:
    """Compara la performance de los gestores IA vs humanos a partir del registro
    de gestiones. Filtros opcionales por `canal` y `tipo` ('IA'|'Humano').
    Devuelve KPIs por tipo, ranking por gestor y desglose por canal."""
    import pandas as pd
    g = gestiones.copy() if gestiones is not None else pd.DataFrame()
    if g.empty or "tipo_gestor" not in g.columns:
        return {"por_tipo": [], "ranking": [], "por_canal": [], "total_gestiones": 0}
    if canal and "canal" in g.columns:
        g = g[g["canal"] == canal]
    if tipo:
        g = g[g["tipo_gestor"] == tipo]

    def _kpis(sub):
        return {
            "gestiones": int(len(sub)),
            "calidad_prom": round(float(sub["calidad_gestion"].mean()), 1)
                            if "calidad_gestion" in sub and len(sub) else 0.0,
            "tasa_conversion": _tasa_conversion(sub),
            "recupero_total": round(float(sub["recupero"].fillna(0).sum()), 0)
                              if "recupero" in sub else 0.0,
            "recupero_prom": round(float(sub["recupero"].fillna(0).mean()), 0)
                             if "recupero" in sub and len(sub) else 0.0,
        }

    por_tipo = [{"tipo": t, **_kpis(sub)} for t, sub in g.groupby("tipo_gestor")]
    ranking = []
    if "gestor_id" in g.columns:
        for gid, sub in g.groupby("gestor_id"):
            k = _kpis(sub)
            ranking.append({"gestor": sub["gestor"].iloc[0] if "gestor" in sub else gid,
                            "gestor_id": gid,
                            "tipo": sub["tipo_gestor"].iloc[0], **k})
        ranking.sort(key=lambda r: r["calidad_prom"], reverse=True)
    por_canal = []
    if "canal" in g.columns:
        for (t, cn), sub in g.groupby(["tipo_gestor", "canal"]):
            por_canal.append({"tipo": t, "canal": cn, **_kpis(sub)})
    return {"por_tipo": por_tipo, "ranking": ranking, "por_canal": por_canal,
            "total_gestiones": int(len(g))}
