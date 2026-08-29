# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Caso de demostración en vivo
============================================
Un deudor de verdad —con un teléfono que suena y un WhatsApp que llega— para
mostrarle a un cliente, en una reunión, que esto no es un video: el agente
**llama**, **negocia**, **escribe**, **manda el link**, **cobra** y **registra
el acuerdo**. De punta a punta, delante de él.

El guion de la demostración
---------------------------
1. El agente llama al teléfono del caso y negocia por voz.
2. Le escribe por WhatsApp con la propuesta.
3. Le manda un link de pago (MercadoPago o transferencia).
4. Se paga una parte — $U 100 sobre una deuda de $U 200.
5. El pago se imputa, y queda un **saldo de $U 100**.
6. Sobre ese saldo se negocia la diferencia y se registra la promesa.

El paso 4 es el que convence: el cliente ve entrar la plata y ve el saldo
bajar solo. Por eso el caso tiene una deuda chica y redonda ($U 200): la mitad
es un pago real de $U 100, que cuesta poco hacer en una reunión y se puede
repetir en cada demostración sin pensarlo.

Dónde están los datos de contacto (y por qué no acá)
-----------------------------------------------------
El teléfono, el mail y la cuenta bancaria **no están en este archivo**. Este
repositorio es público: un número de celular escrito acá queda indexado por
Google y lo levantan los bots que rastrean GitHub buscando justamente eso. Y
la regla del proyecto es que el código no lleva datos personales (CLAUDE.md,
Ley 18.331).

Así que salen de la configuración cifrada de la máquina donde corre la demo
(`kobra/config.py` → keyring del sistema o archivo cifrado, siempre fuera del
repo). Se cargan una sola vez:

    python -m kobra.demo_vivo --configurar

Sin configurar, el caso existe igual con datos sintéticos y todo el flujo se
puede recorrer —el link de pago, el saldo, la promesa—; lo único que no pasa
es que suene un teléfono real.

