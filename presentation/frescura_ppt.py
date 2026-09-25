# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Diapositiva de Frescura para los PowerPoint exportados
=====================================================================
Una diapositiva (o varias, si la lista es larga) que dice, para cada tabla que
usa el programa, cuándo se cargó por última vez, de qué fecha es el dato,
cuántas filas tiene, cada cuánto se espera y —con un semáforo— si llegó tarde.

Por qué va en el deck
---------------------
Un PowerPoint viaja solo: se reenvía, se proyecta en un directorio, se abre
dos semanas después. Los números de las otras diapositivas no dicen de cuándo
son, y un KPI de hace tres semanas se ve idéntico a uno de hoy. Esta hoja es la
que le pone fecha a todo lo demás.

Qué NO hace este módulo
-----------------------
No decide si una tabla está atrasada. Eso lo decide `kobra/frecuencia_cargas.py`
—el mismo motor que alimenta la pantalla «Frecuencia de cargas» de la webapp—
y acá solo se dibuja su veredicto. Si el deck calculara el atraso por su
cuenta, el día que alguien cambie la tolerancia el PowerPoint y la pantalla
darían semáforos distintos para la misma tabla.
"""
from __future__ import annotations

import os
from datetime import datetime

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from kobra import frecuencia_cargas as kfc
from marketing import marca as _marca


def _c(hex_):
    return RGBColor(*_marca.rgb(hex_))


NAVY = _c(_marca.MARCA["navy"])
PANEL = _c(_marca.MARCA["panel"])
LINEA = _c(_marca.MARCA["line"])
TINTA = _c(_marca.MARCA["ink"])
SUB = _c(_marca.MARCA["sub"])
TENUE = _c(_marca.MARCA["muted"])
VERDE = _c(_marca.MARCA["green"])
COLOR_ESTADO = {k: _c(v) for k, v in _marca.SEMAFORO.items()}

# Lo que está mal va primero: el que abre la hoja tiene que ver el problema
# sin leer la tabla entera. Dentro de las atrasadas, la más vieja arriba.
_ORDEN = {kfc.ATRASADA: 0, kfc.SIN_DATOS: 1, kfc.AL_DIA: 2}

# Cuántas tablas entran en una diapositiva sin achicar la letra. Con más, se
# pagina: una fila más apretada es una fila que no se lee proyectada.
FILAS_POR_PAGINA = 5

# Geometría (pulgadas). Todo se calcula contra el ancho y alto del deck para
# que nada se salga de la hoja: un chip cortado en el borde es lo primero que
# se nota en una proyección.
_MARGEN = 0.7
_Y_KPI, _H_KPI = 1.5, 0.95
_Y_CABECERA, _H_CABECERA = 2.62, 0.36
_Y_FILAS, _H_FILA, _GAP_FILA = 3.04, 0.66, 0.06
_Y_LEYENDA, _H_LEYENDA = 6.72, 0.5
# (clave de texto, proporción del ancho útil)
_COLUMNAS = (("col_tabla", 0.33), ("col_carga", 0.165), ("col_dato", 0.13),
             ("col_filas", 0.10), ("col_esperada", 0.16), ("col_estado", 0.115))

_SEPARADOR_MILES = {"es": ".", "pt": ".", "en": ","}


def ordenar(tablas: list[dict]) -> list[dict]:
    """Atrasadas primero (la más vieja arriba), después las faltantes, al final
    las que están al día. Estable dentro de cada grupo."""
    return sorted(tablas, key=lambda t: (_ORDEN.get(t["estado"], 1),
                                         -(t.get("horas_desde_carga") or 0)))


def _miles(n: int | None, idioma: str) -> str:
    if n is None:
        return "—"
    return f"{n:,}".replace(",", _SEPARADOR_MILES.get(idioma, "."))


def _texto(slide, x, y, w, h, lineas, *, align=PP_ALIGN.LEFT,
           anchor=MSO_ANCHOR.MIDDLE, nombre=None):
    """`lineas` = [(texto, tamaño, color, negrita), ...], un párrafo cada una."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if nombre:
        tb.name = nombre
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right"):
        setattr(tf, m, Inches(0.08))
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    for i, (txt, tam, color, negrita) in enumerate(lineas):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = txt
        r.font.size = Pt(tam)
        r.font.bold = negrita
        r.font.color.rgb = color
        r.font.name = "Segoe UI"
    return tb


def _caja(slide, x, y, w, h, fill, *, forma=MSO_SHAPE.ROUNDED_RECTANGLE,
          linea=None, nombre=None):
    shp = slide.shapes.add_shape(forma, Inches(x), Inches(y), Inches(w), Inches(h))
    if nombre:
        shp.name = nombre
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if linea is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = linea
        shp.line.width = Pt(1)
    shp.shadow.inherit = False
    if forma == MSO_SHAPE.ROUNDED_RECTANGLE:
        shp.adjustments[0] = 0.18
    return shp


