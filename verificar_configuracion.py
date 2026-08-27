#!/usr/bin/env python3
# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Qué falta configurar para poder vender
=====================================================
Dice, en un comando, qué variables están puestas y qué se rompe exactamente
sin cada una de las que faltan.

Por qué existe: las cuatro cosas que bloquean una venta —cobrar, firmar la
licencia, mandarla y dejar bajar el instalador— fallan de formas distintas y
ninguna grita. Sin `RESEND_FROM` el comprador no recibe nada y desde el lado
del dueño se ve todo bien, porque a él sí le llegó la copia. Sin
`RELEASES_TOKEN` el cliente paga y se queda sin producto. Descubrir eso con un
cliente adentro es caro; descubrirlo con este script no cuesta nada.

    python3 verificar_configuracion.py            # lee el entorno y .env
    python3 verificar_configuracion.py --todas    # incluye las opcionales

NUNCA imprime el valor de una variable, ni siquiera parcial: este script se
corre compartiendo pantalla y su salida se pega en un chat.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# (variable, para qué, qué pasa si falta)
CRITICAS = [
    ("MP_ACCESS_TOKEN", "Crear la preferencia de pago en MercadoPago",
     "El checkout devuelve 503 y nadie puede comprar."),
    ("KOBRA_LICENSE_PRIVATE_KEY", "Firmar la licencia RS256 del comprador",
     "El pago entra y NO se emite licencia: el cliente paga y no puede activar."),
    ("RESEND_API_KEY", "Mandar la licencia al comprador y los avisos al dueño",
     "La licencia se emite y queda solo en el log. No se entera nadie."),
    ("RESEND_FROM", "Remitente propio, con el dominio verificado en Resend",
     "Los mails salen del remitente de prueba, que SOLO entrega a tu casilla: "
     "al comprador no le llega y vos lo ves bien porque te llegó la copia."),
    ("RELEASES_TOKEN", "Bajar el instalador desde el release privado",
     "Nadie puede descargar el producto aunque haya pagado."),
]

OPCIONALES = [
    ("KOBRA_BACKEND_ADMIN_TOKEN", "Panel/monitor de ventas",
     "El panel queda cerrado (que es lo correcto si no lo usás)."),
    ("ANTHROPIC_API_KEY", "Redacción del agente negociador",
     "Negocia con plantillas en vez de redactar."),
    ("OPENAI_API_KEY", "Transcripción de audio (Whisper)",
     "Sin transcripción en la nube."),
    ("ELEVENLABS_API_KEY", "Voz premium",
     "Usa las voces de Twilio/Polly, ya incluidas."),
    ("MP_CURRENCY", "Moneda de cobro", "Usa el default UYU."),
    ("MP_TASA_UYU", "Tipo de cambio de referencia", "Usa el default 40."),
]

# Las pone cada CLIENTE en su instalación, no el dueño en su servidor: que
# falten acá no es un problema. Se listan para que nadie las busque en Vercel.
DEL_CLIENTE = [
    ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM",
     "TWILIO_WHATSAPP_FROM", "PUBLIC_BASE_URL"),
]


def cargar_dotenv(ruta: str) -> dict:
    """Lee un `.env` sin dependencias. Solo `CLAVE=valor`, ignora comentarios.

    No usa python-dotenv a propósito: este script tiene que correr en una
    máquina recién clonada, antes de instalar nada.
    """
    valores = {}
    if not os.path.exists(ruta):
        return valores
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valor = valor.strip().strip('"').strip("'")
            if valor:
                valores[clave.strip()] = valor
    return valores


def esta_puesta(nombre: str, extra: dict) -> bool:
    return bool((os.environ.get(nombre) or extra.get(nombre) or "").strip())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--todas", action="store_true",
                   help="mostrar también las opcionales que ya están puestas")
    a = p.parse_args(argv)

    ruta_env = os.path.join(ROOT, ".env")
    extra = cargar_dotenv(ruta_env)
    origen = f" (+ {os.path.basename(ruta_env)})" if extra else ""
    print(f"\n  Configuración de MV Kobra AI — entorno{origen}\n")

    faltan = []
    print("  PARA VENDER")
    for nombre, para, sin in CRITICAS:
        ok = esta_puesta(nombre, extra)
        print(f"   {'[ok]  ' if ok else '[FALTA]'} {nombre:<28} {para}")
        if not ok:
            faltan.append((nombre, sin))

    print("\n  OPCIONALES")
    for nombre, para, sin in OPCIONALES:
        ok = esta_puesta(nombre, extra)
        if ok and not a.todas:
            continue
        print(f"   {'[ok]  ' if ok else '[  -  ]'} {nombre:<28} {para}")
        if not ok:
            print(f"           -> {sin}")

    print("\n  LAS PONE CADA CLIENTE EN SU INSTALACIÓN (no van en tu servidor)")
    print("   " + ", ".join(DEL_CLIENTE[0]))
    print("   Modelo BYO: la cuenta de Twilio es del cliente y Twilio le "
          "factura a él.")

    if faltan:
        print(f"\n  {len(faltan)} de {len(CRITICAS)} sin configurar. Qué pasa "
              "hoy si alguien intenta comprar:\n")
        for nombre, sin in faltan:
            print(f"   · {nombre}\n     {sin}")
        print("\n  Dónde se cargan: Vercel -> Project -> Settings -> "
              "Environment Variables (Production),")
        print("  y REDESPLEGAR después. El paso a paso está en "
              "docs/PUESTA_EN_PRODUCCION_VERCEL.md\n")
        return 1

    print("\n  Todo lo necesario para vender está configurado.")
    print("  Probalo sin gastar: tocá Comprar en la landing y confirmá que "
          "llega el mail de intención.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
