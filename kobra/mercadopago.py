# © 2026 Martín Viera. Todos los derechos reservados.

r"""
MV Kobra AI · MercadoPago para el pago del deudor
===================================================
Hasta acá, el "link de MercadoPago" del portal del deudor era una de dos
cosas: el link de pago **estático** que la empresa hubiera pegado en la
configuración, o uno **simulado** que no cobra nada. Ninguna de las dos sirve
para cobrar una deuda:

* un link estático tiene el monto fijo, y cada deudor debe un monto distinto;
* y el pago quedaba `informado` —declarado por el deudor, sin verificar—,
  porque marcarlo `aprobado` solo porque alguien dice que pagó permitiría a
  cualquiera con su token de acceso saldar su propia deuda sin pagar un peso.

Este módulo cierra las dos puntas contra la API de MercadoPago:

1. `crear_preferencia()` arma un **Checkout Pro** con el monto exacto de esa
   deuda y una `external_reference` que es la referencia del pago en el
   portal. Eso devuelve una URL a la que se puede llegar por link, por
   WhatsApp o escaneando un QR.
2. `verificar_pago()` vuelve a preguntarle a MercadoPago por ese pago y
   **compara la referencia y el monto** antes de que el portal lo impute. Es
   el mismo criterio que `api/verify-payment.js` usa antes de emitir una
   licencia: la única fuente de verdad sobre si entró la plata es MercadoPago,
   nunca el navegador del que paga.

Credenciales de prueba y tarjetas ficticias
--------------------------------------------
MercadoPago distingue los entornos por el prefijo del access token:
`TEST-…` es sandbox y `APP_USR-…` es producción. Con un token `TEST-`, este
módulo devuelve el `sandbox_init_point`, que es el checkout donde se paga con
las **tarjetas de prueba** —plata que no existe, pago que se acredita igual—.
Eso es exactamente lo que se necesita para ensayar la demostración completa,
incluido escanear el QR con el celular y pagar, sin mover un peso real.

Los números de las tarjetas de prueba salen del panel de MercadoPago de cada
cuenta (**Tus integraciones → Cuentas de prueba**), que es la fuente de
verdad: cambian por país y se actualizan. `datos_de_prueba()` devuelve los que
publica MercadoPago para Uruguay y Argentina, con esa aclaración incluida.

Sin `access_token` configurado nada de esto se activa y el portal sigue
comportándose como antes — link preconfigurado o simulado.
"""
from __future__ import annotations

import requests

API = "https://api.mercadopago.com"

# El prefijo que distingue una credencial de sandbox de una de producción.
PREFIJO_TEST = "TEST-"


def es_credencial_de_prueba(access_token: str) -> bool:
    return (access_token or "").strip().startswith(PREFIJO_TEST)


def crear_preferencia(access_token: str, referencia: str, monto: float,
                      descripcion: str, base_url: str = "",
                      moneda: str = "UYU", email_pagador: str = "",
                      timeout: int = 30) -> dict:
    """Crea el checkout de MercadoPago para una deuda concreta.

    Devuelve `{"ok", "url", "id", "es_prueba", "detalle"}`. `url` es el
    checkout al que hay que mandar al deudor: con credenciales de prueba es el
    `sandbox_init_point` (tarjetas ficticias), y con las de producción el
    `init_point` (plata real).

    `referencia` viaja como `external_reference` y es lo que después permite
    verificar que el pago que entró corresponde a ESTA deuda y no a otra.
    """
    token = (access_token or "").strip()
    if len(token) < 20:
        return {"ok": False, "url": "", "id": "", "es_prueba": False,
                "detalle": "Falta el access token de MercadoPago de la empresa."}
    try:
        monto = round(float(monto), 2)
    except (TypeError, ValueError):
        return {"ok": False, "url": "", "id": "", "es_prueba": False,
                "detalle": "Monto inválido."}
    if monto <= 0:
        return {"ok": False, "url": "", "id": "", "es_prueba": False,
                "detalle": "El monto tiene que ser mayor a cero."}

    base = (base_url or "").rstrip("/")
    pref = {
        "items": [{
            "title": descripcion or "Pago de deuda",
            "quantity": 1,
            "unit_price": monto,
            "currency_id": moneda,
        }],
        "external_reference": referencia,
    }
    if email_pagador:
        pref["payer"] = {"email": email_pagador}
    if base:
        # A dónde vuelve el deudor después de pagar. `auto_return` solo se
        # manda si hay `back_urls`: MercadoPago rechaza la preferencia entera
        # si se pide el retorno automático sin decirle a dónde volver.
        pref["back_urls"] = {
            "success": f"{base}/portal?pago={referencia}&estado=aprobado",
            "pending": f"{base}/portal?pago={referencia}&estado=pendiente",
            "failure": f"{base}/portal?pago={referencia}&estado=rechazado",
        }
        pref["auto_return"] = "approved"
        # Aviso server-to-server: llega aunque el deudor cierre la pestaña o
        # se quede sin señal al volver del pago.
        pref["notification_url"] = f"{base}/api/portal/mercadopago/aviso"

    try:
        r = requests.post(f"{API}/checkout/preferences",
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"},
                          json=pref, timeout=timeout)
        datos = r.json() if r.content else {}
    except Exception as e:
        return {"ok": False, "url": "", "id": "", "es_prueba": es_credencial_de_prueba(token),
                "detalle": f"No se pudo hablar con MercadoPago: {str(e)[:200]}"}

    if not r.ok:
        detalle = datos.get("message") or datos.get("error") or r.text[:200]
        return {"ok": False, "url": "", "id": "", "es_prueba": es_credencial_de_prueba(token),
                "detalle": f"MercadoPago rechazó la preferencia: {detalle}"}

    prueba = es_credencial_de_prueba(token)
    # Con credenciales de prueba se usa el sandbox: es el único checkout que
    # acepta las tarjetas ficticias. Si por algún motivo no viene, se cae al
    # init_point para no quedarse sin link.
    url = (datos.get("sandbox_init_point") or datos.get("init_point")) if prueba \
        else datos.get("init_point")
    if not url:
        return {"ok": False, "url": "", "id": datos.get("id", ""), "es_prueba": prueba,
                "detalle": "MercadoPago no devolvió el link de pago."}
    return {"ok": True, "url": url, "id": str(datos.get("id", "")),
            "es_prueba": prueba, "detalle": None}


