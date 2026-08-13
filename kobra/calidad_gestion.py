# © 2026 Martín Viera. Todos los derechos reservados.

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
                 "cancelacion", "divida total", "quitar todo", "cerrar la cuenta",
                 "para cancelar", "cancela con", "con una quita", "quedar al dia",
                 "al dia", "monto vencido", "lo vencido"]},
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
                 "cuota", "concepto", "valor", "divida", "montante", "atraso", "por su atraso",
                 "lo vencido", "monto vencido", "genera por mora", "por mora", "billetera",
                 "descuento a su recibo", "recibo de sueldo", "pago minimo"]},
    {"id": 8, "nombre": "Ofrecimiento de soluciones", "max": 10, "critico": False, "piso": 0.45,
     "señales": ["podemos", "opciones", "alternativas", "facilidades", "descuento", "plan",
                 "cuotas", "arreglo", "refinanciar", "beneficio", "parcelar", "desconto",
                 "le podemos ofrecer", "pago minimo", "entrega de", "con una quita",
                 "le sugerimos", "le propongo", "pase por sucursal", "pase con"]},
    {"id": 9, "nombre": "Manejo de objeciones", "max": 10, "critico": False, "piso": 0.45,
     "señales": ["entiendo su situacion", "busquemos", "comprendo que", "sin problema",
                 "veamos como", "le propongo", "que le parece", "podemos ajustar", "comprendo",
                 "dejeme ver", "como puedo hacer", "entiendo que", "de igual manera",
                 "igualmente", "le comento", "le informo", "lamentablemente"]},
    {"id": 10, "nombre": "Cierre efectivo", "max": 5, "critico": False, "piso": 0.5,
     "señales": ["quedamos en", "entonces vas a", "fecha", "el dia", "para el", "confirmo el",
                 "coordinamos", "link de pago", "comprobante", "fica combinado",
                 "plazo limite", "plazo de", "dia 19", "vuelva a comunicarse",
                 "volver a comunicarse", "le agendo", "fecha de pago", "a la brevedad"]},
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

# Fracción de referencia por criterio (promedio_humano/max del evaluador V24):
# marca la FORMA típica de una gestión — qué criterios suelen estar más flojos
# (manejo de objeciones, negociación total, seguimiento) vs. fuertes (normativo,
# identificación). Se usa para estimar el perfil por criterio de un gestor a
# partir de su calidad agregada.
_REF_FRAC = {1: 0.82, 2: 0.85, 3: 0.76, 4: 0.853, 5: 0.84, 6: 0.90, 7: 0.82,
             8: 0.75, 9: 0.72, 10: 0.78, 11: 0.86, 12: 0.94, 13: 0.833, 14: 0.75}

_RES_POSITIVO = {"Pago", "Promesa", "Arreglo de pago", "Promesa de pago", "Arreglo"}


def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower())


def _turnos_gestor(transcripcion: str) -> tuple[str, int, int]:
    """Separa lo que dijo el GESTOR (para no puntuarle señales del cliente) y
    cuenta turnos/preguntas. Si no hay marcas de hablante, usa todo el texto."""
    lineas = [ln.strip() for ln in str(transcripcion).splitlines() if ln.strip()]
    gestor, n_gestor, n_cliente = [], 0, 0
    marcado = False
    for ln in lineas:
        m = re.match(r"^\s*(gestor|agente|operador|cobrador|asesor)\s*[:\-]", ln, re.I)
        c = re.match(r"^\s*(cliente|deudor|titular|socio)\s*[:\-]", ln, re.I)
        if m:
            marcado = True; n_gestor += 1; gestor.append(ln.split(":", 1)[-1])
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


def _perfil_de(calidad_agregada: float) -> list[dict]:
    """Estima el puntaje por criterio (los 14 ítems de negociación) a partir de
    la calidad agregada de un gestor/grupo, usando la forma de referencia
    (_REF_FRAC). Es una ESTIMACIÓN de demo — con transcripciones reales, cada
    gestión trae su puntaje por criterio del evaluador."""
    factor = (calidad_agregada or 0) / PROMEDIO_HUMANO_REF
    perfil = []
    for c in RUBRICA:
        frac = min(1.0, _REF_FRAC[c["id"]] * factor)
        perfil.append({"id": c["id"], "nombre": c["nombre"], "max": c["max"],
                       "puntaje": round(c["max"] * frac, 1),
                       "pct": round(100 * frac, 0)})
    return perfil


