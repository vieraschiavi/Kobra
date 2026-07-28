"""
MV Kobra AI · Logo vectorial (SVG) a partir del PNG
====================================================
Todo el branding del producto era raster: el icono en 1024×1024 y el logotipo
en 1200×320, sin ningún SVG. Eso limita más de lo que parece — para imprimir,
para un favicon nítido en pantallas HiDPI, para el icono de la app en Windows
o para cualquier pieza más grande que el PNG original, un raster se ve blando o
directamente pixelado, y no hay forma de recuperarlo.

Este módulo reconstruye el logo como vectores fieles al original, sin
redibujarlo a ojo. El método aprovecha que el logo son colores planos:

1. **Cobertura por color.** Un píxel del borde de una letra no es blanco ni
   fondo: es una mezcla `P = t·C + (1-t)·B`. Despejando `t` por proyección se
   recupera *cuánto* de ese píxel pertenece a la forma — o sea, el antialias
   deja de ser ruido y pasa a ser información de sub-píxel.
2. **Isolínea en t = 0,5.** El contorno se saca de ese campo continuo, no del
   píxel; el borde queda donde estaba de verdad, con precisión de sub-píxel.
3. **Simplificación Douglas-Peucker.** Las letras son de trazos rectos: una vez
   simplificados, cada lado queda como un segmento y no como cien puntos.

El resultado es un SVG chico y limpio, no un calco con miles de nodos.

Uso:
    python3 -m marketing.vectorizar_marca
"""
from __future__ import annotations

import os

from marketing import marca as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "assets", "brand")


# --------------------------------------------------------------------------
# Cobertura de sub-píxel
# --------------------------------------------------------------------------
def cobertura(pixeles, color, fondo, tol_error: float = 46.0):
    """Cuánto de cada píxel pertenece a `color` sobre `fondo`, entre 0 y 1.

    En un borde antialiaseado el píxel vale `t·color + (1-t)·fondo`. Proyectando
    sobre el eje `fondo→color` se despeja `t`. La proyección sola no alcanza:
    un píxel de OTRO color también proyecta algo sobre ese eje. Por eso se
    descarta todo píxel cuya reconstrucción se aleje más de `tol_error` del
    valor real — así el verde no contamina la máscara del blanco.
    """
    import numpy as np
    p = pixeles.astype(np.float64)
    c = np.asarray(color, dtype=np.float64)
    b = np.asarray(fondo, dtype=np.float64)
    eje = c - b
    denom = float(eje @ eje)
    if denom == 0:
        raise ValueError("el color y el fondo no pueden ser iguales")
    t = ((p - b) @ eje) / denom
    t = np.clip(t, 0.0, 1.0)
    reconstruido = b + t[..., None] * eje
    error = np.linalg.norm(p - reconstruido, axis=-1)
    t[error > tol_error] = 0.0
    return t


def _rdp(puntos, epsilon: float):
    """Douglas-Peucker iterativo (recursivo desborda la pila con contornos de
    miles de puntos). Deja solo los vértices que cambian la forma más que
    `epsilon`."""
    import numpy as np
    pts = np.asarray(puntos, dtype=np.float64)
    if len(pts) < 3:
        return pts
    conservar = np.zeros(len(pts), dtype=bool)
    conservar[0] = conservar[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        ini, fin = pila.pop()
        if fin <= ini + 1:
            continue
        a, b = pts[ini], pts[fin]
        seg = b - a
        largo = float(np.hypot(*seg))
        tramo = pts[ini + 1:fin]
        if largo == 0:
            dist = np.hypot(*(tramo - a).T)
        else:
            # Distancia punto-recta por producto cruzado.
            dist = np.abs(np.cross(seg, tramo - a)) / largo
        k = int(np.argmax(dist))
        if dist[k] > epsilon:
            corte = ini + 1 + k
            conservar[corte] = True
            pila += [(ini, corte), (corte, fin)]
    return pts[conservar]


def contornos(campo, epsilon: float = 0.35) -> list:
    """Isolíneas cerradas del campo de cobertura en 0,5, ya simplificadas.

    Devuelve los contornos exteriores y los agujeros mezclados: en el SVG se
    resuelven con `fill-rule="evenodd"`, que es exactamente para esto — la O y
    la B tienen hueco y no hay que distinguirlos a mano.
    """
    import numpy as np
    from contourpy import contour_generator
    # Acolchado obligatorio: si la figura toca el borde del lienzo, la isolínea
    # no se cierra a su alrededor y el trazador devuelve un bucle por esquina
    # en lugar de uno por figura. Rellenar esos bucles pinta exactamente lo
    # contrario a lo que se quiere — el cuadrado del isotipo salía como cuatro
    # triángulos en las esquinas. Con un marco de ceros la figura queda
    # rodeada de vacío y cada contorno cierra donde corresponde.
    acolchado = np.pad(np.asarray(campo, dtype=np.float64), 1,
                       mode="constant", constant_values=0.0)
    gen = contour_generator(z=acolchado, name="serial", line_type="SeparateCode")
    lineas, _ = gen.lines(0.5)
    salida = []
    for linea in lineas:
        pts = np.asarray(linea, dtype=np.float64) - 1.0  # deshacer el acolchado
        if len(pts) < 4:
            continue
        # Cerrar explícitamente antes de simplificar, para que el primer y el
        # último vértice no se separen.
        if not np.allclose(pts[0], pts[-1]):
            pts = np.vstack([pts, pts[0]])
        simple = _rdp(pts, epsilon)
        if len(simple) >= 4:
            salida.append(simple)
    return salida


def _path(contornos_lista, decimales: int = 2) -> str:
    partes = []
    for c in contornos_lista:
        puntos = [f"{round(float(x), decimales)},{round(float(y), decimales)}"
                  for x, y in c[:-1]]
        partes.append("M" + "L".join(puntos) + "Z")
    return "".join(partes)


# --------------------------------------------------------------------------
# Piezas
# --------------------------------------------------------------------------
def _svg(ancho: int, alto: int, capas: list[tuple[str, str]],
         etiqueta: str) -> str:
    cuerpo = "\n  ".join(f'<path fill="{color}" fill-rule="evenodd" d="{d}"/>'
                         for color, d in capas if d)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" '
            f'width="{ancho}" height="{alto}" role="img" '
            f'aria-label="{etiqueta}">\n  {cuerpo}\n</svg>\n')


