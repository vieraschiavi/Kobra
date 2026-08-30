# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Agente IA Negociador
============================
Motor de decisión que, combinando ProbPago + tramo de mora + monto + canal,
recomienda para cada deudor:

    - estrategia            : la jugada de cobranza óptima
    - descuento_recomendado : % de quita sugerida
    - plan_cuotas           : nº de cuotas propuesto
    - canal_recomendado     : mejor canal de contacto
    - prioridad             : ranking operativo (1 = máxima)
    - valor_esperado_recupero (UYU) = probpago * monto * (1 - descuento)
    - guion                 : mensaje de negociación listo para enviar

El guion es un template parametrizado (sin nombres reales) que cualquier
gestor puede usar tal cual. Diseñado para maximizar recupero minimizando
la quita, priorizando por valor esperado.

Idiomas
-------
`recomendar(df, idioma=...)` devuelve la estrategia y el guion en castellano,
portugués de Brasil o inglés. Lo que cambia es de dónde sale la cadena: la
decisión —umbrales, descuentos, cuotas, prioridad— es exactamente la misma en
los tres, y el default sigue siendo castellano.
"""
import pandas as pd

# Los tres idiomas del producto. El castellano es el piso: si a una clave le
# falta la traducción se muestra en castellano, porque media pantalla en el
# idioma equivocado se lee mejor que un KeyError delante de un cliente.
IDIOMAS = ("es", "pt", "en")
IDIOMA_DEFAULT = "es"

# ---------------------------------------------------------------------------
# Catálogo de textos
# ---------------------------------------------------------------------------
# Todo lo que ve un gestor o un deudor sale de acá, por clave y con plantilla.
# El motor decide por CLAVE ("plan_cuotas"), nunca por la cadena que se
# muestra: si el guion se eligiera comparando el nombre de la estrategia,
# traducirlo dejaría a todo el mundo con el guion equivocado.
_TEXTOS = {
    # --- Nombre de la estrategia (columna `estrategia`) ---
    # Estos siete nombres tienen que decir lo mismo que el catálogo de
    # `kobra/vocabulario.py`, que traduce el valor ya escrito cuando la
    # cartera se sirve desde disco: dos redacciones distintas para la misma
    # estrategia se leen como dos estrategias distintas.
    "estrategia.recordatorio_suave": {
        "es": "Recordatorio suave",
        "pt": "Lembrete leve",
        "en": "Gentle reminder",
    },
    "estrategia.pago_total": {
        "es": "Pago total facilitado",
        "pt": "Pagamento total facilitado",
        "en": "Assisted full payment",
    },
    "estrategia.plan_cuotas": {
        "es": "Plan de cuotas",
        "pt": "Plano de parcelas",
        "en": "Instalment plan",
    },
    "estrategia.plan_cuotas_quita": {
        "es": "Plan de cuotas + quita moderada",
        "pt": "Plano de parcelas + desconto moderado",
        "en": "Instalment plan + moderate write-off",
    },
    "estrategia.quita_agresiva": {
        "es": "Quita agresiva por pago único",
        "pt": "Desconto agressivo por pagamento único",
        "en": "Aggressive write-off for a single payment",
    },
    "estrategia.derivacion": {
        "es": "Derivación a gestión especializada",
        "pt": "Encaminhamento para atendimento especializado",
        "en": "Escalation to specialist collections",
    },
    "estrategia.descuento_maximo": {
        "es": "Descuento máximo / cierre de cuenta",
        "pt": "Desconto máximo / encerramento da conta",
        "en": "Maximum discount / account closure",
    },

    # --- Guion de negociación (columna `guion`) ---
    # Es lo que el gestor le dice al deudor: en los tres idiomas tiene que
    # sonar a cobranza real —cordial y concreta—, no a traducción literal.
    "guion.saludo": {
        "es": "Hola, le escribimos de su gestor de cobranzas.",
        "pt": "Olá, aqui é a sua equipe de cobrança.",
        "en": "Hello, this is a message from your collections team.",
    },
    "guion.recordatorio_suave": {
        "es": "Notamos un saldo pendiente de $U {monto} (ref. {ref}). "
              "Regularizando hoy evita costos adicionales. "
              "¿Le enviamos el link de pago?",
        "pt": "Identificamos um saldo em aberto de $U {monto} (ref. {ref}). "
              "Regularizando hoje você evita custos adicionais. "
              "Podemos enviar o link de pagamento?",
        "en": "We noticed an outstanding balance of $U {monto} (ref. {ref}). "
              "Settling it today saves you extra charges. "
              "Shall we send you the payment link?",
    },
    "guion.pago_total": {
        "es": "Tiene un saldo de $U {monto}. Por pago de contado hoy le "
              "aplicamos un beneficio del {desc}, quedando en $U {monto_final}. "
              "¿Coordinamos el pago?",
        "pt": "Você tem um saldo de $U {monto}. Pagando à vista hoje, "
              "aplicamos um benefício de {desc} e fica em $U {monto_final}. "
              "Vamos combinar o pagamento?",
        "en": "You have a balance of $U {monto}. If you settle it in one "
              "payment today we apply a {desc} benefit, bringing it down to "
              "$U {monto_final}. Shall we arrange the payment?",
    },
    "guion.plan_cuotas": {
        "es": "Le ofrecemos regularizar su saldo de $U {monto} en {cuotas} "
              "cuotas de $U {cuota}{descuento}. "
              "¿Le queda cómodo comenzar este mes?",
        "pt": "Podemos regularizar o seu saldo de $U {monto} em {cuotas} "
              "parcelas de $U {cuota}{descuento}. "
              "Fica confortável começar neste mês?",
        "en": "We can settle your $U {monto} balance in {cuotas} instalments "
              "of $U {cuota}{descuento}. "
              "Would starting this month work for you?",
    },
    # Fragmento opcional: solo aparece cuando la estrategia trae quita.
    "guion.plan_cuotas_descuento": {
        "es": " con {desc} de descuento",
        "pt": " com {desc} de desconto",
        "en": " with a {desc} discount",
    },
    "guion.cierre": {
        "es": "Tenemos una oferta especial de cierre: pagando hoy "
              "$U {monto_final} ({desc} de descuento sobre $U {monto}) cancela "
              "toda su deuda. Es por tiempo limitado.",
        "pt": "Temos uma oferta especial de encerramento: pagando hoje "
              "$U {monto_final} ({desc} de desconto sobre $U {monto}) você "
              "quita toda a sua dívida. É por tempo limitado.",
        "en": "We have a special closing offer: pay $U {monto_final} today "
              "({desc} off your $U {monto} balance) and your debt is cleared "
              "in full. It is available for a limited time.",
    },
    "guion.derivacion": {
        "es": "Su caso (ref. {ref}, saldo $U {monto}) fue asignado a un gestor "
              "especializado que puede estructurar un plan de hasta {cuotas} "
              "cuotas. Le contactaremos para encontrar la mejor solución.",
        "pt": "O seu caso (ref. {ref}, saldo $U {monto}) foi encaminhado a um "
              "atendente especializado, que pode montar um plano de até "
              "{cuotas} parcelas. Entraremos em contato para encontrar a "
              "melhor solução.",
        "en": "Your case (ref. {ref}, balance $U {monto}) has been assigned to "
              "a specialist agent who can arrange a plan of up to {cuotas} "
              "instalments. We will be in touch to find the best solution.",
    },
}


def _norm(idioma: str) -> str:
    """Normaliza lo que llega de la pantalla ("pt-BR", "EN", None) a la clave.

    El selector del sitio manda etiquetas de navegador, no las tres letras que
    usa el catálogo: sin esto, elegir portugués devolvía castellano.
    """
    corto = str(idioma or "").strip().lower()[:2]
    return corto if corto in IDIOMAS else IDIOMA_DEFAULT


def _t(clave: str, idioma: str = IDIOMA_DEFAULT, **datos) -> str:
    """Resuelve un texto del catálogo y lo completa con los datos del deudor.

    Cae a castellano cuando al idioma pedido le falta la clave, para que sumar
    una frase nueva no rompa las pantallas en portugués e inglés hasta que
    alguien las traduzca.
    """
    entrada = _TEXTOS.get(clave, {})
    plantilla = entrada.get(_norm(idioma)) or entrada.get(IDIOMA_DEFAULT, "")
    return plantilla.format(**datos) if datos else plantilla


# Del nombre mostrado de vuelta a la clave, en cualquiera de los tres idiomas.
# Sirve para que `_guion` siga funcionando cuando le pasan una fila que ya
# tiene la estrategia resuelta (una cartera guardada, un brief armado a mano).
_CLAVE_POR_NOMBRE = {
    nombre: clave.split(".", 1)[1]
    for clave, trads in _TEXTOS.items() if clave.startswith("estrategia.")
    for nombre in trads.values()
}


def _decidir(prob, dias_mora, monto):
    """Decide la jugada según propensión y severidad de la mora.

    Devuelve la CLAVE de la estrategia, no su nombre: el resto del motor —el
    guion, sobre todo— se ramifica con esto, así que la decisión no depende
    del idioma en que se vaya a mostrar.
    """
    if prob >= 0.65:
        if dias_mora <= 30:
            return "recordatorio_suave", 0.00, 1
        return "pago_total", 0.05, 1
    if prob >= 0.35:
        if dias_mora <= 90:
            return "plan_cuotas", 0.10, 3
        return "plan_cuotas_quita", 0.20, 6
    # Baja propensión
    if dias_mora <= 90:
        return "quita_agresiva", 0.30, 1
    if monto >= 500_000:
        return "derivacion", 0.15, 12
    return "descuento_maximo", 0.45, 1


def _estrategia(prob, dias_mora, monto, idioma: str = IDIOMA_DEFAULT):
    """La jugada con su nombre ya mostrable, más descuento y cuotas."""
    clave, desc, cuotas = _decidir(prob, dias_mora, monto)
    return _t(f"estrategia.{clave}", idioma), desc, cuotas


def _canal(row):
    """Ajusta canal: alto valor -> contacto humano; resto -> canal preferido."""
    if row["monto_deuda"] >= 500_000 or row["segmento"] == "Corporativo":
        return "Llamada"
    return row["canal_preferido"]


def _guion_de(clave: str, row, idioma: str = IDIOMA_DEFAULT) -> str:
    """Arma el guion de una fila cuya estrategia ya se decidió.

    Los importes se formatean acá y entran a la plantilla como texto ya hecho:
    así el número se ve igual en los tres idiomas y la traducción no puede
    cambiarle el formato a la plata.
    """
    desc = row["descuento_recomendado"]
    cuotas = int(row["plan_cuotas"])
    monto = row["monto_deuda"]
    monto_final = monto * (1 - desc)
    cuota_val = monto_final / max(cuotas, 1)
    datos = {
        "ref": row["id_deudor"],
        "monto": f"{monto:,.0f}",
        "monto_final": f"{monto_final:,.0f}",
        "cuota": f"{cuota_val:,.0f}",
        "cuotas": cuotas,
        "desc": f"{desc:.0%}",
    }

    if clave in ("recordatorio_suave", "pago_total"):
        cuerpo = _t(f"guion.{clave}", idioma, **datos)
    elif clave in ("plan_cuotas", "plan_cuotas_quita"):
        # La quita se menciona solo si existe: "en 3 cuotas de $U 100 con 10 %
        # de descuento" contra "en 3 cuotas de $U 100" a secas.
        fragmento = (_t("guion.plan_cuotas_descuento", idioma, desc=datos["desc"])
                     if desc > 0 else "")
        cuerpo = _t("guion.plan_cuotas", idioma, descuento=fragmento, **datos)
    elif clave in ("quita_agresiva", "descuento_maximo"):
        cuerpo = _t("guion.cierre", idioma, **datos)
    else:  # derivación
        cuerpo = _t("guion.derivacion", idioma, **datos)
    return f"{_t('guion.saludo', idioma)} {cuerpo}"


def _guion(row, idioma: str = IDIOMA_DEFAULT) -> str:
    """El guion de una fila que ya trae la columna `estrategia` resuelta."""
    clave = _CLAVE_POR_NOMBRE.get(str(row["estrategia"]).strip(), "derivacion")
    return _guion_de(clave, row, idioma)


def recomendar(df: pd.DataFrame, idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Aplica el motor de negociación sobre una cartera ya scoreada (probpago).

    `idioma` ("es" | "pt" | "en") solo cambia el texto de `estrategia` y
    `guion`; los descuentos, las cuotas, el valor esperado y la prioridad son
    los mismos números en los tres.
    """
    out = df.copy()
    est = out.apply(
        lambda r: _decidir(r["probpago"], r["dias_mora"], r["monto_deuda"]),
        axis=1, result_type="expand")
    claves = est[0]
    out["estrategia"] = claves.map(lambda c: _t(f"estrategia.{c}", idioma))
    out["descuento_recomendado"] = est[1]
    out["plan_cuotas"] = est[2]
    out["canal_recomendado"] = out.apply(_canal, axis=1)

    out["valor_esperado_recupero"] = (
        out["probpago"] * out["monto_deuda"] * (1 - out["descuento_recomendado"]))
    # Prioridad operativa: máximo valor esperado primero
    out["prioridad"] = (
        out["valor_esperado_recupero"].rank(ascending=False, method="first").astype(int))
    # Por clave y no por el nombre ya traducido: el guion tiene que ser el
    # mismo en los tres idiomas, no depender de qué cadena quedó en la columna.
    out["guion"] = [_guion_de(clave, fila, idioma)
                    for clave, (_, fila) in zip(claves, out.iterrows())]
    return out


def resumen_estrategias(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("estrategia").agg(
        deudores=("id_deudor", "count"),
        cartera_uyu=("monto_deuda", "sum"),
        recupero_esperado_uyu=("valor_esperado_recupero", "sum"),
        probpago_prom=("probpago", "mean"),
        descuento_prom=("descuento_recomendado", "mean"),
    ).reset_index().sort_values("recupero_esperado_uyu", ascending=False)
    return g