def perfil_criterios(gestiones, canal: str | None = None, mes: str | None = None) -> dict:
    """Perfil por criterio (ítem de negociación) de IA vs Humano: en qué ítems
    es fuerte cada uno y en cuáles hay oportunidad de mejora. Devuelve, por
    criterio, el puntaje estimado de IA y de Humano y la brecha."""
    g = _filtrar(gestiones, canal, mes)
    if g is None or g.empty or "tipo_gestor" not in g.columns:
        return {"items": [], "fortalezas_ia": [], "oportunidades_humano": []}
    cal = g.groupby("tipo_gestor")["calidad_gestion"].mean().to_dict()
    perf = {t: {p["id"]: p for p in _perfil_de(cal.get(t, 0))} for t in cal}
    items = []
    for c in RUBRICA:
        ia = perf.get("IA", {}).get(c["id"], {}).get("pct", 0)
        hum = perf.get("Humano", {}).get(c["id"], {}).get("pct", 0)
        items.append({"criterio": c["nombre"], "max": c["max"], "critico": c["critico"],
                      "ia": ia, "humano": hum, "brecha": round(ia - hum, 0)})
    ordenados = sorted(items, key=lambda x: x["brecha"], reverse=True)
    return {
        "items": items,
        # Dónde el IA saca más ventaja (fortalezas del IA) y dónde el humano
        # tiene más para mejorar (misma brecha, leída del lado del humano).
        "fortalezas_ia": [x["criterio"] for x in ordenados[:4]],
        "oportunidades_humano": [x["criterio"] for x in ordenados[:4]],
    }


def evolucion(gestiones, canal: str | None = None) -> dict:
    """Evolución mensual de la calidad por tipo de gestor (IA vs Humano) —
    para ver la mejora en el tiempo."""
    g = _filtrar(gestiones, canal, None)
    if g is None or g.empty or "mes" not in g.columns:
        return {"meses": [], "series": []}
    meses = sorted(g["mes"].dropna().unique().tolist())
    series = []
    for t, sub in g.groupby("tipo_gestor"):
        por_mes = sub.groupby("mes")["calidad_gestion"].mean().round(1)
        series.append({"tipo": t, "valores": [por_mes.get(m) for m in meses]})
    return {"meses": meses, "series": series}


def mejora_potencial(gestiones, canal: str | None = None) -> dict:
    """Cuánto MEJORARÍA la cobranza si los gestores humanos alcanzaran la
    calidad (y por ende la efectividad) del Gestor IA. Estimación honesta a
    partir de la brecha real observada entre ambos grupos."""
    g = _filtrar(gestiones, canal, None)
    if g is None or g.empty or "tipo_gestor" not in g.columns:
        return None
    ia = g[g["tipo_gestor"] == "IA"]
    hum = g[g["tipo_gestor"] == "Humano"]
    if ia.empty or hum.empty:
        return None
    cal_ia = round(float(ia["calidad_gestion"].mean()), 1)
    cal_hum = round(float(hum["calidad_gestion"].mean()), 1)
    conv_ia, conv_hum = _tasa_conversion(ia), _tasa_conversion(hum)
    rec = "recupero"
    rec_ia = float(ia[rec].fillna(0).mean()) if rec in ia else 0.0
    rec_hum = float(hum[rec].fillna(0).mean()) if rec in hum else 0.0
    n_hum = len(hum)
    # Si cada gestión humana rindiera como una del IA: (dif de recupero medio) × N.
    adicional = max(0.0, (rec_ia - rec_hum) * n_hum)
    return {
        "calidad_ia": cal_ia, "calidad_humano": cal_hum,
        "brecha_calidad": round(cal_ia - cal_hum, 1),
        "conversion_ia": conv_ia, "conversion_humano": conv_hum,
        "brecha_conversion": round(conv_ia - conv_hum, 1),
        "recupero_prom_ia": round(rec_ia, 0), "recupero_prom_humano": round(rec_hum, 0),
        "gestiones_humanas": int(n_hum),
        "recupero_adicional_estimado": round(adicional, 0),
    }


