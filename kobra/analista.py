# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Analista: el tablero que se pregunta en el idioma del cliente
===========================================================================
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

Los tres idiomas
----------------
El texto de esas listas se muestra tal cual en la pantalla, así que un cliente
que puso la interfaz en inglés o en portugués no puede recibirlo en castellano.
Las frases viven en `_TEXTOS`, una plantilla por clave y por idioma, y se
resuelven con `_t(clave, idioma, **valores)`.

Se traduce **la plantilla, no la frase ya armada**: traducir a posteriori
obligaría a reconocer por coincidencia de texto qué parte de la cadena es
literal y cuál es un número, y cualquier cambio de redacción rompería el
reconocimiento en silencio. Y las reglas —umbrales, orden, qué se muestra y
qué no— son las mismas en los tres idiomas: lo único que cambia es de dónde
sale la cadena.
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


# ---------------------------------------------------------------------------
# Los textos de la pantalla, en los tres idiomas del producto
# ---------------------------------------------------------------------------
IDIOMA_POR_DEFECTO = "es"

# Una clave por frase, una plantilla por idioma. Las variables entran por
# `.format()` ya formateadas: la plantilla decide DÓNDE va el número, nunca
# cómo se escribe.
_TEXTOS: dict[str, dict[str, str]] = {
    # -- Avisos ------------------------------------------------------------
    "aviso.mora_alta.titulo": {
        "es": "{pct}% de la cartera pasó los {dias} días",
        "pt": "{pct}% da carteira passou dos {dias} dias",
        "en": "{pct}% of the portfolio is past {dias} days in arrears",
    },
    "aviso.mora_alta.detalle": {
        "es": "Cuanto más vieja la mora, menos se recupera. Es el tramo donde "
              "conviene actuar primero.",
        "pt": "Quanto mais antigo o atraso, menos se recupera. É a faixa em "
              "que convém agir primeiro.",
        "en": "The older the arrears, the less gets recovered. It is the "
              "aging bucket where acting first pays off.",
    },
    "aviso.contactabilidad.titulo": {
        "es": "Contactabilidad baja ({pct})",
        "pt": "Contactabilidade baixa ({pct})",
        "en": "Low contactability ({pct})",
    },
    "aviso.contactabilidad.detalle": {
        "es": "Más de la mitad de la cartera no atiende. Antes de sumar "
              "gestiones conviene actualizar los datos de contacto: gestionar "
              "a quien no atiende no cobra y consume cupo.",
        "pt": "Mais da metade da carteira não atende. Antes de somar gestões "
              "convém atualizar os dados de contato: gerir quem não atende "
              "não cobra e consome cota.",
        "en": "More than half of the portfolio does not answer. Before adding "
              "interactions it is worth updating the contact details: working "
              "someone who never answers collects nothing and burns quota.",
    },
    "aviso.promesas.titulo": {
        "es": "Solo {pct} de las promesas se cumplen",
        "pt": "Apenas {pct} das promessas são cumpridas",
        "en": "Only {pct} of promises are kept",
    },
    "aviso.promesas.detalle": {
        "es": "Una promesa que no se cumple ocupa el lugar de una gestión "
              "real. Conviene revisar si los acuerdos son alcanzables para el "
              "deudor.",
        "pt": "Uma promessa que não se cumpre ocupa o lugar de uma gestão "
              "real. Convém revisar se os acordos são alcançáveis para o "
              "devedor.",
        "en": "A promise that is not kept takes the place of a real "
              "interaction. It is worth checking whether the arrangements are "
              "within the debtor's reach.",
    },
    "aviso.concentracion.titulo": {
        "es": "{pct} de la deuda está en {dimension} «{top}»",
        "pt": "{pct} da dívida está em {dimension} «{top}»",
        "en": "{pct} of the debt sits in {dimension} «{top}»",
    },
    "aviso.concentracion.detalle": {
        "es": "Una cartera concentrada se mueve toda junta: lo que afecte a "
              "ese grupo afecta al resultado entero.",
        "pt": "Uma carteira concentrada se move toda junta: o que afetar esse "
              "grupo afeta o resultado inteiro.",
        "en": "A concentrated portfolio moves as one: whatever hits that "
              "group hits the whole result.",
    },
    # -- Sugerencias -------------------------------------------------------
    "sugerencia.alta_propension.titulo": {
        "es": "{cuantos} deudores con alta propensión de pago",
        "pt": "{cuantos} devedores com alta propensão de pagamento",
        "en": "{cuantos} debtors with high payment propensity",
    },
    "sugerencia.alta_propension.detalle": {
        "es": "Concentran ${monto} de deuda. Es el grupo donde la misma "
              "gestión rinde más.",
        "pt": "Concentram ${monto} de dívida. É o grupo onde a mesma gestão "
              "rende mais.",
        "en": "They hold ${monto} of debt. It is the group where the same "
              "interaction yields the most.",
    },
    "sugerencia.mora_alta.titulo": {
        "es": "{pct} de la deuda está en mora alta",
        "pt": "{pct} da dívida está em atraso alto",
        "en": "{pct} of the debt is in high arrears",
    },
    "sugerencia.mora_alta.detalle": {
        "es": "Para este tramo suele rendir más una propuesta de quita o "
              "refinanciación que insistir con el total.",
        "pt": "Para essa faixa costuma render mais uma proposta de desconto "
              "ou refinanciamento do que insistir com o total.",
        "en": "For this aging bucket a write-off or refinancing offer usually "
              "pays off more than pushing for the full amount.",
    },
    "sugerencia.canal.titulo": {
        "es": "El canal con más deuda asociada es {canal}",
        "pt": "O canal com mais dívida associada é {canal}",
        "en": "The channel with the most debt attached is {canal}",
    },
    "sugerencia.canal.detalle": {
        "es": "Arrancar por el canal que el deudor prefiere sube la tasa de "
              "contacto efectivo.",
        "pt": "Começar pelo canal que o devedor prefere aumenta a taxa de "
              "contato efetivo.",
        "en": "Starting on the channel the debtor prefers raises the "
              "effective contact rate.",
    },
    # -- Acciones ----------------------------------------------------------
    "accion.alta_propension.titulo": {
        "es": "Gestionar los {cuantos} de alta propensión",
        "pt": "Trabalhar os {cuantos} de alta propensão",
        "en": "Work the {cuantos} with high propensity",
    },
    "accion.alta_propension.detalle": {
        "es": "Es la cola con mejor retorno por gestión.",
        "pt": "É a fila com melhor retorno por gestão.",
        "en": "It is the queue with the best return per interaction.",
    },
    "accion.mora_alta.titulo": {
        "es": "Revisar los {cuantos} con más de {dias} días",
        "pt": "Revisar os {cuantos} com mais de {dias} dias",
        "en": "Review the {cuantos} past {dias} days",
    },
    "accion.mora_alta.detalle": {
        "es": "Decidir por cada uno: refinanciar, quita, o pasar a gestión "
              "externa. Dejarlos quietos solo los envejece.",
        "pt": "Decidir caso a caso: refinanciar, desconto, ou passar para "
              "cobrança externa. Deixá-los parados só os envelhece.",
        "en": "Decide one by one: refinance, write-off, or hand over to "
              "external collection. Leaving them alone only ages them.",
    },
    "accion.contactabilidad.titulo": {
        "es": "Actualizar datos de contacto",
        "pt": "Atualizar dados de contato",
        "en": "Update contact details",
    },
    "accion.contactabilidad.detalle": {
        "es": "Sin teléfono válido, ninguna estrategia de cobranza funciona.",
        "pt": "Sem telefone válido, nenhuma estratégia de cobrança funciona.",
        "en": "Without a valid phone number, no collections strategy works.",
    },
    # -- Preguntas sugeridas ----------------------------------------------
    "pregunta.cobranza": {
        "es": "¿Cómo viene la cobranza este mes?",
        "pt": "Como está a cobrança neste mês?",
        "en": "How are collections going this month?",
    },
    "pregunta.segmento": {
        "es": "¿Qué segmento concentra más deuda?",
        "pt": "Qual segmento concentra mais dívida?",
        "en": "Which segment holds the most debt?",
    },
    "pregunta.mora_alta": {
        "es": "¿Cuánta cartera está en mora alta?",
        "pt": "Quanta carteira está em atraso alto?",
        "en": "How much of the portfolio is in high arrears?",
    },
    "pregunta.equipo": {
        "es": "¿Dónde conviene poner el equipo hoy?",
        "pt": "Onde vale a pena colocar a equipe hoje?",
        "en": "Where should the team focus today?",
    },
    "pregunta.contactabilidad": {
        "es": "¿Cómo está la contactabilidad?",
        "pt": "Como está a contactabilidade?",
        "en": "How is contactability?",
    },
    # -- Nombres de dimensión ---------------------------------------------
    # El aviso de concentración nombra la dimensión dentro de la frase. Se
    # resuelve por clave y no traduciendo la palabra que quedó en la cadena,
    # que es lo mismo que se pide para el resto del módulo.
    "dimension.segmento": {"es": "segmento", "pt": "segmento", "en": "segment"},
    "dimension.producto": {"es": "producto", "pt": "produto", "en": "product"},
    "dimension.departamento": {
        "es": "departamento", "pt": "departamento", "en": "department"},
    # -- Canales -----------------------------------------------------------
    # Solo los canales que genera el producto. Un canal que venga de la cartera
    # del cliente ("Portal propio", "Carta") se muestra tal como lo escribió:
    # inventarle una traducción sería cambiarle el dato.
    "canal.Llamada": {"es": "Llamada", "pt": "Ligação", "en": "Call"},
    "canal.WhatsApp": {"es": "WhatsApp", "pt": "WhatsApp", "en": "WhatsApp"},
    "canal.Email": {"es": "Email", "pt": "E-mail", "en": "Email"},
    "canal.SMS": {"es": "SMS", "pt": "SMS", "en": "SMS"},
}

