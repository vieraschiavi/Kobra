"""
MV Kobra AI · El caso de gestión que se muestra en vivo a un cliente
====================================================================
Un caso único y reproducible para sentarse frente a alguien y mostrar el ciclo
entero de cobranza: el gestor IA **llama por teléfono**, negocia, **escribe por
WhatsApp** con un link de pago, se **acredita un pago parcial**, queda
**registrada la promesa** por el saldo y se sigue negociando la diferencia.

A diferencia del resto de la demo —12.000 deudores sintéticos— este caso apunta
a una persona real: la que está haciendo la demostración. Es el punto. Que el
teléfono suene en la mesa y que el WhatsApp llegue mientras el cliente mira
convence más que cualquier captura.

Por qué los datos de contacto NO están acá
------------------------------------------
Este repositorio es **público**. Un teléfono y un mail commiteados quedan
indexados y se scrapean solos; un número de cuenta bancaria publicado es
directamente material de fraude. Así que el caso trae la deuda —que es
inventada— y toma el contacto de la configuración del equipo, igual que las
credenciales de Twilio:

    DEMO_NOMBRE     Cómo se llama quien recibe la llamada
    DEMO_TELEFONO   En formato E.164, con país: +598…
    DEMO_EMAIL      Para el comprobante

Se cargan desde ⚙️ Configuración o como variables de entorno, y se guardan en
el keyring del sistema (ver `kobra/config.py`). Sin ellos el caso igual se
arma y se puede recorrer en modo ensayo: lo único que no pasa es que suene un
teléfono.

La cuenta bancaria a la que se acredita tampoco vive acá: es la config del
portal de cobros (`portal_pagos.cargar_config` → sección `transferencia`), que
se guarda en la carpeta de datos del tenant y nunca se commitea.

Los dos modos
-------------
`ejecutar(modo="ensayo")` es el default y **no toca nada externo**: no llama, no
manda WhatsApp y no mueve plata. Devuelve el mismo guion paso a paso, para
poder ensayar la demo, correrla en tests y mostrarla sin gastar un peso.

`ejecutar(modo="real")` sí disca, sí escribe y sí genera el cobro. Es explícito
a propósito: una función que hace sonar el teléfono de alguien no puede
dispararse por accidente desde un import.

Uso:
    python -m kobra.caso_demo            # ensayo, imprime el guion
    python -m kobra.caso_demo --real     # llama y escribe de verdad
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime

# El caso: la deuda es inventada, chica y fácil de contar en voz alta.
ID_DEUDOR = "DEMO-MV-001"
EMPRESA_DEMO = "demo"
MONEDA = "UYU"
DEUDA_TOTAL = 200.0
VENCIMIENTO = date(2026, 1, 1)

# Lo que se paga en el aire durante la demo. 100 de 200: la mitad entra ya y la
# otra mitad queda para negociar, que es justo lo que hay que mostrar.
PAGO_DEMO = 100.0


def _config() -> dict:
    """La config del equipo (keyring / archivo cifrado), con el entorno arriba.

    Se lee perezoso y sin romper: si `kobra.config` no está disponible —o no
    hay nada guardado— se cae al entorno, y si tampoco hay nada el caso queda
    sin contacto, que es un estado válido para el modo ensayo.
    """
    guardada: dict = {}
    try:
        from kobra import config as kconfig
        guardada = kconfig.cargar() or {}
    except Exception:
        pass

    def _val(clave: str) -> str:
        return (os.getenv(clave) or guardada.get(clave) or "").strip()

    return {c: _val(c) for c in ("DEMO_NOMBRE", "DEMO_TELEFONO", "DEMO_EMAIL")}


@dataclass
class Contacto:
    nombre: str = ""
    telefono: str = ""
    email: str = ""

    @property
    def completo(self) -> bool:
        """Si falta el teléfono no hay llamada ni WhatsApp que valga."""
        return bool(self.telefono)

    @property
    def nombre_visible(self) -> str:
        """Para mostrar. El campo crudo se deja vacío a propósito: si le
        pusiera el default acá, `faltantes()` nunca avisaría que no está
        configurado y la llamada saldría saludando a 'Titular de la demo'."""
        return self.nombre or "Titular de la demo"

    def faltantes(self) -> list[str]:
        return [clave for clave, valor in (("DEMO_NOMBRE", self.nombre),
                                           ("DEMO_TELEFONO", self.telefono),
                                           ("DEMO_EMAIL", self.email))
                if not valor]


def contacto() -> Contacto:
    c = _config()
    return Contacto(nombre=c["DEMO_NOMBRE"], telefono=c["DEMO_TELEFONO"],
                    email=c["DEMO_EMAIL"])


def dias_mora(hoy: date | None = None) -> int:
    """Días desde el vencimiento. Se calcula, no se hardcodea: un número fijo
    envejece y a los seis meses la demo muestra una mora que no da."""
    return max(((hoy or date.today()) - VENCIMIENTO).days, 0)


def tramo(dias: int) -> str:
    if dias <= 30:
        return "1-30"
    if dias <= 60:
        return "31-60"
    if dias <= 90:
        return "61-90"
    return "90+"


def brief(hoy: date | None = None) -> dict:
    """El brief que consume `SesionGestorIA`.

    Los valores que no son la deuda están elegidos a mano —no salen de un
    modelo— porque el caso tiene que dar SIEMPRE la misma negociación: una
    demo que cambia de guion entre una reunión y otra no se puede ensayar.
    La probabilidad de pago es alta a propósito: es alguien que quiere
    arreglar, así que la conversación termina en acuerdo y no en un corte.
    """
    d = dias_mora(hoy)
    return {
        "monto_deuda": DEUDA_TOTAL,
        "probpago": 0.72,
        "estrategia": "Plan de cuotas",
        "descuento_recomendado": 0.15,
        "plan_cuotas": 3,
        "segmento_propension": "Alta",
        "dias_mora": d,
        "tramo_mora": tramo(d),
        "moneda": MONEDA,
    }


def fila(hoy: date | None = None) -> dict:
    """La fila de cartera, con las columnas que usa el resto del sistema."""
    b = brief(hoy)
    c = contacto()
    return {
        "id_deudor": ID_DEUDOR,
        "nombre": c.nombre_visible,
        "telefono": c.telefono,
        "email": c.email,
        "monto_deuda": DEUDA_TOTAL,
        "moneda": MONEDA,
        "dias_mora": b["dias_mora"],
        "tramo_mora": b["tramo_mora"],
        "probpago": b["probpago"],
        "segmento_propension": b["segmento_propension"],
        "vencimiento": VENCIMIENTO.isoformat(),
    }


# ---------------------------------------------------------------------------
# El guion
# ---------------------------------------------------------------------------
@dataclass
class Paso:
    orden: int
    titulo: str
    detalle: str
    canal: str = ""
    ok: bool | None = None      # None = no se ejecutó (modo ensayo)
    datos: dict = field(default_factory=dict)


def guion(hoy: date | None = None) -> list[Paso]:
    """Los pasos, en orden, con los textos que se van a escuchar y leer."""
    c = contacto()
    b = brief(hoy)
    saldo = DEUDA_TOTAL - PAGO_DEMO
    cuotas = b["plan_cuotas"]
    desc = b["descuento_recomendado"]
    return [
        Paso(1, "Llamada del gestor IA",
             f"Kobra disca a {c.telefono or '(falta DEMO_TELEFONO)'} y se presenta: "
             f"deuda de {MONEDA} {DEUDA_TOTAL:.0f} vencida el "
             f"{VENCIMIENTO.strftime('%d/%m/%Y')}, {b['dias_mora']} días de mora. "
             "Negocia con la escalera de ofertas, sin pasarse del tope.",
             canal="Llamada"),
        Paso(2, "WhatsApp con el link de pago",
             f"Cierra la llamada y le escribe a {c.telefono or '(falta DEMO_TELEFONO)'} "
             "con el link del portal de cobros. El link es el mismo que usaría "
             "un deudor real: token firmado, sin cuenta previa.",
             canal="WhatsApp"),
        Paso(3, f"Pago a cuenta de {MONEDA} {PAGO_DEMO:.0f}",
             "Paga por el portal (MercadoPago o transferencia). Queda imputado "
             "en el registro conciliable y sale al ERP por webhook.",
             canal="Portal"),
        Paso(4, "Promesa por el saldo",
             f"Quedan {MONEDA} {saldo:.0f}. Se registra el acuerdo y la fecha "
             "comprometida: a partir de acá el seguimiento lo controla solo y "
             "avisa si se incumple.",
             canal="Registro"),
        Paso(5, "Negociación de la diferencia",
             f"Sobre esos {MONEDA} {saldo:.0f} el gestor ofrece hasta "
             f"{desc:.0%} de descuento al contado, o {cuotas} cuotas sin "
             "descuento. El tope no se puede pasar por diseño.",
             canal="Llamada"),
    ]


def ejecutar(modo: str = "ensayo", hoy: date | None = None,
             base_url: str = "", dir_datos: str = "") -> dict:
    """Corre el caso. En 'ensayo' (default) no toca nada externo.

    Devuelve `{"modo", "contacto_ok", "faltantes", "pasos", "resumen"}`.
    """
    if modo not in ("ensayo", "real"):
        raise ValueError("modo tiene que ser 'ensayo' o 'real'")

    c = contacto()
    pasos = guion(hoy)

    if modo == "ensayo":
        return {"modo": modo, "contacto_ok": c.completo,
                "faltantes": c.faltantes(), "pasos": pasos,
                "resumen": _resumen(hoy)}

    # --- modo real ---------------------------------------------------------
    # Se corta antes de empezar si falta el teléfono: arrancar la secuencia
    # para fallar en el paso 1 delante de un cliente es peor que no arrancar.
    if not c.completo:
        raise RuntimeError(
            "Falta DEMO_TELEFONO: sin número no hay llamada ni WhatsApp. "
            "Cargalo en ⚙️ Configuración o como variable de entorno.")

    from kobra import campana, portal_pagos, registro

    dir_datos = dir_datos or os.getcwd()
    secreto = os.getenv("KOBRA_PORTAL_SECRETO", "demo-secreto")
    cfg = portal_pagos.cargar_config(dir_datos)

    # 1) la llamada
    r = campana.iniciar_llamada(to=c.telefono, id_deudor=ID_DEUDOR,
                                monto=DEUDA_TOTAL, base_url=base_url)
    pasos[0].ok, pasos[0].datos = bool(r.get("ok")), r

    # 2) el WhatsApp con el link del portal
    token = portal_pagos.token_portal(secreto, EMPRESA_DEMO, ID_DEUDOR)
    link = f"{base_url.rstrip('/')}/portal?t={token}" if base_url else f"(portal)?t={token}"
    r = campana.enviar_whatsapp(
        to=c.telefono,
        content_variables={"1": c.nombre_visible, "2": f"{MONEDA} {DEUDA_TOTAL:.0f}", "3": link})
    pasos[1].ok, pasos[1].datos = bool(r.get("ok")), {**r, "link": link}

    # 3) el pago a cuenta
    pago = portal_pagos.crear_pago(dir_datos, EMPRESA_DEMO, ID_DEUDOR,
                                   monto=PAGO_DEMO, metodo="mercadopago")
    pasos[2].ok = bool(pago)
    pasos[2].datos = {**pago,
                      "link_mp": portal_pagos.link_mercadopago(
                          cfg, pago.get("referencia", ""), PAGO_DEMO)}

    # 4) la promesa por el saldo
    saldo = portal_pagos.saldo_pendiente(dir_datos, ID_DEUDOR, DEUDA_TOTAL)
    registro.registrar_gestion(id_deudor=ID_DEUDOR, gestor_id="IA01")
    pasos[3].ok, pasos[3].datos = True, {"saldo": saldo}

    # 5) la diferencia queda para la conversación, no la cierra el sistema
    pasos[4].ok = None

    return {"modo": modo, "contacto_ok": True, "faltantes": [],
            "pasos": pasos, "resumen": _resumen(hoy)}


def _resumen(hoy: date | None = None) -> dict:
    b = brief(hoy)
    return {
        "id_deudor": ID_DEUDOR,
        "deuda": DEUDA_TOTAL,
        "moneda": MONEDA,
        "vencimiento": VENCIMIENTO.isoformat(),
        "dias_mora": b["dias_mora"],
        "pago_demo": PAGO_DEMO,
        "saldo_tras_pago": DEUDA_TOTAL - PAGO_DEMO,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Caso de gestión para mostrar en vivo.")
    p.add_argument("--real", action="store_true",
                   help="Llama y escribe DE VERDAD (por defecto es ensayo).")
    p.add_argument("--base-url", default=os.getenv("KOBRA_BASE_URL", ""),
                   help="URL pública del servidor (para el webhook de voz y el portal).")
    a = p.parse_args(argv)

    r = ejecutar(modo="real" if a.real else "ensayo", base_url=a.base_url)
    s = r["resumen"]
    print(f"\n  Caso {s['id_deudor']} · {s['moneda']} {s['deuda']:.0f} "
          f"vencida el {datetime.fromisoformat(s['vencimiento']):%d/%m/%Y} "
          f"({s['dias_mora']} días de mora)")
    print(f"  Modo: {r['modo']}\n")
    for paso in r["pasos"]:
        marca = {True: "✓", False: "✗", None: "·"}[paso.ok]
        print(f"  {marca} {paso.orden}. [{paso.canal}] {paso.titulo}")
        print(f"      {paso.detalle}")
    if r["faltantes"]:
        print(f"\n  ⚠️  Falta configurar: {', '.join(r['faltantes'])}")
        print("      Se cargan en ⚙️ Configuración o como variables de entorno.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
