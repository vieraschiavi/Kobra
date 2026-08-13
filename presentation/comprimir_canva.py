# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Comprimir los exports de Canva para que viajen con el repo
=========================================================================
La presentación más pulida del producto se arma en Canva y se exporta a PDF y
PPTX. Esos exports pesaban 85 MB entre los cuatro archivos y estaban en
`.gitignore`, así que **no viajaban con el repo**: existían solo en la máquina
de quien los exportó. Un equipo nuevo, una máquina nueva o un clon limpio no
los tenían, y nada avisaba de la ausencia.

Versionarlos tal cual tampoco iba: 85 MB entran en el historial de git para
siempre, en cada clon, y GitHub avisa a partir de los 50 MB por archivo.

Este script hace el corte razonable. Cada página de Canva es una sola imagen a
página completa — no hay texto seleccionable que preservar, así que se
rasteriza a la resolución que la pieza realmente necesita y se re-comprime en
JPEG. Para una presentación que se muestra en pantalla o se manda por mail,
150 ppp es de sobra; el peso baja un orden de magnitud.

El PDF comprimido sí se versiona. El original y el PPTX siguen ignorados: el
maestro editable es el propio Canva (el enlace está en el README), no un
archivo binario en git.

Uso:
    python3 presentation/comprimir_canva.py
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANVA = os.path.join(ROOT, "presentation", "canva")

# 150 ppp sobre una diapositiva de 1440×810 pt da ~3000 px de ancho: nítido en
# pantalla y al proyectar, sin el peso de la resolución original.
PPP = 150
CALIDAD_JPEG = 78


def comprimir(origen: str, destino: str, ppp: int = PPP,
              calidad: int = CALIDAD_JPEG) -> dict:
    """Rasteriza cada página y rearma el PDF con las imágenes en JPEG.

    Devuelve {paginas, bytes_antes, bytes_despues, factor}.
    """
    import io

    import fitz
    from PIL import Image

    antes = os.path.getsize(origen)
    entrada = fitz.open(origen)
    salida = fitz.open()
    escala = ppp / 72.0
    for pagina in entrada:
        mapa = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False)
        imagen = Image.frombytes("RGB", (mapa.width, mapa.height), mapa.samples)
        buf = io.BytesIO()
        imagen.save(buf, format="JPEG", quality=calidad, optimize=True,
                    progressive=True)
        nueva = salida.new_page(width=pagina.rect.width,
                                height=pagina.rect.height)
        nueva.insert_image(nueva.rect, stream=buf.getvalue())
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    salida.save(destino, garbage=4, deflate=True)
    paginas = len(entrada)
    salida.close()
    entrada.close()
    despues = os.path.getsize(destino)
    return {"paginas": paginas, "bytes_antes": antes, "bytes_despues": despues,
            "factor": round(antes / despues, 1) if despues else 0}


def main() -> int:
    origen = os.path.join(CANVA, "Kobra_Canva_Honesta.pdf")
    destino = os.path.join(CANVA, "Kobra_Canva_Honesta_comprimido.pdf")
    if not os.path.exists(origen):
        print(f"[SKIP] No está el export de Canva ({os.path.relpath(origen, ROOT)}). "
              "Exportalo desde Canva y volvé a correr esto.")
        return 0
    r = comprimir(origen, destino)
    print(f"[OK] {r['paginas']} páginas · "
          f"{r['bytes_antes'] / 1e6:.1f} MB → {r['bytes_despues'] / 1e6:.1f} MB "
          f"({r['factor']}× más liviano)")
    print(f"     {os.path.relpath(destino, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