# El separador de miles cambia con el idioma, y un "$1.500" leído en inglés es
# mil quinientas veces menos plata de la que hay. Es formato, no cuenta: el
# número que entra es el mismo en los tres idiomas.
_SEPARADOR_MILES = {"es": ".", "pt": ".", "en": ","}


def _t(clave: str, idioma: str = IDIOMA_POR_DEFECTO, **valores: object) -> str:
    """La frase `clave` en `idioma`, con `valores` ya formateados adentro.

    Cae a castellano cuando el idioma no tiene esa frase todavía: una tarjeta
    en castellano dentro de una pantalla en inglés se entiende igual; una
    tarjeta vacía —o una excepción— deja al gerente sin el aviso.
    """
    variantes = _TEXTOS.get(clave)
    if not variantes:
        return clave                      # clave inexistente: bug visible, no caída
    plantilla = variantes.get(idioma) or variantes[IDIOMA_POR_DEFECTO]
    return plantilla.format(**valores) if valores else plantilla


def _miles(n: float, idioma: str = IDIOMA_POR_DEFECTO) -> str:
    """El número con el separador de miles del idioma y sin decimales."""
    return f"{n:,.0f}".replace(",", _SEPARADOR_MILES.get(idioma, "."))


def _canal(nombre: str, idioma: str = IDIOMA_POR_DEFECTO) -> str:
    """El nombre del canal en el idioma, o el dato tal cual si no es uno de
    los que genera el producto."""
    return _t(f"canal.{nombre}", idioma) if f"canal.{nombre}" in _TEXTOS else str(nombre)


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


