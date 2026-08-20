# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Analista: el tablero que se pregunta en castellano
================================================================
La pantalla de inicio deja de ser una grilla de gráficos y pasa a contestar
preguntas: *"¿cómo viene la cobranza?"*, *"¿qué segmento se atrasó más?"*,
*"¿dónde está la plata que falta?"*.

La regla que hace que esto sirva
---------------------------------
**Los números los calcula pandas. El modelo de lenguaje solo redacta.**

Es la única forma de que un tablero conversacional se pueda usar para decidir.
Si el modelo estimara las cifras, cada respuesta sería plausible y algunas
falsas, y no habría manera de saber cuál es cuál sin rehacer la cuenta a mano —
o sea, sin usar el tablero. Un número inventado en un tablero gerencial es peor
que no tener tablero: uno se descubre al mirarlo, el otro recién cuando se tomó
la decisión.

Concretamente:

  1. `hechos()` calcula un resumen exacto de la cartera con pandas.
  2. Ese resumen —y NADA más— se le pasa al modelo junto con la pregunta.
  3. El modelo tiene instrucción de responder solo con esos números y de decir
     "no está en los datos" cuando la pregunta no se puede contestar con ellos.

Y si no hay modelo configurado, el tablero **sigue funcionando**: los KPIs, las
advertencias y las acciones son determinísticos y no dependen de ninguna API.
Lo único que se pierde es la pregunta libre.

