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


def configurado() -> bool:
    """¿Están cargados los datos reales? Si no, la demo corre igual pero no
    suena ningún teléfono — conviene decírselo a quien la va a dar."""
    return bool(kconfig.leer_extra("DEMO_VIVO_TELEFONO"))


def dias_mora(hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return max(0, (hoy - FECHA_ALTA).days)


def caso(hoy: date | None = None) -> dict:
    """El deudor del caso, con la misma forma que una fila de la cartera.

    Lo que es real: el nombre y los datos de contacto (si se configuraron), el
    monto y la fecha de alta. Todo lo demás —el score, el historial, el tramo—
    es sintético y está calculado para que el caso sea *demostrable*: una
    probabilidad de pago alta y un contacto que responde, porque el objetivo
    de la reunión es mostrar el circuito completo, no un caso perdido.
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
        "segmento": "Demostración",
        "tramo_mora": "temprana" if dias_mora(hoy) <= 90 else "media",
        "canal_preferido": "Llamada",
        "gestiones_previas": 0,
        "sintetico": not configurado(),
    }


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
                 metodo: str = "mercadopago", empresa: str = "MV Kobra AI") -> dict:
    """Paso 3 — el link. Devuelve el pago creado y los datos para transferir.

    `metodo`: 'mercadopago' (el link que se paga con tarjeta o saldo) o
    'transferencia' (los datos de la cuenta, que el deudor informa después).
    """
    from kobra import portal_pagos
    pago = portal_pagos.crear_pago(
        dir_datos_tenant=dir_datos_tenant, empresa=empresa, id_deudor=ID_DEUDOR,
        monto=monto, metodo=metodo, total_deuda=MONTO_DEUDA)
    pago["destino"] = (f"{_dato('DEMO_VIVO_BANCO')} · {_dato('DEMO_VIVO_CUENTA')}"
                       if metodo == "transferencia" else "MercadoPago")
    return pago


def acreditar(dir_datos_tenant: str, referencia: str,
              metodo: str = "mercadopago") -> dict:
    """Paso 4 — entra la plata y se imputa sola.

    `mercadopago` entra como **aprobado** (el gateway ya confirmó); una
    transferencia entra como **informado** (la declaró el deudor y todavía
    la tiene que conciliar la empresa). Son dos estados distintos a propósito:
    mostrar una transferencia como cobrada antes de verla en el banco es
    exactamente el error que hace desconfiar a un gerente de cobranzas.
    """
    from kobra import portal_pagos
    estado = "aprobado" if metodo == "mercadopago" else "informado"
    return portal_pagos.confirmar_pago(dir_datos_tenant, referencia, estado)


def saldo(dir_datos_tenant: str) -> float:
    """Paso 5 — lo que queda. Después del pago de $U 100 sobre $U 200, esto
    devuelve 100.0, y ese número es el que se negocia."""
    from kobra import portal_pagos
    return portal_pagos.saldo_pendiente(dir_datos_tenant, ID_DEUDOR, MONTO_DEUDA)


def propuestas(saldo_actual: float) -> list[dict]:
    """Paso 6 — qué ofrecerle por la diferencia.

    Tres opciones, de la que más recupera a la que menos, que es el orden en
    que un gestor las pone sobre la mesa: primero el pago contado con un
    descuento chico, después las cuotas sin descuento, y recién al final el
    descuento grande. Los porcentajes son los del negociador del producto.
    """
    s = round(float(saldo_actual), 2)
    return [
        {"opcion": "Contado hoy", "monto": round(s * 0.95, 2), "cuotas": 1,
         "descuento": 5, "detalle": "5 % por cancelar en el día"},
        {"opcion": "2 cuotas", "monto": s, "cuotas": 2,
         "descuento": 0, "detalle": f"2 de $U {s / 2:.0f}, sin recargo"},
        {"opcion": "Contado con quita", "monto": round(s * 0.85, 2), "cuotas": 1,
         "descuento": 15, "detalle": "15 % — el piso, solo si no cierra por otra vía"},
    ]


def registrar_acuerdo(monto_acordado: float, cuotas: int = 1,
                      descuento: float = 0.0, fecha_compromiso: str = "",
                      notas: str = "") -> dict:
    """Paso 7 — queda la promesa registrada, con su fecha de compromiso.

    A partir de acá el caso entra al seguimiento normal del producto: si la
    fecha pasa sin el pago, aparece en promesas incumplidas como cualquier
    otro deudor.
    """
    from kobra import registro
    return registro.registrar_gestion(
        id_deudor=ID_DEUDOR, gestor_id="IA01", canal="Llamada",
        resultado="Promesa", tipo_gestor="IA",
        monto_acordado=monto_acordado, cuotas=cuotas, descuento=descuento,
        fecha_compromiso=fecha_compromiso,
        notas=notas or "Acuerdo cerrado en demostración en vivo.")


# ---------------------------------------------------------------------------
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
    else:
        d = caso()
        print(f"Caso de demostración · {d['nombre']} · "
              f"$U {d['monto_deuda']:.0f} · {d['dias_mora']} días de mora")
        print(f"Contacto: {d['telefono']} · {d['email']}")
        if d["sintetico"]:
            print("\n(!) Datos sintéticos: no va a sonar ningún teléfono.\n"
                  "    Cargá los reales con: python -m kobra.demo_vivo --configurar")