def _kpis(slide, datos: dict, txt: dict, ancho: float):
    r = datos["resumen"]
    tarjetas = (("kpi_total", r["total"], VERDE, "total"),
                ("kpi_al_dia", r["al_dia"], COLOR_ESTADO[kfc.AL_DIA], kfc.AL_DIA),
                ("kpi_atrasadas", r["atrasadas"], COLOR_ESTADO[kfc.ATRASADA], kfc.ATRASADA),
                ("kpi_sin_datos", r["sin_datos"], COLOR_ESTADO[kfc.SIN_DATOS], kfc.SIN_DATOS))
    gap = 0.2
    w = (ancho - gap * (len(tarjetas) - 1)) / len(tarjetas)
    for i, (clave, valor, color, id_) in enumerate(tarjetas):
        x = _MARGEN + i * (w + gap)
        # Una cuenta en cero no se pinta de alarma: ámbar o rojo con un «0»
        # adentro dice «problema» y no hay ninguno.
        activo = id_ in ("total", kfc.AL_DIA) or valor > 0
        _caja(slide, x, _Y_KPI, w, _H_KPI, PANEL,
              linea=color if activo else LINEA, nombre=f"frescura_kpi_{id_}")
        _caja(slide, x + 0.1, _Y_KPI + 0.2, 0.07, _H_KPI - 0.4,
              color if activo else LINEA)
        _texto(slide, x + 0.22, _Y_KPI + 0.06, w - 0.32, 0.52,
               [(str(valor), 26, color if activo else TENUE, True)])
        _texto(slide, x + 0.22, _Y_KPI + 0.56, w - 0.32, 0.32,
               [(txt[clave], 12, SUB, False)])


def _proxima(t: dict, txt: dict) -> str:
    """Debajo de una tabla al día, cuándo se espera la próxima carga (la calcula
    el motor). Una tabla sin problema no necesita un párrafo: necesita saber
    hasta cuándo va a seguir en verde."""
    tabla = kfc.por_id(t["id"])
    if tabla is None or not t.get("carga"):
        return ""
    prox = kfc.proxima_carga(tabla, datetime.strptime(t["carga"], "%Y-%m-%d %H:%M:%S"))
    return txt["proxima"].format(cuando=prox.strftime("%Y-%m-%d %H:%M")) if prox else ""


def _fila(slide, t: dict, y: float, anchos: list[float], txt: dict,
          idioma: str):
    ancho = sum(anchos)
    color = COLOR_ESTADO.get(t["estado"], COLOR_ESTADO[kfc.SIN_DATOS])
    _caja(slide, _MARGEN, y, ancho, _H_FILA, PANEL, nombre=f"frescura_fila_{t['id']}")
    _caja(slide, _MARGEN + 0.06, y + 0.1, 0.07, _H_FILA - 0.2, color)

    carga = t.get("carga")
    celdas = [
        [(t["nombre"], 12.5, TINTA, True),
         (t.get("motivo") or _proxima(t, txt), 8.5, TENUE, False)],
        [(carga[:16] if carga else "—", 12, TINTA, False),
         (t.get("dia_carga") or "", 9, TENUE, False)],
        [(t.get("fecha_dato") or "—", 12, TINTA, False)],
        [(_miles(t.get("filas"), idioma), 12, TINTA, False)],
        [(t.get("esperada", ""), 11, SUB, False)],
    ]
    x = _MARGEN + 0.14
    for i, lineas in enumerate(celdas):
        w = anchos[i] - (0.14 if i == 0 else 0)
        align = PP_ALIGN.RIGHT if i == 3 else PP_ALIGN.LEFT
        _texto(slide, x, y, w, _H_FILA, [ln for ln in lineas if ln[0]],
               align=align, nombre=f"frescura_celda_{t['id']}_{i}")
        x += w

    # El chip del semáforo: color lleno y texto oscuro, que se lee igual
    # proyectado que impreso en blanco y negro (el texto dice el estado).
    wc = anchos[-1] - 0.2
    chip = _caja(slide, x + 0.1, y + (_H_FILA - 0.38) / 2, wc, 0.38, color,
                 nombre=f"frescura_chip_{t['id']}")
    tf = chip.text_frame
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = txt["estado"].get(t["estado"], t["estado"])
    r.font.size = Pt(11)
    r.font.bold = True
    r.font.color.rgb = NAVY
    r.font.name = "Segoe UI"