def svg_icono(ruta_png: str | None = None) -> str:
    """Isotipo: el cuadrado redondeado con la M y la V."""
    import numpy as np
    from PIL import Image
    ruta_png = ruta_png or os.path.join(BRAND, "mv_icon.png")
    with Image.open(ruta_png) as im:
        w, h = im.size
        a = np.asarray(im.convert("RGBA"))
    pix, alfa = a[:, :, :3], a[:, :, 3] / 255.0

    # El cuadrado redondeado es lo único opaco del PNG: su silueta es
    # directamente el canal alfa, sin necesidad de separar colores.
    capas = [(M.LOGO["fondo"], _path(contornos(alfa)))]
    fondo = M.rgb(M.LOGO["fondo"])
    for clave in ("m", "v"):
        campo = cobertura(pix, M.rgb(M.LOGO[clave]), fondo) * (alfa > 0.5)
        capas.append((M.LOGO[clave], _path(contornos(campo))))
    return _svg(w, h, capas, "MV Kobra AI")


def svg_logotipo(ruta_png: str | None = None, claro: bool = False) -> str:
    """Logotipo horizontal, **con fondo transparente**.

    El PNG original trae el fondo oscuro incrustado, lo que lo vuelve inusable
    sobre cualquier otro color. Acá ese fondo se omite; el cuadrado navy del
    isotipo se conserva, porque es parte de la marca y no del fondo.

    `claro=True` devuelve la variante para fondos claros: el "MV" del logotipo
    es casi blanco y sobre papel desaparecería, así que pasa a navy.
    """
    import numpy as np
    from PIL import Image
    ruta_png = ruta_png or os.path.join(BRAND, "mv_wordmark.png")
    with Image.open(ruta_png) as im:
        w, h = im.size
        pix = np.asarray(im.convert("RGB"))

    lienzo = M.rgb(M.LOGO["lienzo"])
    navy = M.rgb(M.LOGO["fondo"])

    # El cuadrado del isotipo, recortado del lienzo.
    campo_caja = cobertura(pix, navy, lienzo)
    capas = [(M.LOGO["fondo"], _path(contornos(campo_caja)))]

    # Adentro del cuadrado las letras se mezclan con el navy; afuera, con el
    # lienzo. Si no se separan las dos regiones, el texto de afuera se lleva
    # también las letras de adentro y las pinta con el color equivocado.
    #
    # La región no puede ser "los píxeles navy": la M y la V son blancas, o sea
    # agujeros en esa máscara, y quedarían del lado de afuera — es exactamente
    # lo que pasó, las letras del isotipo salían huecas. Hay que rellenar los
    # agujeros para quedarse con el cuadrado macizo.
    from scipy.ndimage import binary_fill_holes
    dentro = binary_fill_holes(campo_caja > 0.5)
    for color, fondo, region in (
            (M.LOGO["m"], navy, dentro),          # "M" del isotipo
            (M.LOGO["v"], navy, dentro),          # "V" del isotipo
            (M.LOGO["texto"], lienzo, ~dentro),   # "MV" del logotipo
            (M.LOGO["texto_ac"], lienzo, ~dentro)):  # "KOBRA AI" + bajada
        campo = cobertura(pix, M.rgb(color), fondo) * region
        if claro and color == M.LOGO["texto"]:
            color = M.MARCA["navy"]
        capas.append((color, _path(contornos(campo))))
    return _svg(w, h, capas, "MV Kobra AI · Cobranzas inteligentes")


# --------------------------------------------------------------------------
def generar(destino: str | None = None) -> dict[str, str]:
    """Escribe los tres SVG en `assets/brand/` y devuelve {archivo: ruta}."""
    destino = destino or BRAND
    os.makedirs(destino, exist_ok=True)
    piezas = {
        "mv_icon.svg": svg_icono(),
        "mv_wordmark.svg": svg_logotipo(),
        "mv_wordmark_claro.svg": svg_logotipo(claro=True),
    }
    salida = {}
    for nombre, contenido in piezas.items():
        ruta = os.path.join(destino, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        salida[nombre] = ruta
    return salida


if __name__ == "__main__":
    for nombre, ruta in generar().items():
        print(f"[OK] {nombre:24s} {os.path.getsize(ruta) / 1024:6.1f} KB")
