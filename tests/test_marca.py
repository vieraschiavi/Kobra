"""Tests de la identidad de marca: tokens de color compartidos y logo vectorial.

Tres defectos reales que cubren estos tests:

* La paleta estaba escrita a mano en tres lugares y ya había divergido — la
  presentación gerencial y el sitio no parecían de la misma empresa.
* Todo el branding era raster: sin SVG no hay forma de imprimir ni de escalar
  el logo sin que se vea blando.
* Al vectorizar, dos bugs de trazado dieron piezas visualmente rotas que
  igual "funcionaban" como archivo: el cuadrado del isotipo salió como cuatro
  triángulos en las esquinas, y las letras de adentro salieron huecas.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from marketing import marca as M  # noqa: E402

BRAND = os.path.join(ROOT, "assets", "brand")
SVGS = ("mv_icon.svg", "mv_wordmark.svg", "mv_wordmark_claro.svg")


# --- tokens ----------------------------------------------------------------
def test_rgb_convierte_y_rechaza_basura():
    assert M.rgb("#00c896") == (0, 200, 150)
    assert M.rgb("00C896") == (0, 200, 150)
    for malo in ("#fff", "", "#00c8961", "azul"):
        with pytest.raises(ValueError):
            M.rgb(malo)


def test_todos_los_tokens_son_hexadecimales_validos():
    for grupo in (M.MARCA, M.LOGO):
        for nombre, valor in grupo.items():
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", valor), f"{nombre}={valor!r}"


def test_los_acentos_existen_en_la_paleta():
    """Los acentos distinguen categorías en gráficos y diapositivas; si uno
    apunta a un token inexistente, la presentación revienta al construirse."""
    for nombre in M.ACENTOS:
        assert nombre in M.MARCA, nombre
    assert len(set(M.ACENTOS)) == len(M.ACENTOS), "acentos repetidos"


def test_la_landing_usa_los_mismos_colores_que_los_tokens():
    """Regresión: la paleta estaba duplicada a mano en la landing, en el
    generador de la presentación y en el kit social, y se habían separado.
    Este test falla en cuanto una copia vuelva a divergir."""
    html = open(os.path.join(ROOT, "landing", "index.html"),
                encoding="utf-8").read()
    for token in ("navy", "green", "blue", "amber", "ink", "muted", "faint"):
        m = re.search(rf"--{token}:\s*(#[0-9a-fA-F]{{6}})", html)
        assert m, f"la landing no declara --{token}"
        assert m.group(1).lower() == M.MARCA[token].lower(), (
            f"--{token}: la landing dice {m.group(1)} y los tokens {M.MARCA[token]}")


def test_el_kit_social_y_la_presentacion_no_redefinen_la_paleta():
    """Ambos tienen que importar de `marca.py`, no volver a escribir colores."""
    for rel in (os.path.join("marketing", "kit_social.py"),
                os.path.join("presentation", "build_ppt.py")):
        fuente = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "marca" in fuente, f"{rel} no importa los tokens"
    from marketing import kit_social as K
    assert K.COLORES is M.MARCA


def test_css_variables_incluye_toda_la_paleta():
    css = M.css_variables()
    for nombre, valor in M.MARCA.items():
        assert f"--{nombre}: {valor};" in css


# --- logo vectorial --------------------------------------------------------
@pytest.mark.parametrize("nombre", SVGS)
def test_existe_el_svg_y_es_svg_de_verdad(nombre):
    ruta = os.path.join(BRAND, nombre)
    assert os.path.exists(ruta), f"falta {nombre}"
    svg = open(ruta, encoding="utf-8").read()
    assert svg.startswith("<svg") and "viewBox" in svg
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert "aria-label" in svg, "sin etiqueta accesible"
    # Un calco malo tiene decenas de miles de nodos; el nuestro está
    # simplificado. Si esto se dispara, la simplificación dejó de funcionar.
    assert len(svg) < 120_000, f"{nombre} pesa {len(svg)} B: ¿se simplificó?"


def test_el_isotipo_tiene_las_tres_capas_con_sus_colores():
    svg = open(os.path.join(BRAND, "mv_icon.svg"), encoding="utf-8").read()
    for clave in ("fondo", "m", "v"):
        assert f'fill="{M.LOGO[clave]}"' in svg, f"falta la capa {clave}"


def test_el_logotipo_no_lleva_el_fondo_incrustado():
    """El PNG original trae el fondo oscuro pegado, lo que lo vuelve inusable
    sobre cualquier otro color. El SVG tiene que ser transparente."""
    svg = open(os.path.join(BRAND, "mv_wordmark.svg"), encoding="utf-8").read()
    assert M.LOGO["lienzo"] not in svg


def test_la_variante_clara_cambia_el_texto_que_seria_invisible():
    """Sobre papel el "MV" casi blanco desaparece; en la variante clara va
    en navy."""
    oscuro = open(os.path.join(BRAND, "mv_wordmark.svg"), encoding="utf-8").read()
    claro = open(os.path.join(BRAND, "mv_wordmark_claro.svg"),
                 encoding="utf-8").read()
    assert M.LOGO["texto"] in oscuro
    assert M.LOGO["texto"] not in claro
    assert M.MARCA["navy"] in claro
    # La "M" de adentro del cuadrado sigue siendo blanca en las dos: ahí el
    # fondo es el navy del isotipo, no el papel.
    assert M.LOGO["m"] in claro


# --- el motor de vectorización --------------------------------------------
def test_la_cobertura_recupera_la_mezcla_del_antialias():
    """Un píxel de borde vale `t·color + (1-t)·fondo`; la cobertura despeja t.
    Es lo que da precisión de sub-píxel en vez de escalones."""
    np = pytest.importorskip("numpy")
    from marketing.vectorizar_marca import cobertura
    blanco, navy = (255, 255, 255), (18, 30, 58)
    medio = tuple(int(round(0.5 * b + 0.5 * n)) for b, n in zip(blanco, navy))
    pix = np.array([[blanco, navy, medio]], dtype=np.uint8)
    t = cobertura(pix, blanco, navy)
    assert t[0, 0] == pytest.approx(1.0, abs=0.01)
    assert t[0, 1] == pytest.approx(0.0, abs=0.01)
    assert t[0, 2] == pytest.approx(0.5, abs=0.02)


def test_la_cobertura_descarta_los_colores_ajenos():
    """Sin esto el verde proyecta sobre el eje del blanco y ensucia su máscara."""
    np = pytest.importorskip("numpy")
    from marketing.vectorizar_marca import cobertura
    verde, blanco, navy = (130, 197, 68), (255, 255, 255), (18, 30, 58)
    t = cobertura(np.array([[verde]], dtype=np.uint8), blanco, navy)
    assert t[0, 0] == 0.0


def test_una_figura_pegada_al_borde_da_un_solo_contorno():
    """Regresión: el cuadrado del isotipo toca los bordes del lienzo. Sin
    acolchar el campo, la isolínea no cierra alrededor de la figura y salen
    cuatro bucles —uno por esquina— que al rellenarse pintan justo lo
    contrario: el isotipo salía como cuatro triángulos en las esquinas."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("contourpy")
    from marketing.vectorizar_marca import contornos
    campo = np.ones((40, 40))          # llena todo el lienzo, toca los 4 bordes
    cs = contornos(campo)
    assert len(cs) == 1, f"{len(cs)} contornos en vez de 1"
    xs, ys = cs[0][:, 0], cs[0][:, 1]
    assert xs.min() < 0.5 and xs.max() > 38.5
    assert ys.min() < 0.5 and ys.max() > 38.5


def test_el_simplificador_conserva_las_esquinas_y_tira_los_puntos_de_paso():
    np = pytest.importorskip("numpy")
    from marketing.vectorizar_marca import _rdp
    # Un cuadrado con puntos intermedios sobre cada lado: sobran todos.
    lado = np.linspace(0, 10, 11)
    pts = ([(x, 0.0) for x in lado] + [(10.0, y) for y in lado[1:]]
           + [(x, 10.0) for x in lado[::-1][1:]] + [(0.0, y) for y in lado[::-1][1:]])
    simple = _rdp(np.array(pts), 0.35)
    assert len(simple) == 5, f"{len(simple)} vértices para un cuadrado"