def _filtrar(gestiones, canal, mes):
    if gestiones is None:
        return gestiones
    g = gestiones
    if canal and "canal" in g.columns:
        g = g[g["canal"] == canal]
    if mes and "mes" in g.columns:
        g = g[g["mes"] == mes]
    return g


# ---------------------------------------------------------------------------
# Fichas de gestores a partir de audios evaluados y acumulados
# ---------------------------------------------------------------------------
_COLS_CRITERIO = [f"c{c['id']}" for c in RUBRICA]


def fila_evaluacion(gestor: str, fecha: str, canal: str, archivo: str,
                    evaluacion: dict, id_ev: str) -> dict:
    """Aplana una evaluación (score + criterios) a una fila para acumular en el
    registro de calidad por audio."""
    mes = (fecha or "")[:7]
    fila = {"id": id_ev, "fecha": fecha, "mes": mes, "gestor": gestor or "—",
            "canal": canal, "archivo": archivo or "",
            "puntaje_total": evaluacion.get("puntaje_total"),
            "categoria": evaluacion.get("categoria"),
            "modo": evaluacion.get("modo", "local")}
    por_id = {c["id"]: c["puntaje"] for c in evaluacion.get("criterios", [])}
    for c in RUBRICA:
        fila[f"c{c['id']}"] = por_id.get(c["id"])
    return fila


def resumen_evaluaciones(df, gestor: str | None = None, mes: str | None = None) -> dict:
    """Tableros de calidad a partir de los audios evaluados y acumulados:
    ranking por gestor, evolución mensual de la nota, promedio por criterio
    (ítem de negociación) y ficha del gestor filtrado si se pide uno."""
    import pandas as pd
    if df is None or len(df) == 0:
        return {"total": 0, "por_gestor": [], "evolucion": {"meses": [], "series": []},
                "criterios_promedio": [], "evaluaciones": []}
    d = df.copy()
    if gestor:
        d = d[d["gestor"].astype(str) == gestor]
    if mes:
        d = d[d["mes"].astype(str) == mes]
    if len(d) == 0:
        return {"total": 0, "por_gestor": [], "evolucion": {"meses": [], "series": []},
                "criterios_promedio": [], "evaluaciones": []}

    por_gestor = []
    for gid, sub in d.groupby("gestor"):
        por_gestor.append({"gestor": str(gid), "audios": int(len(sub)),
                           "calidad_prom": round(float(sub["puntaje_total"].mean()), 1),
                           "ultima": str(sub["fecha"].max())})
    por_gestor.sort(key=lambda x: x["calidad_prom"], reverse=True)

    # Evolución mensual de la nota por gestor.
    meses = sorted(d["mes"].dropna().astype(str).unique().tolist())
    series = []
    for gid, sub in d.groupby("gestor"):
        prom = sub.groupby("mes")["puntaje_total"].mean().round(1)
        series.append({"gestor": str(gid), "valores": [
            (round(float(prom[m]), 1) if m in prom.index else None) for m in meses]})

    # Promedio por criterio (ítem de negociación).
    criterios_promedio = []
    for c in RUBRICA:
        col = f"c{c['id']}"
        if col in d.columns and d[col].notna().any():
            criterios_promedio.append({
                "criterio": c["nombre"], "max": c["max"], "critico": c["critico"],
                "promedio": round(float(pd.to_numeric(d[col], errors="coerce").mean()), 1),
                "pct": round(100 * float(pd.to_numeric(d[col], errors="coerce").mean()) / c["max"], 0)})

    evs = d.sort_values("fecha", ascending=False)[
        ["id", "fecha", "mes", "gestor", "canal", "puntaje_total", "categoria", "archivo"]]
    return {"total": int(len(d)), "por_gestor": por_gestor,
            "evolucion": {"meses": meses, "series": series},
            "criterios_promedio": criterios_promedio,
            "evaluaciones": evs.to_dict("records")}


