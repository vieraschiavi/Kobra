# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Tokens de marca
==============================
Fuente única de los colores del producto. Antes vivían duplicados en tres
lugares que ya habían divergido entre sí:

* `landing/index.html` — navy #081527, verde #00c896, ámbar #f2b441.
* `presentation/build_ppt.py` — oscuro #0E1117, verde #00c896, violeta #6C5CE7.
* `marketing/kit_social.py` — copia de la paleta de la landing.

Nadie decidió que fueran distintas: se copiaron y se fueron separando. El
resultado era que la presentación gerencial y el sitio no parecían de la misma
empresa. Acá se define una sola paleta y los tres la importan.

Sobre los acentos
-----------------
El violeta y el amarillo de la presentación no eran colores de marca: servían
para distinguir categorías — los tres pilares del producto, los pasos del
flujo. Esa necesidad es real, así que se conserva, pero con los acentos que ya
usaba la landing (azul y ámbar) en vez de dos colores que no aparecían en
ningún otro lado.

Sobre el logo
-------------
Los colores del logo se declaran aparte, en `LOGO`, y **no** se tocan. Vale la
pena registrar una inconsistencia real: el verde de la "V" del isotipo es
#82C544, un verde amarillento, mientras que el verde de marca es #00C896, un
verde azulado. Son dos verdes distintos conviviendo en la misma identidad.
Unificarlos es una decisión de marca, no de código, así que queda documentada
acá en vez de resuelta por las malas.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# Paleta
# --------------------------------------------------------------------------
MARCA = {
    # Fondos, de más oscuro a menos
    "navy": "#081527",
    "navy2": "#0c2137",
    "panel": "#0e1e34",
    # Color principal
    "green": "#00c896",
    "green_hi": "#57e6bd",
    # Acentos, para distinguir categorías y series.
    #
    # El azul se oscureció de #2f74c0 a #215ea3 por contraste: sobre el celeste
    # de resalte (#e8f4ff) daba 4,30:1 y WCAG AA pide 4,5:1 — Lighthouse lo
    # marcaba como fallo de accesibilidad en la landing. Ahora da 5,89:1. Es el
    # mismo azul, más oscuro; no es un cambio de identidad, pero cambia el
    # color de un acento y por eso queda dicho acá.
    "blue": "#215ea3",
    "amber": "#f2b441",
    # Texto
    "ink": "#eaf1fb",
    "sub": "#b9c8dc",
    "muted": "#9db0c8",
    # Se aclaró de #6c7f99 a #7a8da7 por contraste: sobre los fondos oscuros
    # daba entre 3,87:1 y 4,48:1, por debajo del 4,5:1 que pide WCAG AA, y
    # Lighthouse lo marcaba en la landing. Ahora da entre 4,67:1 y 5,40:1.
    "faint": "#7a8da7",
    # Bordes
    "line": "#1d3149",
}

# Orden de acentos para series de datos y categorías. Verde primero: es el
# color de marca y le toca lo más importante de cada gráfico.
ACENTOS = ("green", "blue", "amber")

# Colores propios del isotipo. No son intercambiables con los de arriba: son
# la identidad gráfica, y cambiarlos es rehacer el logo.
LOGO = {
    "fondo": "#121E3A",   # cuadrado redondeado
    "m": "#FFFFFF",       # la "M"
    "v": "#82C544",       # la "V" — ver la nota del encabezado
    "lienzo": "#0E1117",  # fondo incrustado en el PNG del logotipo
    "texto": "#F5F6FA",   # "MV" del logotipo horizontal
    "texto_ac": "#00C896",  # "KOBRA AI" y la bajada
}


def rgb(color: str) -> tuple[int, int, int]:
    """'#00c896' → (0, 200, 150). Acepta con o sin almohadilla."""
    h = color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"color hexadecimal inválido: {color!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def css_variables(prefijo: str = "--") -> str:
    """La paleta como declaraciones CSS, para no volver a copiarla a mano."""
    return "\n".join(f"  {prefijo}{k}: {v};" for k, v in MARCA.items())
