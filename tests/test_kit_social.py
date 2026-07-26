"""Tests del kit de contenido para redes (`marketing/`).

Bug real que originó este módulo: los PNG del kit anterior salieron con el
texto pisando el mockup y con URLs que no eran las del producto. Estos tests
cubren las dos familias de defecto — contenido y geometría — sin depender de
que haya navegador: los de contenido corren siempre, y el de render se saltea
solo si falta Playwright o Chromium.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from marketing import kit_social as K              # noqa: E402
from marketing import generar_kit_social as G      # noqa: E402


# --- contenido -------------------------------------------------------------
def test_ningun_banner_menciona_precios():
    """Restricción explícita del pedido: el material publicado no muestra
    precios. El precio se conversa en la demo."""
    for b in K.BANNERS:
        texto = " ".join(str(b.get(c, "")) for c in
                         ("eyebrow", "headline", "sub")).lower()
        texto += " ".join(b.get("chips", [])).lower()
        for termino in K.PROHIBIDO:
            assert termino not in texto, f"{b['id']} menciona {termino!r}"


def test_el_copy_no_menciona_precios():
    for c in K.COPY:
        texto = c["texto"].format(cta=K.CTA, dominio=K.DOMINIO).lower()
        for termino in K.PROHIBIDO:
            # El copy de mail usa {{firma}} y demás, ningún importe.
            assert termino not in texto, f"copy {c['id']} menciona {termino!r}"


def test_solo_aparece_el_dominio_oficial():
    """Regresión: el kit anterior llevaba URLs de preview de Vercel, que
    cambian con cada deploy y no sirven en material publicado."""
    import re
    todo = " ".join(c["texto"].format(cta=K.CTA, dominio=K.DOMINIO)
                    for c in K.COPY) + " " + G.leeme([])
    for url in re.findall(r"[a-z0-9.-]+\.(?:com|app|io|net|uy)\b", todo.lower()):
        assert url == K.DOMINIO, f"URL ajena al producto: {url!r}"


def test_el_antetitulo_no_repite_la_bajada_de_marca():
    """El logotipo ya trae 'Cobranzas inteligentes' debajo del nombre. Si el
    antetítulo dice lo mismo, queda la frase dos veces, una sobre la otra —
    pasó en el banner de Instagram y en el de mail."""
    for b in K.BANNERS:
        assert b["eyebrow"].strip().lower() != K.BAJADA.strip().lower(), b["id"]


def test_las_capturas_referenciadas_existen():
    for b in K.BANNERS:
        if b.get("captura"):
            assert os.path.exists(os.path.join(G.ASSETS, b["captura"])), b["id"]


def test_todos_los_formatos_declaran_tamano_entero():
    """El nombre del archivo lleva el tamaño: tiene que ser el real, porque es
    lo que mira quien lo sube a cada red."""
    vistos = set()
    for b in K.BANNERS:
        assert isinstance(b["ancho"], int) and isinstance(b["alto"], int)
        assert b["id"] not in vistos, f"id duplicado: {b['id']}"
        vistos.add(b["id"])


# --- recorte de capturas ---------------------------------------------------
def test_detecta_la_franja_clara_del_toolbar():
    """Las capturas traen arriba la barra blanca de Streamlit, que sobre una
    pieza oscura queda como un tajo. Se mide, no se hardcodea."""
    from PIL import Image
    ruta = os.path.join(G.ASSETS, "dashboard_overview.png")
    with Image.open(ruta) as im:
        alto = G._alto_franja_clara(im)
    assert alto > 0, "no detectó la franja blanca del toolbar"
    # Y no se come media captura si arriba hubiera un gráfico claro.
    with Image.open(ruta) as im:
        assert alto < im.height * 0.15


def test_recortar_no_devuelve_una_imagen_vacia():
    d = G.captura_recortada(os.path.join(G.ASSETS, "dashboard_overview.png"),
                            izquierda=0.20)
    assert d.startswith("data:image/png;base64,") and len(d) > 5000


# --- geometría (necesita navegador) ---------------------------------------
def test_los_banners_renderizan_sin_solapes_ni_desbordes(tmp_path):
    """El test que cubre el bug original: se renderiza cada pieza en tamaño
    real y se mide el DOM. Ninguna zona puede invadir a otra ni salirse del
    lienzo, y ningún texto puede quedar recortado."""
    pytest.importorskip("playwright.sync_api")
    if not G.fuente_disponible():
        pytest.skip("no hay una tipografía aceptable instalada")
    try:
        resultados = G.renderizar(str(tmp_path))
    except Exception as e:                      # navegador ausente en CI
        if "executable" in str(e).lower() or "browser" in str(e).lower():
            pytest.skip(f"sin navegador para renderizar: {e}")
        raise
    assert len(resultados) == len(K.BANNERS)
    for r in resultados:
        assert not r["problemas"], f"{r['id']}: {r['problemas']}"
        png = tmp_path / r["archivo"]
        assert png.exists() and png.stat().st_size > 10_000
        from PIL import Image
        with Image.open(png) as im:
            assert im.size == (r["ancho"], r["alto"])


def test_revisar_contenido_detecta_precios_y_urls_ajenas():
    """El chequeo de contenido corre sobre el texto renderizado; acá se
    verifica que efectivamente atrape lo que tiene que atrapar."""
    assert G.revisar_contenido("Desde USD 99 por mes")
    assert G.revisar_contenido("Probalo en kobra-ia.vercel.app")
    assert not G.revisar_contenido(
        f"Cobrá más, con menos esfuerzo. {K.DOMINIO}")
