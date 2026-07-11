"""
MV Kobra AI · Informe Ejecutivo en PDF
=======================================
El comprador B2B (gerente de cobranzas) le rinde cuentas a un directorio
que no va a abrir el dashboard. Este módulo genera, con un clic, el PDF
que ese gerente lleva a la reunión: estado de la cartera, recupero
esperado, riesgo, tramos de mora y ranking de gestores — con la marca y
la fecha, listo para imprimir o adjuntar.

Diseño:
  - fpdf2 puro (sin binarios): entra en el instalador de Windows sin
    agrandar el build. Fuente core Helvetica (latin-1) — alcanza para
    español y portugués; los caracteres fuera de latin-1 se sustituyen.
  - Bilingüe ES/PT según el país del tenant (Fase 2 LATAM), moneda y
    separador de miles del país.
  - Mismo criterio de honestidad del resto del producto: si los datos son
    la demo sintética, el pie del informe lo dice — un informe que parece
    evidencia real sin serlo es exactamente lo que NO vendemos.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from kobra import paises as kpaises

_TXT = {
    "es": {
        "titulo": "Informe Ejecutivo de Cartera",
        "generado": "Generado el {fecha} · Empresa: {empresa} · País: {pais}",
        "kpis": "Indicadores generales",
        "deudores": "Deudores",
        "cartera": "Cartera total",
        "recupero": "Recupero esperado",
        "recupero_pct": "de la cartera",
        "probpago": "ProbPago promedio",
        "mora": "Mora promedio",
        "dias": "días",
        "riesgo": "Cartera en riesgo (propensión baja)",
        "tramos": "Cartera y recupero esperado por tramo de mora",
        "col_tramo": "Tramo",
        "col_cartera": "Cartera",
        "col_recupero": "Recupero esperado",
        "col_pct": "% recupero",
        "segmentos": "Recupero esperado por segmento",
        "propension": "Distribución por propensión de pago",
        "col_propension": "Propensión",
        "col_deudores": "Deudores",
        "gestores": "Ranking de gestores (top 10)",
        "sin_gestiones": "Todavía no hay gestiones registradas para rankear gestores.",
        "pie_honestidad": (
            "Datos de demostración 100% sintéticos; las métricas son ilustrativas "
            "de la metodología, no evidencia de resultados reales. Con la cartera "
            "real del cliente, este informe pasa a reflejar la operación real."),
        "pie_marca": "MV Kobra AI · Cobranzas Inteligentes — informe generado automáticamente por la plataforma.",
    },
    "pt": {
        "titulo": "Relatório Executivo de Carteira",
        "generado": "Gerado em {fecha} · Empresa: {empresa} · País: {pais}",
        "kpis": "Indicadores gerais",
        "deudores": "Devedores",
        "cartera": "Carteira total",
        "recupero": "Recuperação esperada",
        "recupero_pct": "da carteira",
        "probpago": "ProbPago médio",
        "mora": "Atraso médio",
        "dias": "dias",
        "riesgo": "Carteira em risco (propensão baixa)",
        "tramos": "Carteira e recuperação esperada por faixa de atraso",
        "col_tramo": "Faixa",
        "col_cartera": "Carteira",
        "col_recupero": "Recuperação esperada",
        "col_pct": "% recuperação",
        "segmentos": "Recuperação esperada por segmento",
        "propension": "Distribuição por propensão de pagamento",
        "col_propension": "Propensão",
        "col_deudores": "Devedores",
        "gestores": "Ranking de operadores (top 10)",
        "sin_gestiones": "Ainda não há atendimentos registrados para rankear operadores.",
        "pie_honestidad": (
            "Dados de demonstração 100% sintéticos; as métricas ilustram a "
            "metodologia, não são evidência de resultados reais. Com a carteira "
            "real do cliente, este relatório passa a refletir a operação real."),
        "pie_marca": "MV Kobra AI · Cobrança Inteligente — relatório gerado automaticamente pela plataforma.",
    },
}

_NAVY = (14, 22, 40)
_GREEN = (124, 194, 66)
_GRIS = (100, 116, 139)
_LINEA = (222, 226, 230)


def _latin1(s: str) -> str:
    """Helvetica core solo soporta latin-1 — sustituir lo que no entre."""
    s = (str(s).replace("—", "-").replace("–", "-")
         .replace("“", '"').replace("”", '"').replace("’", "'"))
    return s.encode("latin-1", "replace").decode("latin-1")


def _fmt_monto(n: float, pais) -> str:
    entero = f"{int(round(n)):,}".replace(",", ".")
    return f"{pais.simbolo} {entero}"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def generar_pdf(scored: pd.DataFrame, gestiones: pd.DataFrame | None,
                empresa: str, codigo_pais: str = "UY",
                datos_demo: bool = True) -> bytes:
    """Genera el informe ejecutivo. Devuelve los bytes del PDF."""
    from fpdf import FPDF

    pais = kpaises.obtener(codigo_pais)
    t = _TXT.get(pais.idioma, _TXT["es"])

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    ancho = pdf.w - pdf.l_margin - pdf.r_margin

    # --- Encabezado con marca --------------------------------------------
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, pdf.w, 26, "F")
    pdf.set_xy(pdf.l_margin, 8)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 15)
    pdf.cell(60, 10, _latin1("MV KOBRA "), new_x="END")
    pdf.set_text_color(*_GREEN)
    pdf.cell(10, 10, "AI", new_x="END")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "", 13)
    pdf.set_xy(-pdf.r_margin - 110, 8)
    pdf.cell(110, 10, _latin1(t["titulo"]), align="R")

    pdf.set_y(32)
    pdf.set_text_color(*_GRIS)
    pdf.set_font("helvetica", "", 9)
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(ancho, 6, _latin1(t["generado"].format(
        fecha=fecha, empresa=empresa, pais=pais.nombre)))
    pdf.ln(10)

    # --- KPIs --------------------------------------------------------------
    cartera = float(scored["monto_deuda"].sum())
    recupero = float(scored["valor_esperado_recupero"].sum())
    riesgo = float(scored.loc[scored["segmento_propension"] == "Baja",
                              "monto_deuda"].sum())
    kpis = [
        (t["deudores"], f"{len(scored):,}".replace(",", ".")),
        (t["cartera"], _fmt_monto(cartera, pais)),
        (t["recupero"], f"{_fmt_monto(recupero, pais)}  ({_fmt_pct(recupero / cartera if cartera else 0)} {t['recupero_pct']})"),
        (t["probpago"], _fmt_pct(float(scored["probpago"].mean()))),
        (t["mora"], f"{scored['dias_mora'].mean():.0f} {t['dias']}"),
        (t["riesgo"], f"{_fmt_monto(riesgo, pais)}  ({_fmt_pct(riesgo / cartera if cartera else 0)})"),
    ]
    _seccion(pdf, t["kpis"])
    pdf.set_font("helvetica", "", 10)
    for etiqueta, valor in kpis:
        pdf.set_text_color(*_GRIS)
        pdf.cell(ancho * 0.45, 7, _latin1(etiqueta))
        pdf.set_text_color(*_NAVY)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(ancho * 0.55, 7, _latin1(valor), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
    pdf.ln(4)

    # --- Tramos de mora (tabla con barra de recupero) -----------------------
    _seccion(pdf, t["tramos"])
    por_tramo = (scored.groupby("tramo_mora")
                 .agg(cartera=("monto_deuda", "sum"),
                      recupero=("valor_esperado_recupero", "sum"))
                 .reindex(["1-30", "31-60", "61-90", "91-180", "180+"]).dropna())
    _fila_tabla(pdf, ancho, [t["col_tramo"], t["col_cartera"], t["col_recupero"], t["col_pct"]],
                encabezado=True)
    max_cartera = float(por_tramo["cartera"].max()) if len(por_tramo) else 1.0
    for tramo, fila in por_tramo.iterrows():
        pct = fila["recupero"] / fila["cartera"] if fila["cartera"] else 0
        _fila_tabla(pdf, ancho, [str(tramo), _fmt_monto(fila["cartera"], pais),
                                 _fmt_monto(fila["recupero"], pais), _fmt_pct(pct)],
                    barra=fila["cartera"] / max_cartera)
    pdf.ln(4)

    # --- Segmentos y propensión, lado a lado --------------------------------
    _seccion(pdf, t["segmentos"])
    por_seg = (scored.groupby("segmento")["valor_esperado_recupero"].sum()
               .sort_values(ascending=False))
    pdf.set_font("helvetica", "", 10)
    for seg, val in por_seg.items():
        pdf.set_text_color(*_GRIS)
        pdf.cell(ancho * 0.45, 7, _latin1(str(seg)))
        pdf.set_text_color(*_NAVY)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(ancho * 0.55, 7, _latin1(_fmt_monto(val, pais)),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
    pdf.ln(4)

    _seccion(pdf, t["propension"])
    prop = scored.groupby("segmento_propension")["id_deudor"].count()
    _fila_tabla(pdf, ancho, [t["col_propension"], t["col_deudores"], "%"], encabezado=True)
    for nombre in ["Alta", "Media", "Baja"]:
        if nombre in prop.index:
            _fila_tabla(pdf, ancho, [nombre, f"{int(prop[nombre]):,}".replace(",", "."),
                                     _fmt_pct(prop[nombre] / len(scored))])
    pdf.ln(4)

    # --- Gestores ------------------------------------------------------------
    _seccion(pdf, t["gestores"])
    if gestiones is None or gestiones.empty:
        pdf.set_font("helvetica", "I", 9)
        pdf.set_text_color(*_GRIS)
        pdf.multi_cell(ancho, 6, _latin1(t["sin_gestiones"]))
    else:
        from kobra import analitica as kanalitica
        ranking = kanalitica.ranking_gestores(gestiones).head(10)
        if "index" in ranking.columns:
            ranking = ranking.drop(columns="index")
        enc = {"es": ["Gestor", "Gestiones", "Calidad prom.", "Recupero", "Conversión"],
               "pt": ["Operador", "Atendimentos", "Qualidade méd.", "Recuperação", "Conversão"]}
        _fila_tabla(pdf, ancho, enc.get(pais.idioma, enc["es"]), encabezado=True)
        for _, fila in ranking.iterrows():
            _fila_tabla(pdf, ancho, [
                str(fila.get("gestor", fila.get("gestor_id", ""))),
                str(int(fila.get("gestiones", 0))),
                f"{float(fila.get('calidad_prom', 0)):.1f}",
                _fmt_monto(float(fila.get("recupero", 0)), pais),
                _fmt_pct(float(fila.get("tasa_conversion", 0) or 0)),
            ])
    pdf.ln(6)

    # --- Pie: honestidad + marca ---------------------------------------------
    pdf.set_draw_color(*_LINEA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(*_GRIS)
    if datos_demo:
        pdf.multi_cell(ancho, 4.5, _latin1(t["pie_honestidad"]))
        pdf.ln(1)
    pdf.multi_cell(ancho, 4.5, _latin1(t["pie_marca"]))

    return bytes(pdf.output())


def _seccion(pdf, titulo: str):
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 8, _latin1(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_GREEN)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 24, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(3)


def _fila_tabla(pdf, ancho: float, celdas: list[str], encabezado: bool = False,
                barra: float | None = None):
    n = len(celdas)
    w = ancho / n
    if encabezado:
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(*_GRIS)
    else:
        pdf.set_font("helvetica", "", 9.5)
        pdf.set_text_color(*_NAVY)
    y = pdf.get_y()
    if barra is not None:
        # barra sutil de fondo proporcional a la cartera del tramo
        pdf.set_fill_color(234, 244, 226)
        pdf.rect(pdf.l_margin, y + 0.8, max(2.0, ancho * 0.98 * barra), 5.4, "F")
    for c in celdas:
        pdf.cell(w, 7, _latin1(c))
    pdf.ln(7)
    pdf.set_draw_color(*_LINEA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + ancho, pdf.get_y())