def verificar_pago(access_token: str, payment_id: str,
                   referencia_esperada: str = "", monto_esperado: float | None = None,
                   timeout: int = 30) -> dict:
    """Le pregunta a MercadoPago por un pago y decide si se puede imputar.

    Devuelve `{"aprobado", "estado", "monto", "referencia", "detalle"}`.
    `aprobado` es True solo si MercadoPago dice `approved` **y** la referencia
    coincide con la esperada **y** el monto no es menor al esperado. Las tres
    condiciones importan:

    * sin comparar la referencia, un pago de $1 hecho a otra cosa serviría
      para saldar una deuda de $100.000 — basta con pasar su `payment_id`;
    * sin comparar el monto, pagar de menos saldaría el total;
    * y el estado lo dice MercadoPago, no el navegador del que paga.

    Se tolera un pago MAYOR al esperado (alguien que paga de más no debería
    quedar sin acreditar), pero nunca uno menor.
    """
    token = (access_token or "").strip()
    if len(token) < 20:
        return {"aprobado": False, "estado": "", "monto": 0.0, "referencia": "",
                "detalle": "Falta el access token de MercadoPago de la empresa."}
    if not str(payment_id or "").strip().isdigit():
        return {"aprobado": False, "estado": "", "monto": 0.0, "referencia": "",
                "detalle": "payment_id inválido."}
    try:
        r = requests.get(f"{API}/v1/payments/{payment_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
        datos = r.json() if r.content else {}
    except Exception as e:
        return {"aprobado": False, "estado": "", "monto": 0.0, "referencia": "",
                "detalle": f"No se pudo hablar con MercadoPago: {str(e)[:200]}"}
    if not r.ok:
        return {"aprobado": False, "estado": "", "monto": 0.0, "referencia": "",
                "detalle": f"MercadoPago respondió {r.status_code}."}

    estado = str(datos.get("status") or "")
    referencia = str(datos.get("external_reference") or "")
    try:
        monto = round(float(datos.get("transaction_amount") or 0), 2)
    except (TypeError, ValueError):
        monto = 0.0

    if referencia_esperada and referencia != referencia_esperada:
        return {"aprobado": False, "estado": estado, "monto": monto, "referencia": referencia,
                "detalle": "El pago corresponde a otra referencia."}
    if monto_esperado is not None and monto + 0.01 < round(float(monto_esperado), 2):
        return {"aprobado": False, "estado": estado, "monto": monto, "referencia": referencia,
                "detalle": f"El pago es por {monto:.2f} y se esperaba {float(monto_esperado):.2f}."}

    return {"aprobado": estado == "approved", "estado": estado, "monto": monto,
            "referencia": referencia,
            "detalle": None if estado == "approved" else f"Estado en MercadoPago: {estado or '—'}."}


def datos_de_prueba(pais: str = "UY") -> dict:
    """Tarjetas ficticias para ensayar el cobro sin mover un peso.

    Fuente de verdad: el panel de MercadoPago de cada cuenta
    (**Tus integraciones → Cuentas de prueba**). Estos son los valores que
    MercadoPago publica para el Cono Sur; si alguno dejara de funcionar, el
    del panel manda.

    El truco del nombre del titular es de MercadoPago, no nuestro: escribir
    `APRO` fuerza que el pago se apruebe y `OTHE` que se rechace, lo que
    permite ensayar también el camino del pago fallido.
    """
    return {
        "aviso": ("Verificá los valores en tu panel de MercadoPago "
                  "(Tus integraciones → Cuentas de prueba): cambian por país."),
        "tarjetas": [
            {"marca": "Mastercard", "numero": "5031 7557 3453 0604", "cvv": "123", "vence": "11/30"},
            {"marca": "Visa", "numero": "4509 9535 6623 3704", "cvv": "123", "vence": "11/30"},
        ],
        "titular": {"aprobar": "APRO", "rechazar": "OTHE"},
        "documento": {"tipo": "CI" if pais == "UY" else "DNI", "numero": "12345678"},
        "nota": ("El nombre del titular decide el resultado: APRO aprueba el pago "
                 "y OTHE lo rechaza. Sirve para ensayar también el camino del pago fallido."),
    }