def advertencias(h: dict, idioma: str = IDIOMA_POR_DEFECTO) -> list[dict]:
    """Lo que está mal y hay que mirar. Reglas explícitas, no opiniones.

    `severidad` queda en castellano a propósito: no es texto de pantalla sino
    el código que la interfaz traduce por su cuenta (`sev_alta`/`sev_media`).
    Traducirlo acá le rompería el mapeo.
    """
    salida = []

    pct = h.get("pct_mora_alta")
    if pct is not None and pct >= 25:
        salida.append({
            "titulo": _t("aviso.mora_alta.titulo", idioma,
                         pct=pct, dias=UMBRAL_MORA_ALTA_DIAS),
            "detalle": _t("aviso.mora_alta.detalle", idioma),
            "severidad": "alta" if pct >= 40 else "media"})

    contact = h.get("contactabilidad_promedio")
    if contact is not None and contact < UMBRAL_CONTACTABILIDAD_BAJA:
        salida.append({
            "titulo": _t("aviso.contactabilidad.titulo", idioma,
                         pct=f"{contact:.0%}"),
            "detalle": _t("aviso.contactabilidad.detalle", idioma),
            "severidad": "alta"})

    cumpl = h.get("tasa_cumplimiento_promesas")
    if cumpl is not None and cumpl < UMBRAL_PROMESAS_INCUMPLIDAS:
        salida.append({
            "titulo": _t("aviso.promesas.titulo", idioma, pct=f"{cumpl:.0%}"),
            "detalle": _t("aviso.promesas.detalle", idioma),
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
                "titulo": _t("aviso.concentracion.titulo", idioma,
                             pct=f"{parte:.0%}",
                             dimension=_t(f"dimension.{dimension}", idioma),
                             top=top),
                "detalle": _t("aviso.concentracion.detalle", idioma),
                "severidad": "media"})
            break

    return salida