# ---------------------------------------------------------------------------
# Panel de calidad de llamadas: gestor · mes · año · aspecto · vs. la media
# ---------------------------------------------------------------------------
def _pct(valor, tope):
    """Puntaje a porcentaje del máximo del criterio.

    Sin normalizar, los criterios no se pueden comparar entre sí: "Escucha
    activa" vale 15 puntos y "Apertura y saludo" 5, así que un 4 en el primero
    (26% del máximo, malo) parece mejor que un 4 en el segundo (80%, bueno).
    """
    if valor is None or tope in (None, 0):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v != v:                                    # NaN
        return None
    return round(100.0 * v / float(tope), 1)


def _criterios_vs_equipo(foco, periodo) -> list:
    """Cada aspecto de la negociación, del gestor contra la media del equipo.

    La comparación es el punto del tablero: saber que un gestor tiene 68 de
    calidad no dice qué entrenarle; saber que está 22 puntos por debajo del
    equipo en «Negociación deuda total» y 9 por encima en «Escucha activa», sí.
    """
    filas = []
    for c in RUBRICA:
        col = f"c{c['id']}"
        if col not in periodo.columns:
            continue
        suyo = _pct(foco[col].mean(), c["max"])
        equipo = _pct(periodo[col].mean(), c["max"])
        filas.append({
            "id": c["id"], "criterio": c["nombre"], "max": c["max"],
            "critico": bool(c.get("critico")),
            "puntaje": round(float(foco[col].mean()), 2)
                       if foco[col].notna().any() else None,
            "pct": suyo, "media_equipo_pct": equipo,
            "brecha": None if (suyo is None or equipo is None)
                      else round(suyo - equipo, 1),
        })
    return filas


def _evolucion_mensual(foco, periodo, hay_gestor: bool) -> list:
    """El gestor contra el equipo, mes a mes."""
    filas = []
    for m in sorted(periodo["mes"].unique()):
        pm = periodo[periodo["mes"] == m]
        fm = foco[foco["mes"] == m]
        filas.append({
            "mes": str(m),
            "gestor": round(float(fm["puntaje_total"].mean()), 1) if len(fm) else None,
            "equipo": round(float(pm["puntaje_total"].mean()), 1) if len(pm) else None,
            "audios": int(len(fm)) if hay_gestor else int(len(pm)),
        })
    return filas


def _ranking_gestores(periodo, nota_equipo) -> list:
    filas = []
    for g, sub in periodo.groupby("gestor"):
        filas.append({
            "gestor": str(g), "audios": int(len(sub)),
            "calidad_prom": round(float(sub["puntaje_total"].mean()), 1),
            "vs_media": (round(float(sub["puntaje_total"].mean()) - nota_equipo, 1)
                         if nota_equipo is not None else None),
        })
    filas.sort(key=lambda x: x["calidad_prom"], reverse=True)
    return filas


# Tramos de la distribución de notas: sirven para ver la FORMA y no solo la
# media — diez audios de 75 y cinco de 95 con cinco de 55 dan el mismo promedio
# y son dos equipos distintos.
TRAMOS_NOTA = [(0, 60, "Insuficiente"), (60, 70, "Regular"), (70, 80, "Bueno"),
               (80, 90, "Muy bueno"), (90, 101, "Excelente")]


def _distribucion_notas(foco) -> list:
    return [
        {"tramo": nombre, "desde": a, "hasta": b,
         "audios": int(((foco["puntaje_total"] >= a) &
                        (foco["puntaje_total"] < b)).sum())}
        for a, b, nombre in TRAMOS_NOTA]


def _calidad_por_canal(foco, periodo) -> list:
    if "canal" not in periodo.columns:
        return []
    return [{"canal": str(c), "audios": int(len(sub)),
             "calidad_prom": round(float(sub["puntaje_total"].mean()), 1)}
            for c, sub in foco.groupby("canal")]


