# © 2026 Martín Viera. Todos los derechos reservados.

"""La diapositiva de Frescura del PowerPoint: que diga lo mismo que la pantalla.

El deck se reenvía y se proyecta semanas después; esta hoja es la que le pone
fecha a los números. Se prueba contra tablas SINTÉTICAS en una carpeta
temporal, con fechas de modificación puestas a mano y `ahora` inyectado: un
semáforo que depende del reloj de la máquina deja tests que fallan solos.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from pptx import Presentation
from pptx.util import Inches

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import frecuencia_cargas as kfc  # noqa: E402
from marketing import marca  # noqa: E402
from presentation import frescura_ppt as fp  # noqa: E402

AHORA = datetime(2026, 9, 6, 10, 0, 0)


def _archivo(carpeta, nombre, contenido, hace_horas, binario=False):
    ruta = carpeta / nombre
    if binario:
        ruta.write_bytes(contenido)
    else:
        ruta.write_text(contenido, encoding="utf-8")
    cuando = (AHORA - timedelta(hours=hace_horas)).timestamp()
    os.utime(ruta, (cuando, cuando))
    return str(ruta)


@pytest.fixture
def rutas(tmp_path):
    """Cinco tablas sintéticas, una por situación que el semáforo distingue."""
    return {
        # diaria, hace 5 h → al día
        "scored": _archivo(tmp_path, "scored.csv",
                           "id,prob\n1,0.2\n2,0.5\n3,0.9\n", 5),
        # diaria, hace 3 días → atrasada
        "gestiones": _archivo(
            tmp_path, "gestiones.csv",
            "id,fecha_gestion\n1,2026-08-30\n2,2026-09-01\n3,2026-09-02 18:30\n"
            "4,2026-08-15\n", 72),
        # semanal, hace 20 días → atrasada, y más vieja que gestiones
        "calidad": _archivo(tmp_path, "calidad.csv",
                            "id,fecha,nota\n1,2026-08-10,80\n", 24 * 20),
        # nunca subida → sin cargar
        "cartera_real": str(tmp_path / "no_existe.csv"),
        # mensual, hace 10 días → al día; binario, sin filas
        "modelo": _archivo(tmp_path, "modelo.joblib", b"\x80\x04\n\n\n", 240,
                           binario=True),
    }


def _deck():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    return prs


def _por_nombre(slide, prefijo):
    return [s for s in slide.shapes if s.name.startswith(prefijo)]


def _texto(shape):
    return shape.text_frame.text if shape.has_text_frame else ""


def test_una_fila_por_tabla_con_el_color_del_semaforo(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, ahora=AHORA)
    chips = {c.name.removeprefix("frescura_chip_"): c
             for c in _por_nombre(s, "frescura_chip_")}
    assert set(chips) == {t.id for t in kfc.TABLAS}

    esperado = {"scored": kfc.AL_DIA, "gestiones": kfc.ATRASADA,
                "calidad": kfc.ATRASADA, "cartera_real": kfc.SIN_DATOS,
                "modelo": kfc.AL_DIA}
    etiquetas = kfc.textos("es")["ppt"]["estado"]
    for id_, estado in esperado.items():
        chip = chips[id_]
        assert str(chip.fill.fore_color.rgb).lower() == \
            marca.SEMAFORO[estado].lstrip("#").lower(), id_
        assert _texto(chip) == etiquetas[estado]


def test_las_atrasadas_van_primero_y_la_mas_vieja_arriba(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, ahora=AHORA)
    filas = sorted(_por_nombre(s, "frescura_fila_"), key=lambda f: f.top)
    orden = [f.name.removeprefix("frescura_fila_") for f in filas]
    assert orden == ["calidad", "gestiones", "cartera_real", "modelo", "scored"]


def test_la_fila_muestra_las_dos_fechas_las_filas_y_la_cadencia(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, ahora=AHORA)
    celdas = {c.name: _texto(c) for c in _por_nombre(s, "frescura_celda_")}
    # Fecha de CARGA (mtime) y fecha del DATO (máximo de la columna), separadas.
    assert celdas["frescura_celda_gestiones_1"].startswith("2026-09-03 10:00")
    assert "jueves" in celdas["frescura_celda_gestiones_1"]
    assert celdas["frescura_celda_gestiones_2"] == "2026-09-02"
    assert celdas["frescura_celda_gestiones_3"] == "4"
    assert celdas["frescura_celda_gestiones_4"] == "Todos los días"
    # El motivo del atraso, redactado por el motor, va debajo del nombre.
    assert "3 días" in celdas["frescura_celda_gestiones_0"]
    # Debajo de una tabla al día: hasta cuándo sigue en verde (motor).
    assert celdas["frescura_celda_modelo_0"].endswith(
        "Próxima carga esperada: 2026-09-26 10:00")
    # Un binario no inventa filas; una tabla nunca subida no inventa fechas.
    assert celdas["frescura_celda_modelo_3"] == "—"
    assert celdas["frescura_celda_cartera_real_1"] == "—"
    assert celdas["frescura_celda_cartera_real_2"] == "—"


def test_la_tira_de_kpis_cuenta_lo_mismo_que_el_motor(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, ahora=AHORA)
    resumen = kfc.panel(rutas, "es", AHORA)["resumen"]
    assert resumen == {"total": 5, "al_dia": 2, "atrasadas": 2, "sin_datos": 1}
    textos = [_texto(x) for x in s.shapes]
    for id_, n in (("total", 5), (kfc.AL_DIA, 2), (kfc.ATRASADA, 2),
                   (kfc.SIN_DATOS, 1)):
        assert _por_nombre(s, f"frescura_kpi_{id_}"), id_
        assert str(n) in textos
    # El titular del motor ("2 atrasada(s): … · 1 sin cargar: …") va arriba.
    titular = _texto(_por_nombre(s, "frescura_titular")[0])
    assert "atrasada" in titular and "sin cargar" in titular


def test_la_leyenda_trae_los_umbrales_calculados_por_el_motor(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, ahora=AHORA)
    todo = " ".join(_texto(x) for x in s.shapes)
    # diaria 24 h × 1,5 = 36 h; semanal 168 h × 1,5 = 10 días; mensual 45 días.
    assert "diaria > 36 horas" in todo
    assert "semanal > 10 días" in todo
    assert "mensual > 45 días" in todo
    assert "manual: no vence" in todo
    # De la cadencia más corta a la más larga, no en el orden de las filas.
    assert todo.index("diaria >") < todo.index("semanal >") < todo.index("mensual >")
    assert len(_por_nombre(s, "frescura_leyenda_")) == 3


def _dentro(slide, prs):
    for shp in slide.shapes:
        assert shp.left >= 0 and shp.top >= 0, shp.name
        assert shp.left + shp.width <= prs.slide_width, shp.name
        assert shp.top + shp.height <= prs.slide_height, shp.name


def test_nada_se_sale_de_la_diapositiva(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, ahora=AHORA)
    _dentro(s, prs)


def test_una_lista_larga_se_pagina_sin_perder_ni_repetir_tablas(rutas):
    base = kfc.panel(rutas, "es", AHORA)
    muchas = [dict(t, id=f"{t['id']}_{i}") for i in range(3)
              for t in base["tablas"]][:12]
    datos = dict(base, tablas=muchas)
    prs = _deck()
    slides = fp.agregar(prs, datos)
    assert len(slides) == 3
    vistas = []
    for s in slides:
        filas = _por_nombre(s, "frescura_fila_")
        assert 1 <= len(filas) <= fp.FILAS_POR_PAGINA
        vistas += [f.name for f in filas]
        _dentro(s, prs)
        assert "página" in _texto(_por_nombre(s, "frescura_titulo")[0])
    assert sorted(vistas) == sorted(f"frescura_fila_{t['id']}" for t in muchas)


def test_en_ingles_la_diapositiva_no_queda_en_castellano(rutas):
    prs = _deck()
    [s] = fp.agregar_desde_rutas(prs, rutas, idioma="en", ahora=AHORA)
    todo = " ".join(_texto(x) for x in s.shapes)
    assert "Data freshness" in todo and "Late" in todo
    assert "Frescura" not in todo and "Atrasada" not in todo


def test_el_deck_completo_trae_la_diapositiva_despues_de_los_kpis(rutas, tmp_path):
    from presentation import build_ppt
    salida = tmp_path / "deck.pptx"
    build_ppt.build(out=str(salida), rutas=rutas, ahora=AHORA)
    prs = Presentation(str(salida))
    titulos = [next((_texto(x) for x in s.shapes
                     if x.name == "frescura_titulo"), None) for s in prs.slides]
    indices = [i for i, t in enumerate(titulos) if t]
    assert len(indices) == 1 and titulos[indices[0]] == "Frescura de los datos"
    anterior = " ".join(_texto(x) for x in prs.slides[indices[0] - 1].shapes)
    assert "Impacto sobre la cartera" in anterior
    _dentro(prs.slides[indices[0]], prs)


def test_las_rutas_del_deck_son_las_mismas_que_las_de_la_webapp():
    """Si el deck mira otras rutas que la pantalla, los dos semáforos pueden
    decir cosas distintas sobre la misma instalación."""
    from webapp.backend import api
    assert fp.rutas_por_defecto(api.DIR_DATOS) == \
        api._rutas_de_tablas(api.EMPRESA_DEFAULT)