Advertencias, sugerencias y acciones
-------------------------------------
Las tres listas de la pantalla salen de reglas explícitas sobre los datos, no
del modelo. Una advertencia que aparece y desaparece según lo que haya
alucinado el modelo esa vez no es una advertencia.
"""
from __future__ import annotations

import pandas as pd

from kobra import llm as kllm

# Umbrales de las reglas. Se declaran acá y no salpicados en el código para
# que se puedan discutir y ajustar sin leer la implementación.
UMBRAL_MORA_ALTA_DIAS = 90
UMBRAL_CONCENTRACION = 0.35      # % de la deuda en un solo segmento
UMBRAL_CONTACTABILIDAD_BAJA = 0.4
UMBRAL_PROMESAS_INCUMPLIDAS = 0.5


def _seguro(df: pd.DataFrame, col: str) -> pd.Series | None:
    """La columna, o None si la cartera del cliente no la trae."""
    return df[col] if col in df.columns else None


def hechos(df: pd.DataFrame) -> dict:
    """Resumen exacto de la cartera. Todo lo de acá es una cuenta, no una
    estimación."""
    monto = _seguro(df, "monto_deuda")
    dias = _seguro(df, "dias_mora")
    prob = _seguro(df, "prob_pago")

    h = {"deudores": int(len(df))}

    if monto is not None:
        h["deuda_total"] = round(float(monto.sum()), 2)
        h["deuda_promedio"] = round(float(monto.mean()), 2)
        h["deuda_mediana"] = round(float(monto.median()), 2)

    if dias is not None:
        h["mora_promedio_dias"] = round(float(dias.mean()), 1)
        en_mora_alta = dias > UMBRAL_MORA_ALTA_DIAS
        h["deudores_mora_alta"] = int(en_mora_alta.sum())
        h["pct_mora_alta"] = round(float(en_mora_alta.mean() * 100), 1)
        if monto is not None:
            h["deuda_en_mora_alta"] = round(float(monto[en_mora_alta].sum()), 2)

    if prob is not None:
        h["prob_pago_promedio"] = round(float(prob.mean()), 3)
        altos = prob >= 0.7
        h["deudores_alta_propension"] = int(altos.sum())
        if monto is not None:
            # Lo más accionable del tablero: plata cobrable ya.
            h["deuda_recuperable_alta_propension"] = round(
                float(monto[altos].sum()), 2)

    for dimension in ("segmento", "producto", "departamento", "canal_preferido"):
        serie = _seguro(df, dimension)
        if serie is None:
            continue
        if monto is not None:
            por = monto.groupby(serie).sum().sort_values(ascending=False)
            h[f"deuda_por_{dimension}"] = {str(k): round(float(v), 2)
                                           for k, v in por.head(8).items()}
        else:
            h[f"deudores_por_{dimension}"] = {
                str(k): int(v) for k, v in serie.value_counts().head(8).items()}

    contact = _seguro(df, "contactabilidad")
    if contact is not None:
        h["contactabilidad_promedio"] = round(float(contact.mean()), 3)

    cumplidas = _seguro(df, "promesas_cumplidas")
    incumplidas = _seguro(df, "promesas_incumplidas")
    if cumplidas is not None and incumplidas is not None:
        total = float(cumplidas.sum() + incumplidas.sum())
        if total > 0:
            h["tasa_cumplimiento_promesas"] = round(
                float(cumplidas.sum()) / total, 3)

    return h


def advertencias(h: dict) -> list[dict]:
    """Lo que está mal y hay que mirar. Reglas explícitas, no opiniones."""
    salida = []

    pct = h.get("pct_mora_alta")
    if pct is not None and pct >= 25:
        salida.append({
            "titulo": f"{pct}% de la cartera pasó los {UMBRAL_MORA_ALTA_DIAS} días",
            "detalle": "Cuanto más vieja la mora, menos se recupera. Es el "
                       "tramo donde conviene actuar primero.",
            "severidad": "alta" if pct >= 40 else "media"})

    contact = h.get("contactabilidad_promedio")
    if contact is not None and contact < UMBRAL_CONTACTABILIDAD_BAJA:
        salida.append({
            "titulo": f"Contactabilidad baja ({contact:.0%})",
            "detalle": "Más de la mitad de la cartera no atiende. Antes de "
                       "sumar gestiones conviene actualizar los datos de "
                       "contacto: gestionar a quien no atiende no cobra y "
                       "consume cupo.",
            "severidad": "alta"})

    cumpl = h.get("tasa_cumplimiento_promesas")
    if cumpl is not None and cumpl < UMBRAL_PROMESAS_INCUMPLIDAS:
        salida.append({
            "titulo": f"Solo {cumpl:.0%} de las promesas se cumplen",
            "detalle": "Una promesa que no se cumple ocupa el lugar de una "
                       "gestión real. Conviene revisar si los acuerdos son "
                       "alcanzables para el deudor.",
            "severidad": "media"})

    # Concentración: una cartera muy cargada en un solo segmento es un riesgo
    # que no se ve mirando el total.
    #
    # El umbral NO puede ser un porcentaje fijo: depende de cuántas categorías
    # haya. Con dos segmentos, un reparto 50/50 es el más equilibrado que puede
    # existir, y una regla de "35% es mucho" lo marcaría como concentrado —
    # una alerta que aparece siempre y que por eso se deja de mirar. Se compara
    # contra el reparto parejo (1/n) y se pide además un piso absoluto.
    for dimension in ("segmento", "producto", "departamento"):
        reparto = h.get(f"deuda_por_{dimension}")
        if not reparto or len(reparto) < 3:
            continue
        total = sum(reparto.values())
        if total <= 0:
            continue
        top, valor = max(reparto.items(), key=lambda kv: kv[1])
        parte = valor / total
        parejo = 1 / len(reparto)
        if parte >= max(UMBRAL_CONCENTRACION, 1.5 * parejo):
            salida.append({
                "titulo": f"{parte:.0%} de la deuda está en {dimension} «{top}»",
                "detalle": "Una cartera concentrada se mueve toda junta: lo "
                           "que afecte a ese grupo afecta al resultado entero.",
                "severidad": "media"})
            break

    return salida


def sugerencias(h: dict) -> list[dict]:
    """Dónde está la oportunidad."""
    salida = []

    recuperable = h.get("deuda_recuperable_alta_propension")
    cuantos = h.get("deudores_alta_propension")
    if recuperable and cuantos:
        salida.append({
            "titulo": f"{cuantos:,} deudores con alta propensión de pago".replace(",", "."),
            "detalle": f"Concentran ${recuperable:,.0f} de deuda. Es el grupo "
                       "donde la misma gestión rinde más.".replace(",", "."),
        })

    en_mora_alta = h.get("deuda_en_mora_alta")
    if en_mora_alta and h.get("deuda_total"):
        parte = en_mora_alta / h["deuda_total"]
        if parte >= 0.2:
            salida.append({
                "titulo": f"{parte:.0%} de la deuda está en mora alta",
                "detalle": "Para este tramo suele rendir más una propuesta de "
                           "quita o refinanciación que insistir con el total.",
            })

    reparto = h.get("deuda_por_canal_preferido")
    if reparto:
        canal, _ = max(reparto.items(), key=lambda kv: kv[1])
        salida.append({
            "titulo": f"El canal con más deuda asociada es {canal}",
            "detalle": "Arrancar por el canal que el deudor prefiere sube la "
                       "tasa de contacto efectivo.",
        })

    return salida


def acciones(h: dict) -> list[dict]:
    """Qué hacer hoy, en orden. Concreto y contable."""
    salida = []

    cuantos = h.get("deudores_alta_propension")
    if cuantos:
        salida.append({
            "titulo": f"Gestionar los {cuantos:,} de alta propensión".replace(",", "."),
            "detalle": "Es la cola con mejor retorno por gestión.",
            "prioridad": 1})

    mora_alta = h.get("deudores_mora_alta")
    if mora_alta:
        salida.append({
            "titulo": f"Revisar los {mora_alta:,} con más de {UMBRAL_MORA_ALTA_DIAS} días".replace(",", "."),
            "detalle": "Decidir por cada uno: refinanciar, quita, o pasar a "
                       "gestión externa. Dejarlos quietos solo los envejece.",
            "prioridad": 2})

    contact = h.get("contactabilidad_promedio")
    if contact is not None and contact < UMBRAL_CONTACTABILIDAD_BAJA:
        salida.append({
            "titulo": "Actualizar datos de contacto",
            "detalle": "Sin teléfono válido, ninguna estrategia de cobranza "
                       "funciona.",
            "prioridad": 3})

    return sorted(salida, key=lambda a: a["prioridad"])


# ---------------------------------------------------------------------------
# La pregunta libre
# ---------------------------------------------------------------------------
_SISTEMA = """Sos el analista de cobranzas de MV Kobra AI.