def panel_calidad(df, gestor=None, anio=None, mes=None, canal=None) -> dict:
    """Tablero de calidad de llamadas, con el desglose que pide una supervisión
    real: por gestor, por mes y año, por aspecto de la negociación, y **cada
    aspecto comparado contra la media del equipo**.

    El filtro por gestor acota la ficha, pero **la media se calcula siempre
    sobre el equipo completo** del período: compararlo contra sí mismo daría
    cero de brecha en todos los aspectos y el tablero no serviría para nada.

    Cada bloque del tablero vive en su propia función (`_criterios_vs_equipo`,
    `_evolucion_mensual`, `_ranking_gestores`, `_distribucion_notas`,
    `_calidad_por_canal`); acá queda el filtrado y el armado.
    """
    import pandas as pd

    vacio = {"total": 0, "kpis": {}, "por_criterio": [], "evolucion": [],
             "ranking": [], "distribucion": [], "por_canal": [],
             "gestores": [], "anios": [], "meses": []}
    if df is None or len(df) == 0:
        return vacio

    d = pd.DataFrame(df).copy()
    d["mes"] = d.get("mes", pd.Series(dtype=str)).astype(str)
    d["anio"] = d["mes"].str[:4]

    # Universo de filtros disponibles: se calcula ANTES de filtrar, si no la
    # pantalla se queda sin opciones apenas elegís una.
    universo = {
        "gestores": sorted(d["gestor"].dropna().astype(str).unique().tolist()),
        "anios": sorted(x for x in d["anio"].unique().tolist() if x and x != "nan"),
        "meses": sorted(x for x in d["mes"].unique().tolist() if x and x != "nan"),
    }

    periodo = d
    if anio:
        periodo = periodo[periodo["anio"] == str(anio)]
    if mes:
        periodo = periodo[periodo["mes"] == str(mes)]
    if canal and "canal" in periodo.columns:
        periodo = periodo[periodo["canal"].astype(str) == str(canal)]
    if len(periodo) == 0:
        return {**vacio, **universo}

    # El equipo del período es la referencia; el gestor filtrado, el foco.
    foco = periodo
    if gestor:
        foco = periodo[periodo["gestor"].astype(str) == str(gestor)]
    if len(foco) == 0:
        return {**vacio, **universo}

    por_criterio = _criterios_vs_equipo(foco, periodo)
    con_brecha = [c for c in por_criterio if c["brecha"] is not None]
    fuertes = sorted(con_brecha, key=lambda c: -c["brecha"])[:3]
    debiles = sorted(con_brecha, key=lambda c: c["brecha"])[:3]

    nota = float(foco["puntaje_total"].mean()) if foco["puntaje_total"].notna().any() else None
    nota_equipo = (float(periodo["puntaje_total"].mean())
                   if periodo["puntaje_total"].notna().any() else None)

    return {
        "total": int(len(foco)),
        "kpis": {
            "audios": int(len(foco)),
            "calidad_prom": round(nota, 1) if nota is not None else None,
            "media_equipo": round(nota_equipo, 1) if nota_equipo is not None else None,
            "vs_media": (round(nota - nota_equipo, 1)
                         if (nota is not None and nota_equipo is not None) else None),
            "gestores_evaluados": int(periodo["gestor"].nunique()),
            "mejor_aspecto": fuertes[0]["criterio"] if fuertes else None,
            "peor_aspecto": debiles[0]["criterio"] if debiles else None,
            "criticos_bajos": int(sum(1 for c in por_criterio
                                      if c["critico"] and (c["pct"] or 100) < 60)),
        },
        "por_criterio": por_criterio,
        "fortalezas": fuertes,
        "oportunidades": debiles,
        "evolucion": _evolucion_mensual(foco, periodo, bool(gestor)),
        "ranking": _ranking_gestores(periodo, nota_equipo),
        "distribucion": _distribucion_notas(foco),
        "por_canal": _calidad_por_canal(foco, periodo),
        **universo,
    }
