# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Marca blanca (white-label)
========================================
El plan Enterprise otorgaba la feature `white_label` en el JWT de licencia
—`backend_venta/licencias.py` y `api/_license.js` la firman— y **ningún código
del producto la miraba**. Ni una línea. Se cobraba una feature que no existía:
el cliente de Enterprise abría el programa y veía "MV KOBRA AI" en la barra
lateral, igual que todos.

Acá está lo que faltaba: nombre, logo y color de acento propios del cliente,
en el dashboard que usan sus gestores todos los días.

Qué NO hace, a propósito
------------------------
No toca la landing, ni el instalador, ni los avisos de licencia. Marca blanca
en un producto vendido significa que la HERRAMIENTA se ve del cliente —lo que
ve su equipo, y lo que ve un tercero si comparte pantalla—, no que se borre el
rastro de quién lo fabricó. El pie de "hecho con MV Kobra AI" se mantiene.

Por qué el logo se valida tan duro
----------------------------------
El logo entra como data URI y sale renderizado en un `<img>` de todas las
pantallas. Un `data:text/html;base64,...` ahí adentro es XSS con permanencia:
lo escribe un admin, lo ve cada gestor, cada vez que abre el programa. Así que
se acepta una lista blanca de tipos de imagen y nada más — y con tope de
tamaño, porque el valor viaja en cada respuesta de `/api/marca`.
"""
from __future__ import annotations

import re

CLAVE_CONFIG = "marca_blanca"

# Los que un navegador dibuja como imagen y nada más. SVG queda AFUERA
# deliberadamente: un SVG puede traer `<script>` adentro, así que como data URI
# en un `<img>` es una vía de ejecución más, no un formato de logo más.
TIPOS_LOGO = ("image/png", "image/jpeg", "image/webp", "image/gif")

# 256 KB de data URI ≈ 190 KB de imagen. Un logo de barra lateral entra
# holgado; el tope está porque esto viaja en cada respuesta de `/api/marca`.
MAX_LOGO = 256 * 1024
MAX_NOMBRE = 40

_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_LOGO = re.compile(r"^data:(" + "|".join(re.escape(t) for t in TIPOS_LOGO) +
                   r");base64,[A-Za-z0-9+/]+={0,2}$")

# Lo que se ve si el cliente no configuró nada (o no tiene la feature).
DEFECTO = {"nombre": "MV Kobra AI", "logo": "", "color": "", "propia": False}


class MarcaInvalida(ValueError):
    """El logo o el color no pasan la validación. Nunca se guarda a medias."""


def _limpiar_nombre(v) -> str:
    if not isinstance(v, str):
        return ""
    # Sin saltos ni caracteres de control: el nombre va a un `<b>` y a un
    # `<title>`, y un salto ahí rompe el layout sin avisar.
    v = re.sub(r"[\r\n\t\x00-\x1f\x7f]", " ", v).strip()
    return re.sub(r"\s{2,}", " ", v)[:MAX_NOMBRE]


def validar(datos: dict) -> dict:
    """Normaliza y valida. Lanza `MarcaInvalida` con el motivo, o devuelve la
    marca lista para guardar."""
    datos = datos or {}
    nombre = _limpiar_nombre(datos.get("nombre"))
    if not nombre:
        raise MarcaInvalida("Falta el nombre con el que se va a ver el producto.")

    color = (datos.get("color") or "").strip()
    if color and not _COLOR.match(color):
        raise MarcaInvalida(
            f"El color tiene que ser hexadecimal (#1B4D3E o #1B4). Vino: {color!r}.")

    logo = (datos.get("logo") or "").strip()
    if logo:
        if len(logo) > MAX_LOGO:
            raise MarcaInvalida(
                f"El logo pesa {len(logo) // 1024} KB y el tope son "
                f"{MAX_LOGO // 1024} KB. Es un ícono de barra lateral: con "
                "128×128 alcanza.")
        if not _LOGO.match(logo):
            raise MarcaInvalida(
                "El logo tiene que ser una imagen PNG, JPEG, WebP o GIF en "
                "base64 (data:image/png;base64,…). SVG no se acepta: puede "
                "traer código adentro.")

    return {"nombre": nombre, "color": color, "logo": logo, "propia": True}


def leer() -> dict:
    """La marca vigente. Siempre devuelve algo usable.

    Si el plan no incluye `white_label`, devuelve la marca de fábrica aunque
    haya una guardada: una licencia que se degradó de Enterprise a Pro no
    puede seguir mostrando la marca del cliente — eso sería seguir entregando
    la feature después de que dejó de pagarla.
    """
    from kobra import plan as kplan
    if not kplan.permite("white_label"):
        return dict(DEFECTO)
    from kobra import config as kconfig
    guardada = kconfig.leer_extra(CLAVE_CONFIG)
    if not isinstance(guardada, dict) or not guardada.get("nombre"):
        return dict(DEFECTO)
    return {"nombre": guardada.get("nombre") or DEFECTO["nombre"],
            "color": guardada.get("color") or "",
            "logo": guardada.get("logo") or "",
            "propia": True}


def guardar(datos: dict) -> dict:
    """Valida y persiste. No mira el plan — eso lo hace el endpoint, que es
    quien tiene que devolver el 403 con el mensaje del plan."""
    marca = validar(datos)
    from kobra import config as kconfig
    kconfig.guardar_extra(CLAVE_CONFIG, marca)
    return marca


def borrar() -> dict:
    """Vuelve a la marca de fábrica."""
    from kobra import config as kconfig
    kconfig.guardar_extra(CLAVE_CONFIG, None)
    return dict(DEFECTO)
