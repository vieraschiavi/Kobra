# © 2026 Martín Viera. Todos los derechos reservados.

"""Los carteles de LinkedIn no pueden prometer lo que el producto no hace.

Un post publicado con un precio viejo o una función que se sacó no se
"despublica": ya lo leyeron, y el que compró por eso tiene razón en reclamar.
Como el texto vive en el repo, se puede atar a la fuente de verdad y que falle
acá antes de salir.

Lo que se fija: precios, y las dos afirmaciones que, de ser falsas, no son un
error de marketing sino un problema legal — que los datos son sintéticos y que
las cifras son ilustrativas.
"""
import os
import pathlib
import re

import pytest

from backend_venta.licencias import MODULOS_VENTA, PLANES

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARTELES = ROOT / "docs" / "CARTELES_LINKEDIN.md"


def _texto():
    return CARTELES.read_text(encoding="utf-8")


def _bloques():
    """Solo el texto de los posts, sin las notas de uso."""
    return re.findall(r"```text\n(.*?)```", _texto(), re.S)


def test_existe():
    assert CARTELES.exists()


def test_hay_seis_posts():
    """Tres videos por dos idiomas."""
    assert len(_bloques()) == 6, f"esperaba 6 posts, hay {len(_bloques())}"


# --- Precios ---------------------------------------------------------------
def test_el_precio_de_entrada_es_el_del_catalogo():
    """"Desde US$ 99" tiene que ser el plan pago más barato de verdad."""
    pagos = [v["precio"] for v in PLANES.values()
             if v["precio"] not in (None, 0.0)]
    mas_barato = int(min(pagos))
    texto = _texto()
    assert f"US$ {mas_barato}" in texto or f"US${mas_barato}" in texto, (
        f"el plan pago más barato es US$ {mas_barato} y los carteles no lo dicen")


@pytest.mark.parametrize("modulo", sorted(MODULOS_VENTA))
def test_los_modulos_sueltos_llevan_su_precio_real(modulo):
    precio = int(MODULOS_VENTA[modulo]["precio"])
    texto = _texto()
    assert f"US$ {precio}" in texto or f"US${precio}" in texto, (
        f"el módulo {modulo} cuesta US$ {precio} y los carteles dicen otra cosa")


def test_no_hay_precios_que_no_existan_en_el_catalogo():
    """Un precio inventado en un post publicado es una oferta que hay que
    honrar."""
    reales = {int(v["precio"]) for v in PLANES.values()
              if v["precio"] not in (None, 0.0)}
    reales |= {int(v["precio"]) for v in MODULOS_VENTA.values()}
    nombrados = {int(m) for m in re.findall(r"US\$\s?(\d+)", _texto())}
    assert nombrados <= reales, (
        f"los carteles nombran precios que no están en el catálogo: "
        f"{sorted(nombrados - reales)}")


# --- Lo que no se puede omitir ---------------------------------------------
@pytest.mark.parametrize("n", range(6))
def test_cada_post_aclara_que_los_datos_son_sinteticos(n):
    """La demo corre sobre datos sintéticos. Un post que lo omite deja creer
    que son clientes reales, y eso ya no es un matiz de marketing."""
    bloque = _bloques()[n].lower()
    assert "sintétic" in bloque or "synthetic" in bloque, (
        f"el post {n + 1} no aclara que los datos son sintéticos")


def test_las_cifras_se_presentan_como_ilustrativas():
    """El post que muestra números de impacto tiene que decir que son
    ilustrativos de la metodología, no resultados de clientes."""
    texto = _texto().lower()
    assert "ilustrativas de la metodología" in texto
    assert "illustrative of the methodology" in texto
    assert "no son resultados de clientes" in texto
    assert "not client results" in texto


@pytest.mark.parametrize("n", range(6))
def test_no_inventa_prueba_social(n):
    """No hay clientes públicos todavía. Un testimonio o un logo inventado en
    un post es lo más caro que se puede publicar.

    Se mira SOLO el texto de los posts y no el documento entero: las notas de
    uso nombran estas frases justamente para prohibirlas, y buscarlas en todo
    el archivo hacía fallar al test por su propia advertencia.
    """
    prohibidas = ["testimonio", "caso de éxito", "empresas que confían",
                  "nuestros clientes dicen", "case study", "trusted by",
                  "our customers say", "success story"]
    bloque = _bloques()[n].lower()
    for frase in prohibidas:
        assert frase not in bloque, (
            f"el post {n + 1} usa prueba social ({frase!r}) y todavía no hay "
            "clientes públicos")


# --- Estilo ----------------------------------------------------------------
@pytest.mark.parametrize("n", range(6))
def test_ningun_emoji_se_usa_como_vineta(n):
    """Un emoji por ítem de lista es la marca de agua del texto generado. Las
    listas van con raya; el emoji marca un momento, no un ítem."""
    for linea in _bloques()[n].splitlines():
        limpia = linea.strip()
        if limpia.startswith("—"):
            assert not re.match(r"^—\s*[\U0001F300-\U0001FAFF☀-➿]",
                                limpia), (
                f"post {n + 1}: hay un emoji usado como viñeta -> {limpia[:60]}")


@pytest.mark.parametrize("n", range(6))
def test_los_emojis_son_pocos(n):
    """Tres o cuatro por post. Más que eso deja de leerse profesional."""
    emojis = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", _bloques()[n])
    assert len(emojis) <= 5, (
        f"post {n + 1} tiene {len(emojis)} emojis: son demasiados")


@pytest.mark.parametrize("n", range(6))
def test_no_usa_markdown_que_linkedin_no_renderiza(n):
    """LinkedIn muestra `**negrita**` con los asteriscos a la vista."""
    bloque = _bloques()[n]
    assert "**" not in bloque, f"post {n + 1} usa negritas markdown"
    assert not re.search(r"^#{1,6}\s", bloque, re.M), (
        f"post {n + 1} usa encabezados markdown")


@pytest.mark.parametrize("n", range(6))
def test_cada_post_lleva_el_dominio(n):
    assert "mvkobranzaia.com" in _bloques()[n], (
        f"el post {n + 1} no tiene a dónde mandar al lector")


def test_los_videos_citados_existen():
    """Si un video se renombra, la tabla del documento manda a buscar un
    archivo que no está."""
    for nombre in re.findall(r"`(MVKobraAI_\w+\.\w+)`", _texto()):
        assert (ROOT / "landing" / "video" / nombre).exists(), (
            f"el documento cita {nombre} y no está en landing/video/")
