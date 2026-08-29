# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Vocabulario del producto en los tres idiomas
===========================================================
Traducir las pantallas no alcanza para que el programa esté en otro idioma:
buena parte de lo que se lee son VALORES de la cartera —la estrategia
recomendada, el resultado de una gestión, el segmento de propensión— y esos
valores los escribe el propio producto en castellano cuando scorea.

Con la interfaz en portugués, la tabla de cartera mostraba encabezados en
portugués y celdas que decían "Recordatorio suave" e "Individuo". Este módulo
traduce ESAS celdas al vuelo, al momento de servirlas.

Qué se traduce y qué no
-----------------------
Solo el vocabulario que **genera Kobra**: estrategias, prioridades, canales,
resultados de gestión, emociones, tramos de mora, tipo de gestor. Lo que el
cliente subió con su cartera —el nombre del deudor, su producto, su
departamento— NO se toca: son sus datos, no nuestro vocabulario, y traducirlos
sería inventarle otra base. Los del escenario de DEMO sí se traducen, porque
esos también los generamos nosotros y de eso se trata mostrar el producto en
el idioma del que mira.

La traducción es por valor exacto: lo que no está en el catálogo pasa igual,
sin romper nada. Ese es el punto — una cartera real trae valores que no
conocemos y tienen que llegar intactos a la pantalla.
"""
from __future__ import annotations

IDIOMAS = ("es", "pt", "en")

# Valor en castellano → traducción. Agrupado por concepto para que se lea, pero
# se resuelve como un solo diccionario plano: los valores no se repiten entre
# columnas y así una columna nueva no obliga a tocar el código.
_CATALOGO: dict[str, dict[str, str]] = {
    # --- Estrategia recomendada por el negociador --------------------------
    "Recordatorio suave": {"pt": "Lembrete leve", "en": "Gentle reminder"},
    "Pago total facilitado": {"pt": "Pagamento total facilitado",
                              "en": "Assisted full payment"},
    "Plan de cuotas": {"pt": "Plano de parcelas", "en": "Instalment plan"},
    "Plan de cuotas + quita moderada": {
        "pt": "Plano de parcelas + desconto moderado",
        "en": "Instalment plan + moderate write-off"},
    "Descuento máximo / cierre de cuenta": {
        "pt": "Desconto máximo / encerramento da conta",
        "en": "Maximum discount / account closure"},
    "Derivación": {"pt": "Encaminhamento", "en": "Escalation"},
    "Derivación a gestión especializada": {
        "pt": "Encaminhamento para atendimento especializado",
        "en": "Escalation to specialist collections"},
    "Quita agresiva por pago único": {
        "pt": "Desconto agressivo por pagamento único",
        "en": "Aggressive write-off for a single payment"},
    # --- Segmento de propensión y prioridad --------------------------------
    "Alta": {"pt": "Alta", "en": "High"},
    "Media": {"pt": "Média", "en": "Medium"},
    "Baja": {"pt": "Baixa", "en": "Low"},
    # --- Canales -----------------------------------------------------------
    "Llamada": {"pt": "Ligação", "en": "Call"},
    "WhatsApp": {"pt": "WhatsApp", "en": "WhatsApp"},
    "Email": {"pt": "E-mail", "en": "Email"},
    "Portal": {"pt": "Portal", "en": "Portal"},
    # --- Resultado de una gestión ------------------------------------------
    "Pago": {"pt": "Pagamento", "en": "Payment"},
    "Promesa": {"pt": "Promessa", "en": "Promise"},
    "Arreglo de pago": {"pt": "Acordo de pagamento", "en": "Payment arrangement"},
    "Sin acuerdo": {"pt": "Sem acordo", "en": "No agreement"},
    "Informado": {"pt": "Informado", "en": "Informed"},
    "No contactado": {"pt": "Não contatado", "en": "Not reached"},
    "Número erróneo": {"pt": "Número errado", "en": "Wrong number"},
    "Fallecido": {"pt": "Falecido", "en": "Deceased"},
    # --- Quién gestionó ----------------------------------------------------
    "Humano": {"pt": "Humano", "en": "Human"},
    "IA": {"pt": "IA", "en": "AI"},
    # --- Emoción dominante detectada en la conversación --------------------
    "intencion_pago": {"pt": "intenção de pagamento", "en": "intent to pay"},
    "neutro": {"pt": "neutro", "en": "neutral"},
    "ansiedad": {"pt": "ansiedade", "en": "anxiety"},
    "objecion": {"pt": "objeção", "en": "objection"},
    "frustracion": {"pt": "frustração", "en": "frustration"},
    "enojo": {"pt": "raiva", "en": "anger"},
    "dificultad_economica": {"pt": "dificuldade financeira",
                             "en": "financial hardship"},
    # --- Segmento de la cartera de demostración ----------------------------
    "Individuo": {"pt": "Pessoa física", "en": "Individual"},
    "Pyme": {"pt": "PME", "en": "SMB"},
    "Demostración": {"pt": "Demonstração", "en": "Demonstration"},
    # --- Calidad del dato ---------------------------------------------------
    "estimada": {"pt": "estimada", "en": "estimated"},
    "provista": {"pt": "fornecida", "en": "provided"},
    # --- Producto de la cartera sintética ----------------------------------
    # Va acá y no en "datos del cliente" porque esta cartera la generamos
    # nosotros para la demo: es vocabulario nuestro mientras se está mirando
    # el escenario de demostración.
    "Préstamo personal": {"pt": "Empréstimo pessoal", "en": "Personal loan"},
    "Tarjeta": {"pt": "Cartão", "en": "Credit card"},
    "Consumo": {"pt": "Consumo", "en": "Consumer credit"},
    "Crédito comercial": {"pt": "Crédito comercial", "en": "Commercial credit"},
}

# Columnas que se traducen cuando la respuesta sale hacia la pantalla. Están
# nombradas una por una a propósito: traducir "toda columna de texto" tocaría
# el nombre del deudor y sus notas.
COLUMNAS_TRADUCIBLES = (
    "estrategia", "segmento_propension", "canal_recomendado", "canal",
    "canal_preferido", "resultado", "tipo_gestor", "emocion_dominante",
    "segmento", "producto", "calidad_datos",
)


def valor(texto, idioma: str = "es"):
    """Un valor del vocabulario en `idioma`. Lo desconocido pasa intacto."""
    if idioma == "es" or not isinstance(texto, str):
        return texto
    return _CATALOGO.get(texto, {}).get(idioma, texto)


def traducir(df, idioma: str = "es", columnas=None):
    """Copia del DataFrame con el vocabulario del producto en `idioma`.

    No modifica el original: lo que se guarda en disco sigue en castellano —
    una sola verdad en los datos— y la traducción vive el tiempo que dura la
    respuesta HTTP. Si mañana el cliente cambia de idioma, sus archivos no
    cambian.
    """
    if idioma == "es" or df is None or getattr(df, "empty", True):
        return df
    salida = df.copy()
    for col in (columnas or COLUMNAS_TRADUCIBLES):
        if col in salida.columns:
            salida[col] = salida[col].map(lambda v: valor(v, idioma))
    return salida