Contestás preguntas sobre una cartera usando EXCLUSIVAMENTE los datos que te
paso abajo, que ya están calculados y son exactos.

Reglas que no se negocian:
1. No inventes ni estimes ningún número. Si una cifra no está en los datos, no
   la digas.
2. Si la pregunta no se puede contestar con estos datos, decilo claro:
   "Eso no está en los datos que tengo". No aproximes ni supongas.
3. No hagas proyecciones a futuro: no tenés información para eso.
4. Respondé en español rioplatense, en 2 o 3 frases, directo.
5. Citá las cifras exactas que uses, con su unidad.
"""


class SinModelo(RuntimeError):
    """No hay proveedor de IA configurado."""


def responder(pregunta: str, df: pd.DataFrame) -> dict:
    """Contesta una pregunta sobre la cartera.

    Devuelve la respuesta y **los hechos que se usaron**: quien lea el tablero
    tiene que poder verificar de dónde salió cada número sin creernos.
    """
    if not pregunta or not pregunta.strip():
        raise ValueError("la pregunta está vacía")

    h = hechos(df)
    if not kllm.disponible():
        raise SinModelo(
            "No hay un proveedor de IA configurado. Los indicadores, las "
            "advertencias y las acciones funcionan igual; para preguntar en "
            "castellano hay que configurar la IA en Configuración.")

    import json
    prompt = (f"Datos de la cartera (exactos, ya calculados):\n"
              f"{json.dumps(h, ensure_ascii=False, indent=1)}\n\n"
              f"Pregunta: {pregunta.strip()}")
    try:
        texto = kllm.generar(prompt, system=_SISTEMA, max_tokens=400)
    except Exception as e:                              # noqa: BLE001
        # El proveedor puede fallar por mil razones ajenas a Kobra: clave
        # vencida, cuota agotada, la API caída, sin internet. Ninguna es un
        # error del programa, y todas tienen que llegar al usuario como
        # "no se pudo consultar", no como una pantalla rota.
        raise SinModelo(
            f"No se pudo consultar al proveedor de IA ({e}). Los indicadores "
            "y las acciones de la pantalla funcionan igual.") from e

    # `generar` puede devolver None o vacío si el proveedor respondió mal. Sin
    # este chequeo, el `.strip()` tira AttributeError y el endpoint contesta
    # 500 — o sea, "Kobra está roto" en vez de "el proveedor no contestó".
    if not texto or not str(texto).strip():
        raise SinModelo(
            "El proveedor de IA no devolvió una respuesta. Probá de nuevo, o "
            "revisá la configuración de la IA. Los indicadores y las acciones "
            "de la pantalla funcionan igual.")
    return {"respuesta": str(texto).strip(), "hechos_usados": h}


def preguntas_sugeridas(h: dict) -> list[str]:
    """Las que se ofrecen bajo el buscador.

    Se arman según lo que la cartera efectivamente tiene: ofrecer "¿cómo viene
    la contactabilidad?" a quien no subió esa columna es prometer algo que va a
    responder "no está en los datos".
    """
    ps = []
    if h.get("deuda_total"):
        ps.append("¿Cómo viene la cobranza este mes?")
    if h.get("deuda_por_segmento"):
        ps.append("¿Qué segmento concentra más deuda?")
    if h.get("pct_mora_alta") is not None:
        ps.append("¿Cuánta cartera está en mora alta?")
    if h.get("deudores_alta_propension"):
        ps.append("¿Dónde conviene poner el equipo hoy?")
    if h.get("contactabilidad_promedio") is not None:
        ps.append("¿Cómo está la contactabilidad?")
    return ps[:4]


def tablero(df: pd.DataFrame) -> dict:
    """Todo lo que muestra la pantalla, sin llamar al modelo.

    Es determinístico a propósito: el tablero tiene que abrir y mostrar lo
    mismo siempre, haya o no proveedor de IA configurado.
    """
    h = hechos(df)
    return {
        "hechos": h,
        "advertencias": advertencias(h),
        "sugerencias": sugerencias(h),
        "acciones": acciones(h),
        "preguntas_sugeridas": preguntas_sugeridas(h),
        "ia_disponible": kllm.disponible(),
    }