def sugerencias(h: dict, idioma: str = IDIOMA_POR_DEFECTO) -> list[dict]:
    """Dónde está la oportunidad."""
    salida = []

    recuperable = h.get("deuda_recuperable_alta_propension")
    cuantos = h.get("deudores_alta_propension")
    if recuperable and cuantos:
        salida.append({
            "titulo": _t("sugerencia.alta_propension.titulo", idioma,
                         cuantos=_miles(cuantos, idioma)),
            "detalle": _t("sugerencia.alta_propension.detalle", idioma,
                          monto=_miles(recuperable, idioma)),
        })

    en_mora_alta = h.get("deuda_en_mora_alta")
    if en_mora_alta and h.get("deuda_total"):
        parte = en_mora_alta / h["deuda_total"]
        if parte >= 0.2:
            salida.append({
                "titulo": _t("sugerencia.mora_alta.titulo", idioma,
                             pct=f"{parte:.0%}"),
                "detalle": _t("sugerencia.mora_alta.detalle", idioma),
            })

    reparto = h.get("deuda_por_canal_preferido")
    if reparto:
        canal, _ = max(reparto.items(), key=lambda kv: kv[1])
        salida.append({
            "titulo": _t("sugerencia.canal.titulo", idioma,
                         canal=_canal(canal, idioma)),
            "detalle": _t("sugerencia.canal.detalle", idioma),
        })

    return salida


def acciones(h: dict, idioma: str = IDIOMA_POR_DEFECTO) -> list[dict]:
    """Qué hacer hoy, en orden. Concreto y contable."""
    salida = []

    cuantos = h.get("deudores_alta_propension")
    if cuantos:
        salida.append({
            "titulo": _t("accion.alta_propension.titulo", idioma,
                         cuantos=_miles(cuantos, idioma)),
            "detalle": _t("accion.alta_propension.detalle", idioma),
            "prioridad": 1})

    mora_alta = h.get("deudores_mora_alta")
    if mora_alta:
        salida.append({
            "titulo": _t("accion.mora_alta.titulo", idioma,
                         cuantos=_miles(mora_alta, idioma),
                         dias=UMBRAL_MORA_ALTA_DIAS),
            "detalle": _t("accion.mora_alta.detalle", idioma),
            "prioridad": 2})

    contact = h.get("contactabilidad_promedio")
    if contact is not None and contact < UMBRAL_CONTACTABILIDAD_BAJA:
        salida.append({
            "titulo": _t("accion.contactabilidad.titulo", idioma),
            "detalle": _t("accion.contactabilidad.detalle", idioma),
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


def preguntas_sugeridas(h: dict, idioma: str = IDIOMA_POR_DEFECTO) -> list[str]:
    """Las que se ofrecen bajo el buscador.

    Se arman según lo que la cartera efectivamente tiene: ofrecer "¿cómo viene
    la contactabilidad?" a quien no subió esa columna es prometer algo que va a
    responder "no está en los datos".
    """
    ps = []
    if h.get("deuda_total"):
        ps.append(_t("pregunta.cobranza", idioma))
    if h.get("deuda_por_segmento"):
        ps.append(_t("pregunta.segmento", idioma))
    if h.get("pct_mora_alta") is not None:
        ps.append(_t("pregunta.mora_alta", idioma))
    if h.get("deudores_alta_propension"):
        ps.append(_t("pregunta.equipo", idioma))
    if h.get("contactabilidad_promedio") is not None:
        ps.append(_t("pregunta.contactabilidad", idioma))
    return ps[:4]


def tablero(df: pd.DataFrame, idioma: str = IDIOMA_POR_DEFECTO) -> dict:
    """Todo lo que muestra la pantalla, sin llamar al modelo.

    Es determinístico a propósito: el tablero tiene que abrir y mostrar lo
    mismo siempre, haya o no proveedor de IA configurado. `idioma` cambia el
    texto y nada más: las mismas reglas producen las mismas tarjetas, en el
    mismo orden, en los tres idiomas.
    """
    h = hechos(df)
    return {
        "hechos": h,
        "advertencias": advertencias(h, idioma),
        "sugerencias": sugerencias(h, idioma),
        "acciones": acciones(h, idioma),
        "preguntas_sugeridas": preguntas_sugeridas(h, idioma),
        "ia_disponible": kllm.disponible(),
    }