En qué idioma
-------------
`caso`, `guion` y `propuestas` toman `idioma` ("es" | "pt" | "en"), porque la
demostración se da también en Brasil y afuera, y leerle a un cliente una
pantalla en castellano mientras se le habla en su idioma arruina el efecto.
Cambia el texto, nunca los números: el caso es el mismo caso.
"""
from __future__ import annotations

from datetime import date

from kobra import config as kconfig

# Identificador del caso. Se elige distinto de los del dataset sintético para
# que nunca colisione con un deudor generado.
ID_DEUDOR = "DEMO-VIVO-001"

# La deuda del caso. Chica y redonda a propósito: la mitad es un pago real que
# se hace en una reunión sin pensarlo dos veces.
MONTO_DEUDA = 200.0
PAGO_DEMO = 100.0
FECHA_ALTA = date(2026, 1, 1)
MONEDA = "UYU"

# Claves donde se guardan los datos de contacto — en el backend seguro de
# `kobra.config` (keyring / archivo cifrado), nunca en el repositorio.
CLAVES = {
    "DEMO_VIVO_NOMBRE": "Nombre del deudor de la demostración",
    "DEMO_VIVO_TELEFONO": "Teléfono al que va a llamar el agente (formato +598…)",
    "DEMO_VIVO_EMAIL": "Correo del deudor de la demostración",
    "DEMO_VIVO_BANCO": "Banco para la transferencia (ej. Itaú)",
    "DEMO_VIVO_CUENTA": "Cuenta para la transferencia (ej. caja de ahorro …)",
}

# Valores sintéticos: los que trae el repo cuando nadie configuró nada. El
# teléfono usa el rango 555 reservado para ficción, para que no exista.
_SINTETICO = {
    "DEMO_VIVO_NOMBRE": "Deudor de Demostración",
    "DEMO_VIVO_TELEFONO": "+598 99 555 000",
    "DEMO_VIVO_EMAIL": "demo@ejemplo.invalid",
    "DEMO_VIVO_BANCO": "Banco de Demostración",
    "DEMO_VIVO_CUENTA": "caja de ahorro 0000000",
}


def _dato(clave: str) -> str:
    return (kconfig.leer_extra(clave) or _SINTETICO[clave]).strip()


# ---------------------------------------------------------------------------
# Catálogo de textos de la demostración
# ---------------------------------------------------------------------------
# Los tres idiomas del producto; el castellano es el piso cuando falta una
# traducción, porque quedarse sin el guion en medio de una reunión es peor que
# leer una línea en el idioma de al lado.
IDIOMAS = ("es", "pt", "en")
IDIOMA_DEFAULT = "es"

# Todo el texto que se proyecta en la reunión sale de acá, por clave y con
# plantilla. Los importes y las fechas se formatean en Python y entran ya
# hechos, para que traducir no le cambie el formato a la plata.
_TEXTOS = {
    # --- Etiquetas del caso ---
    "segmento": {"es": "Demostración", "pt": "Demonstração",
                 "en": "Demonstration"},
    "tramo.temprana": {"es": "temprana", "pt": "inicial", "en": "early"},
    "tramo.media": {"es": "media", "pt": "média", "en": "mid"},
    "sin_telefono": {
        "es": "(falta el teléfono)",
        "pt": "(falta o telefone)",
        "en": "(the phone number is missing)",
    },

    # --- Los seis pasos ---
    "canal.llamada": {"es": "Llamada", "pt": "Ligação", "en": "Call"},
    "canal.whatsapp": {"es": "WhatsApp", "pt": "WhatsApp", "en": "WhatsApp"},
    "canal.portal": {"es": "Portal", "pt": "Portal", "en": "Portal"},
    "canal.cobro": {"es": "Cobro", "pt": "Cobrança", "en": "Payment"},
    "canal.registro": {"es": "Registro", "pt": "Registro", "en": "Log"},

    "paso1.titulo": {
        "es": "El agente llama y negocia",
        "pt": "O agente liga e negocia",
        "en": "The agent calls and negotiates",
    },
    "paso1.detalle": {
        "es": "Disca a {tel} y se presenta: deuda de {moneda} {monto} "
              "vencida el {vencimiento}, {dias} días de mora.",
        "pt": "Disca para {tel} e se apresenta: dívida de {moneda} {monto} "
              "vencida em {vencimiento}, {dias} dias de atraso.",
        "en": "Dials {tel} and introduces itself: a {moneda} {monto} debt "
              "due on {vencimiento}, {dias} days in arrears.",
    },
    "paso2.titulo": {
        "es": "Le escribe con la propuesta",
        "pt": "Escreve com a proposta",
        "en": "It writes with the offer",
    },
    "paso2.detalle": {
        "es": "Cierra la llamada y le manda el WhatsApp con el link de pago, "
              "con la plantilla aprobada por Meta.",
        "pt": "Encerra a ligação e manda o WhatsApp com o link de pagamento, "
              "com o modelo aprovado pela Meta.",
        "en": "Ends the call and sends the WhatsApp with the payment link, "
              "using the template approved by Meta.",
    },
    "paso3.titulo": {
        "es": "El link de pago",
        "pt": "O link de pagamento",
        "en": "The payment link",
    },
    "paso3.detalle": {
        "es": "{moneda} {pago} a cuenta, por MercadoPago o transferencia. "
              "Se puede pagar escaneando el QR.",
        "pt": "{moneda} {pago} por conta, por MercadoPago ou transferência. "
              "Dá para pagar escaneando o QR.",
        "en": "{moneda} {pago} on account, by MercadoPago or bank transfer. "
              "It can be paid by scanning the QR code.",
    },
    "paso4.titulo": {
        "es": "Entra la plata",
        "pt": "O dinheiro entra",
        "en": "The money comes in",
    },
    "paso4.detalle": {
        "es": "El pago se verifica contra MercadoPago y se imputa. Este es "
              "el paso que convence: el cliente ve el saldo bajar solo.",
        "pt": "O pagamento é verificado no MercadoPago e é lançado. Este é o "
              "passo que convence: o cliente vê o saldo cair sozinho.",
        "en": "The payment is verified against MercadoPago and posted. This "
              "is the step that convinces: the customer watches the balance "
              "drop on its own.",
    },
    "paso5.titulo": {
        "es": "Queda la promesa",
        "pt": "Fica a promessa",
        "en": "The payment promise is logged",
    },
    "paso5.detalle": {
        "es": "Sobre los {moneda} {saldo} que quedan se acuerda "
              "el saldo y la fecha, y entra al seguimiento.",
        "pt": "Sobre os {moneda} {saldo} que restam combina-se o saldo e a "
              "data, e o caso entra no acompanhamento.",
        "en": "On the {moneda} {saldo} still outstanding, the balance and the "
              "date are agreed and the case enters follow-up.",
    },
    "paso6.titulo": {
        "es": "Se negocia la diferencia",
        "pt": "Negocia-se a diferença",
        "en": "The difference gets negotiated",
    },
    "paso6.detalle": {
        "es": "Contado con descuento chico, cuotas sin recargo, o el tope "
              "del 15 % — en ese orden, que es como se ponen sobre la mesa.",
        "pt": "À vista com desconto pequeno, parcelas sem acréscimo, ou o "
              "teto de 15 % — nessa ordem, que é como se colocam na mesa.",
        "en": "Lump sum with a small discount, instalments with no surcharge, "
              "or the 15 % cap — in that order, which is how they go on the "
              "table.",
    },

    # --- Las tres propuestas por la diferencia ---
    "propuesta.contado.opcion": {
        "es": "Contado hoy", "pt": "À vista hoje", "en": "Lump sum today",
    },
    "propuesta.contado.detalle": {
        "es": "5 % por cancelar en el día",
        "pt": "5 % por quitar no mesmo dia",
        "en": "5 % for settling the same day",
    },
    "propuesta.cuotas.opcion": {
        "es": "2 cuotas", "pt": "2 parcelas", "en": "2 instalments",
    },
    "propuesta.cuotas.detalle": {
        "es": "2 de $U {mitad}, sin recargo",
        "pt": "2 de $U {mitad}, sem acréscimo",
        "en": "2 of $U {mitad}, no surcharge",
    },
    "propuesta.quita.opcion": {
        "es": "Contado con quita",
        "pt": "À vista com desconto",
        "en": "Lump sum with write-off",
    },
    "propuesta.quita.detalle": {
        "es": "15 % — el piso, solo si no cierra por otra vía",
        "pt": "15 % — o piso, só se não fechar de outra forma",
        "en": "15 % — the floor, only if it does not close any other way",
    },

    # --- El registro del acuerdo ---
    "acuerdo.notas": {
        "es": "Acuerdo cerrado en demostración en vivo.",
        "pt": "Acordo fechado em demonstração ao vivo.",
        "en": "Agreement closed in the live demo.",
    },
}


def _norm(idioma: str) -> str:
    """Normaliza lo que manda la pantalla ("pt-BR", "EN", None) a la clave.

    El selector del sitio usa etiquetas de navegador, no las dos letras del
    catálogo: sin esto, elegir portugués devolvía la demostración en
    castellano.
    """
    corto = str(idioma or "").strip().lower()[:2]
    return corto if corto in IDIOMAS else IDIOMA_DEFAULT


def _t(clave: str, idioma: str = IDIOMA_DEFAULT, **datos) -> str:
    """Resuelve un texto del catálogo, cayendo a castellano si falta la clave.

    Que falte una traducción no puede dejar un paso del guion en blanco: la
    pantalla se muestra delante de un cliente y el hueco se nota más que el
    idioma.
    """
    entrada = _TEXTOS.get(clave, {})
    plantilla = entrada.get(_norm(idioma)) or entrada.get(IDIOMA_DEFAULT, "")
    return plantilla.format(**datos) if datos else plantilla


def configurado() -> bool:
    """¿Están cargados los datos reales? Si no, la demo corre igual pero no
    suena ningún teléfono — conviene decírselo a quien la va a dar."""
    return bool(kconfig.leer_extra("DEMO_VIVO_TELEFONO"))


def dias_mora(hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return max(0, (hoy - FECHA_ALTA).days)


def caso(hoy: date | None = None, idioma: str = IDIOMA_DEFAULT) -> dict:
    """El deudor del caso, con la misma forma que una fila de la cartera.

    Lo que es real: el nombre y los datos de contacto (si se configuraron), el
    monto y la fecha de alta. Todo lo demás —el score, el historial, el tramo—
    es sintético y está calculado para que el caso sea *demostrable*: una
    probabilidad de pago alta y un contacto que responde, porque el objetivo
    de la reunión es mostrar el circuito completo, no un caso perdido.

    `idioma` traduce solo las dos etiquetas que se proyectan —el segmento y el
    tramo de mora—. `canal_preferido` no se traduce: no es un cartel, es el
    valor con el que después se elige por dónde contactar.
    """
    return {
        "id_deudor": ID_DEUDOR,
        "nombre": _dato("DEMO_VIVO_NOMBRE"),
        "telefono": _dato("DEMO_VIVO_TELEFONO"),
        "email": _dato("DEMO_VIVO_EMAIL"),
        "monto_deuda": MONTO_DEUDA,
        "moneda": MONEDA,
        "fecha_alta": FECHA_ALTA.isoformat(),
        "dias_mora": dias_mora(hoy),
        # Sintético de acá para abajo.
        "probpago": 0.78,
        "segmento": _t("segmento", idioma),
        "tramo_mora": _t("tramo.temprana" if dias_mora(hoy) <= 90 else "tramo.media",
                         idioma),
        "canal_preferido": "Llamada",
        "gestiones_previas": 0,
        "sintetico": not configurado(),
    }


def guion(hoy: date | None = None, idioma: str = IDIOMA_DEFAULT) -> list[dict]:
    """Los seis pasos, con lo que va a pasar en cada uno.

    Es el mismo guion del docstring, pero como datos: la pantalla lo muestra
    para que quien da la demostración pueda ir narrando sin acordarse de nada,
    y el orden de la pantalla sea el orden de la reunión.

    La fecha se escribe igual en los tres idiomas (%d/%m/%Y): es la que figura
    en el caso, y cambiarla según el idioma haría que el número proyectado no
    coincida con el que se está diciendo en voz alta.
    """
    d = caso(hoy, idioma)
    tel = d["telefono"] if not d["sintetico"] else _t("sin_telefono", idioma)
    saldo_tras = MONTO_DEUDA - PAGO_DEMO
    comun = {"moneda": MONEDA}
    return [
        {"orden": 1, "canal": _t("canal.llamada", idioma),
         "titulo": _t("paso1.titulo", idioma),
         "detalle": _t("paso1.detalle", idioma, tel=tel,
                       monto=f"{MONTO_DEUDA:.0f}",
                       vencimiento=FECHA_ALTA.strftime('%d/%m/%Y'),
                       dias=d["dias_mora"], **comun)},
        {"orden": 2, "canal": _t("canal.whatsapp", idioma),
         "titulo": _t("paso2.titulo", idioma),
         "detalle": _t("paso2.detalle", idioma)},
        {"orden": 3, "canal": _t("canal.portal", idioma),
         "titulo": _t("paso3.titulo", idioma),
         "detalle": _t("paso3.detalle", idioma, pago=f"{PAGO_DEMO:.0f}", **comun)},
        {"orden": 4, "canal": _t("canal.cobro", idioma),
         "titulo": _t("paso4.titulo", idioma),
         "detalle": _t("paso4.detalle", idioma)},
        {"orden": 5, "canal": _t("canal.registro", idioma),
         "titulo": _t("paso5.titulo", idioma),
         "detalle": _t("paso5.detalle", idioma, saldo=f"{saldo_tras:.0f}", **comun)},
        {"orden": 6, "canal": _t("canal.llamada", idioma),
         "titulo": _t("paso6.titulo", idioma),
         "detalle": _t("paso6.detalle", idioma)},
    ]


# ---------------------------------------------------------------------------
# Los pasos del guion. Cada uno delega en el módulo que ya hace ese trabajo en
# producción — acá no se reimplementa nada: si la demo funciona, es porque el
# producto funciona.
# ---------------------------------------------------------------------------
def llamar(base_url: str, hoy: date | None = None) -> dict:
    """Paso 1 — el teléfono suena. Llamada real vía Twilio."""
    from kobra import campana
    d = caso(hoy)
    return campana.iniciar_llamada(
        to=d["telefono"], id_deudor=ID_DEUDOR, monto=d["monto_deuda"],
        base_url=base_url)


def escribir_whatsapp(hoy: date | None = None) -> dict:
    """Paso 2 — le llega el WhatsApp.

    Va con la plantilla aprobada por Meta que el cliente ya tenga configurada
    (`TWILIO_WHATSAPP_CONTENT_SID`): sin una plantilla aprobada, WhatsApp no
    deja que una empresa inicie la conversación, y eso no se puede saltear
    desde acá.
    """
    from kobra import campana
    d = caso(hoy)
    return campana.enviar_whatsapp(
        to=d["telefono"],
        content_variables={"1": d["nombre"], "2": f"{d['monto_deuda']:.0f}"})


def link_de_pago(dir_datos_tenant: str, monto: float = PAGO_DEMO,
                 metodo: str = "mercadopago", empresa: str = "MV Kobra AI",
                 base_url: str = "") -> dict:
    """Paso 3 — el link. Devuelve el pago creado y a dónde mandar al deudor.

    Con `mercadopago`, el link sale de `portal_pagos.link_mercadopago`: si la
    empresa cargó su access token, es un **checkout con el monto exacto de
    esta deuda**, y si el token es `TEST-…`, el de sandbox — el único que
    acepta tarjetas ficticias, que es como se ensaya el cobro sin mover un
    peso. Antes acá el `destino` decía "MercadoPago" y nada más: un QR que
    apuntara a eso no llevaba a ninguna parte donde se pudiera pagar.
    """
    from kobra import portal_pagos
    cfg = portal_pagos.cargar_config(dir_datos_tenant)
    pago = portal_pagos.crear_pago(
        dir_datos_tenant=dir_datos_tenant, empresa=empresa, id_deudor=ID_DEUDOR,
        monto=monto, metodo=metodo, total_deuda=MONTO_DEUDA)
    if metodo == "transferencia":
        pago["destino"] = f"{_dato('DEMO_VIVO_BANCO')} · {_dato('DEMO_VIVO_CUENTA')}"
        pago["transferencia"] = {k: v for k, v in cfg["transferencia"].items()
                                 if k != "habilitado"}
    else:
        from kobra import mercadopago as kmp
        pago["url_pago"] = portal_pagos.link_mercadopago(
            cfg, pago["referencia"], pago["monto"],
            descripcion=f"Deuda {ID_DEUDOR}", base_url=base_url)
        pago["destino"] = "MercadoPago"
        pago["modo_prueba"] = kmp.es_credencial_de_prueba(
            cfg["mercadopago"].get("access_token", ""))
    return pago


def acreditar(dir_datos_tenant: str, referencia: str,
              payment_id: str = "") -> dict:
    """Paso 4 — entra la plata y se imputa. Con tres desenlaces posibles.

    Lo que decide cuál es: **si se pudo verificar**, no el medio de pago.
    Antes, un pago por MercadoPago entraba como `aprobado` por el solo hecho
    de ser de MercadoPago —"el gateway ya confirmó"—, pero nadie le preguntaba
    nada al gateway: alcanzaba con apretar el botón para dar por cobrada una
    deuda que nadie pagó. Es el mismo agujero que `portal_pagos` documenta
    como inaceptable en el portal público.

    * **Verificado y aprobado** → `aprobado`. Se le preguntó a MercadoPago por
      ese `payment_id` y coinciden estado, referencia y monto.
    * **Sin verificar** (transferencia, o sin `payment_id`/token) →
      `informado`: imputado pero pendiente de conciliar. Es lo honesto cuando
      nadie averiguó nada — una transferencia bancaria no se puede confirmar
      sin integrar el banco de la empresa.
    * **Verificado y NO aprobado** → no se imputa nada y el pago queda
      `pendiente`. Dejarlo en `informado` descontaría del saldo pese a que
      MercadoPago acaba de decir que ese pago no corresponde a esta deuda.
    """
    from kobra import portal_pagos
    cfg = portal_pagos.cargar_config(dir_datos_tenant)
    pago = next((p for p in portal_pagos.listar_pagos(dir_datos_tenant, ID_DEUDOR)
                 if p["referencia"] == referencia), None)
    if pago is None:
        raise KeyError(f"No existe el pago {referencia} para este caso.")

    estado, verificacion = "informado", None
    token = (cfg["mercadopago"].get("access_token") or "").strip()
    if payment_id and token and pago["metodo"] == "mercadopago":
        from kobra import mercadopago as kmp
        verificacion = kmp.verificar_pago(
            token, payment_id, referencia_esperada=referencia,
            monto_esperado=pago["monto"])
        if verificacion["aprobado"]:
            estado = "aprobado"
        else:
            return {**pago, "verificacion": verificacion,
                    "detalle": verificacion["detalle"]}

    registro = portal_pagos.confirmar_pago(dir_datos_tenant, referencia, estado,
                                           webhook_url=cfg["erp"]["webhook_url"])
    return {**registro, "verificacion": verificacion}


def saldo(dir_datos_tenant: str) -> float:
    """Paso 5 — lo que queda. Después del pago de $U 100 sobre $U 200, esto
    devuelve 100.0, y ese número es el que se negocia."""
    from kobra import portal_pagos
    return portal_pagos.saldo_pendiente(dir_datos_tenant, ID_DEUDOR, MONTO_DEUDA)


def propuestas(saldo_actual: float, idioma: str = IDIOMA_DEFAULT) -> list[dict]:
    """Paso 6 — qué ofrecerle por la diferencia.

    Tres opciones, de la que más recupera a la que menos, que es el orden en
    que un gestor las pone sobre la mesa: primero el pago contado con un
    descuento chico, después las cuotas sin descuento, y recién al final el
    descuento grande. Los porcentajes son los del negociador del producto.

    `idioma` traduce el nombre y el detalle de cada opción; los montos, las
    cuotas y los porcentajes son los mismos en los tres.
    """
    s = round(float(saldo_actual), 2)
    return [
        {"opcion": _t("propuesta.contado.opcion", idioma),
         "monto": round(s * 0.95, 2), "cuotas": 1,
         "descuento": 5, "detalle": _t("propuesta.contado.detalle", idioma)},
        {"opcion": _t("propuesta.cuotas.opcion", idioma), "monto": s, "cuotas": 2,
         "descuento": 0,
         "detalle": _t("propuesta.cuotas.detalle", idioma, mitad=f"{s / 2:.0f}")},
        {"opcion": _t("propuesta.quita.opcion", idioma),
         "monto": round(s * 0.85, 2), "cuotas": 1,
         "descuento": 15, "detalle": _t("propuesta.quita.detalle", idioma)},
    ]


def registrar_acuerdo(monto_acordado: float, cuotas: int = 1,
                      descuento: float = 0.0, fecha_compromiso: str = "",
                      notas: str = "", idioma: str = IDIOMA_DEFAULT) -> dict:
    """Paso 7 — queda la promesa registrada, con su fecha de compromiso.

    A partir de acá el caso entra al seguimiento normal del producto: si la
    fecha pasa sin el pago, aparece en promesas incumplidas como cualquier
    otro deudor.

    `idioma` alcanza a la nota, que es lo único que después lee una persona.
    El canal y el resultado quedan como están: son las categorías con las que
    el registro agrupa las gestiones, y traducirlas partiría en tres los
    rankings de la pantalla de calidad.
    """
    from kobra import registro
    return registro.registrar_gestion(
        id_deudor=ID_DEUDOR, gestor_id="IA01", canal="Llamada",
        resultado="Promesa", tipo_gestor="IA",
        monto_acordado=monto_acordado, cuotas=cuotas, descuento=descuento,
        fecha_compromiso=fecha_compromiso,
        notas=notas or _t("acuerdo.notas", idioma))


# ---------------------------------------------------------------------------
def _ensayo(base_url: str = ""):
    """Recorre la demostración completa, parando en cada paso.

    Está pensado para el ensayo previo a la reunión: se corre una vez con el
    teléfono de uno propio, se comprueba que suene, que llegue el WhatsApp y
    que el pago con tarjeta de prueba se acredite, y recién ahí se muestra a
    un cliente. Cada paso dice qué falta si no se puede hacer, en vez de
    fallar en silencio.
    """
    import os

    from kobra import mercadopago as kmp
    from kobra import portal_pagos as kportal
    from kobra import rutas as krutas

    base_url = base_url or os.environ.get("PUBLIC_BASE_URL", "")
    d = caso()
    tenant = krutas.DIR_DATOS
    cfg = kportal.cargar_config(tenant)
    token_mp = (cfg["mercadopago"].get("access_token") or "").strip()

    print("=" * 66)
    print(f"  ENSAYO · {d['nombre']} · $U {d['monto_deuda']:.0f} · "
          f"{d['dias_mora']} días de mora")
    print(f"  Contacto: {d['telefono']}")
    print("=" * 66)
    if d["sintetico"]:
        print("\n(!) Datos SINTÉTICOS: no va a sonar ningún teléfono.")
        print("    python -m kobra.demo_vivo --configurar\n")

    print("\n[1/5] Llamada")
    if not base_url:
        print("  ✗ Falta PUBLIC_BASE_URL (la URL pública donde Twilio busca el webhook).")
    else:
        r = llamar(base_url)
        print(f"  {'✓ llamando…' if r['ok'] else '✗ ' + str(r['detalle'])}")

    print("\n[2/5] WhatsApp")
    r = escribir_whatsapp()
    print(f"  {'✓ enviado' if r['ok'] else '✗ ' + str(r.get('detalle'))}")

    print("\n[3/5] Link de pago")
    saldo_actual = saldo(tenant)
    if saldo_actual <= 0:
        print("  ✓ La deuda ya está cancelada — nada que cobrar.")
        return
    pago = link_de_pago(tenant, monto=min(PAGO_DEMO, saldo_actual),
                        metodo="mercadopago", base_url=base_url)
    url = kportal.link_mercadopago(cfg, pago["referencia"], pago["monto"],
                                   descripcion=f"Deuda {ID_DEUDOR}", base_url=base_url)
    print(f"  Referencia : {pago['referencia']}  ($U {pago['monto']:.0f})")
    print(f"  Link       : {url}")
    if kmp.es_credencial_de_prueba(token_mp):
        p = kmp.datos_de_prueba()
        print("\n  MODO PRUEBA — pagalo con una tarjeta ficticia:")
        for t in p["tarjetas"]:
            print(f"    · {t['marca']}: {t['numero']}  CVV {t['cvv']}  vence {t['vence']}")
        print(f"    · Titular: {p['titular']['aprobar']} (aprueba) / "
              f"{p['titular']['rechazar']} (rechaza)")
        print(f"    · Documento: {p['documento']['tipo']} {p['documento']['numero']}")
        print(f"    · {p['aviso']}")
    elif token_mp:
        print("\n  (!) Credenciales de PRODUCCIÓN: este cobro es REAL.")
    else:
        print("\n  (!) Sin access token de MercadoPago: el link no cobra de verdad.")
        print("      Cargá uno TEST-… en Portal de cobros para ensayar con tarjeta ficticia.")

    print("\n[4/5] Pagá el link (o escaneá el QR desde el portal) y volvé acá.")
    pid = input("  payment_id que devolvió MercadoPago (Enter para saltear): ").strip()
    if pid and token_mp:
        v = kmp.verificar_pago(token_mp, pid, referencia_esperada=pago["referencia"],
                               monto_esperado=pago["monto"])
        print(f"  MercadoPago dice: {v['estado']} · $U {v['monto']:.2f}")
        if v["aprobado"]:
            acreditar(tenant, pago["referencia"], payment_id=pid)
            print("  ✓ Verificado y acreditado.")
        else:
            print(f"  ✗ No se acredita: {v['detalle']}")
    else:
        print("  — salteado (el pago queda pendiente).")

    print("\n[5/5] Estado final")
    s = saldo(tenant)
    print(f"  Saldo: $U {s:.0f}")
    if s > 0:
        print("  Propuestas para la diferencia:")
        for o in propuestas(s):
            print(f"    · {o['opcion']:<22} $U {o['monto']:>7.0f}  {o['detalle']}")
    print()


def _configurar():
    """Carga los datos de contacto en el almacén cifrado de la máquina."""
    print(__doc__)
    print("\nDejá vacío para conservar lo que ya está guardado.\n")
    for clave, desc in CLAVES.items():
        actual = kconfig.leer_extra(clave)
        pista = f" [{actual}]" if actual else ""
        valor = input(f"{desc}{pista}: ").strip()
        if valor:
            kconfig.guardar_extra(clave, valor)
    print("\n[OK] Guardado fuera del repositorio "
          f"(backend: {kconfig.backend_activo()}).")


if __name__ == "__main__":
    import sys
    if "--configurar" in sys.argv:
        _configurar()
    elif "--ensayo" in sys.argv:
        _ensayo()
    else:
        d = caso()
        print(f"Caso de demostración · {d['nombre']} · "
              f"$U {d['monto_deuda']:.0f} · {d['dias_mora']} días de mora")
        print(f"Contacto: {d['telefono']} · {d['email']}")
        if d["sintetico"]:
            print("\n(!) Datos sintéticos: no va a sonar ningún teléfono.\n"
                  "    Cargá los reales con: python -m kobra.demo_vivo --configurar")