def _leyenda(slide, tablas: list[dict], txt_motor: dict, txt: dict,
             ancho: float, idioma: str):
    """Los tres colores y el umbral de cada cadencia presente, calculado con
    las constantes del motor (período × tolerancia) — no escrito a mano."""
    umbrales = []
    presentes = {t["frecuencia"] for t in tablas}
    for f in (f for f in kfc.PERIODOS_HORAS if f in presentes):
        horas = kfc.PERIODOS_HORAS.get(f)
        nombre = txt_motor["frecuencia"].get(f, f)
        if horas is None:
            umbrales.append(txt["umbral_manual"].format(frecuencia=nombre))
        else:
            limite = kfc._humano(horas * kfc.TOLERANCIA, txt_motor)
            umbrales.append(txt["umbral"].format(frecuencia=nombre, limite=limite))

    x = _MARGEN
    for estado in (kfc.AL_DIA, kfc.ATRASADA, kfc.SIN_DATOS):
        _caja(slide, x, _Y_LEYENDA + 0.16, 0.18, 0.18, COLOR_ESTADO[estado],
              forma=MSO_SHAPE.OVAL, nombre=f"frescura_leyenda_{estado}")
        _texto(slide, x + 0.2, _Y_LEYENDA, 1.35, _H_LEYENDA,
               [(txt["estado"][estado], 11, SUB, True)])
        x += 1.6
    tolerancia = f"{kfc.TOLERANCIA:g}"
    if idioma != "en":
        tolerancia = tolerancia.replace(".", ",")
    _texto(slide, x, _Y_LEYENDA, _MARGEN + ancho - x, _H_LEYENDA,
           [(txt["leyenda"].format(tolerancia=tolerancia) + "  "
             + "  ·  ".join(umbrales), 10, TENUE, False)])


def agregar(prs, datos: dict, fondo=None) -> list:
    """Agrega la(s) diapositiva(s) de Frescura a `prs` a partir de un panel ya
    calculado por `kobra.frecuencia_cargas.panel`. Devuelve las diapositivas."""
    idioma = kfc.normalizar(datos.get("idioma"))
    txt_motor = kfc.textos(idioma)
    txt = txt_motor["ppt"]
    tablas = ordenar(list(datos["tablas"]))
    ancho_util = prs.slide_width / 914400 - 2 * _MARGEN
    anchos = [ancho_util * p for _, p in _COLUMNAS]

    paginas = [tablas[i:i + FILAS_POR_PAGINA]
               for i in range(0, max(len(tablas), 1), FILAS_POR_PAGINA)] or [[]]
    creadas = []
    for n, pagina in enumerate(paginas, start=1):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = fondo or NAVY

        titulo = txt["titulo"]
        if len(paginas) > 1:
            titulo += "  ·  " + txt["pagina"].format(n=n, total=len(paginas))
        _texto(s, _MARGEN, 0.32, ancho_util, 0.7, [(titulo, 30, TINTA, True)],
               nombre="frescura_titulo")
        _caja(s, _MARGEN, 1.05, 0.15, 0.36, VERDE, forma=MSO_SHAPE.RECTANGLE)
        generado = datos.get("generado", "")[:16]
        _texto(s, _MARGEN + 0.25, 0.98, ancho_util - 0.25, 0.5,
               [(txt["subtitulo"].format(cuando=generado), 12, TENUE, False),
                (datos.get("titular", ""), 12, SUB, True)],
               nombre="frescura_titular")

        _kpis(s, datos, txt, ancho_util)

        # Cabecera de la tabla.
        _caja(s, _MARGEN, _Y_CABECERA, ancho_util, _H_CABECERA,
              _c(_marca.MARCA["navy2"]), forma=MSO_SHAPE.RECTANGLE)
        x = _MARGEN + 0.14
        for i, (clave, _) in enumerate(_COLUMNAS):
            w = anchos[i] - (0.14 if i == 0 else 0)
            align = (PP_ALIGN.RIGHT if clave == "col_filas" else
                     PP_ALIGN.CENTER if clave == "col_estado" else PP_ALIGN.LEFT)
            _texto(s, x, _Y_CABECERA, w, _H_CABECERA,
                   [(txt[clave].upper(), 9.5, VERDE, True)], align=align)
            x += w

        for j, t in enumerate(pagina):
            _fila(s, t, _Y_FILAS + j * (_H_FILA + _GAP_FILA), anchos, txt, idioma)

        _leyenda(s, tablas, txt_motor, txt, ancho_util, idioma)
        creadas.append(s)
    return creadas


def agregar_desde_rutas(prs, rutas: dict, idioma: str = "es",
                        ahora: datetime | None = None, fondo=None) -> list:
    """Atajo: calcula el panel con el motor del programa y lo dibuja."""
    return agregar(prs, kfc.panel(rutas, idioma, ahora), fondo=fondo)


def rutas_por_defecto(dir_datos: str | None = None) -> dict:
    """Dónde viven las tablas de la instalación «principal» — las mismas rutas
    que resuelve `webapp/backend/api.py::_rutas_de_tablas("principal")` (hay un
    test que falla si se separan). La cartera real importada por el usuario
    entra como una tabla más: si es la fuente, su fecha de carga es la que
    importa."""
    if dir_datos is None:
        from kobra import rutas as krutas
        dir_datos = krutas.DIR_DATOS
    return {
        "scored": os.path.join(dir_datos, "outputs", "kobra_scored.csv"),
        "gestiones": os.path.join(dir_datos, "data", "kobra_gestiones.csv"),
        "calidad": os.path.join(dir_datos, "data", "calidad_evaluaciones.csv"),
        "cartera_real": os.path.join(dir_datos, "outputs", "kobra_cartera_real.csv"),
        "modelo": os.path.join(dir_datos, "outputs", "probpago_model.joblib"),
    }
