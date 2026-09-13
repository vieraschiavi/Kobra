# © 2026 Martín Viera. Todos los derechos reservados.

"""Los números de la cartera de un cliente, tal como salen de su Excel.

El defecto más peligroso de un producto de cobranzas no es el que rompe: es el
que NO rompe y devuelve un número equivocado. Nadie ve un error, la pantalla se
llena igual, y la decisión que se toma con esa pantalla es otra.

Estos tests fijan tres formas que ninguna persona escribe a mano —las tres las
produce un Excel o un ERP solo— y que entraban mal en silencio:

    '1.23E+09'    Excel exporta así cualquier número grande.
    '(2.500,50)'  Paréntesis contables: es NEGATIVO (nota de crédito).
    '1.234,00-'   Signo al final, típico de SAP.
"""
import math
import sys

import pandas as pd
import pytest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from kobra import cartera_manual as cm  # noqa: E402

# (entrada tal como viene del archivo, número que significa, por qué aparece)
FORMATOS = [
    # --- Lo que ya andaba. Va en el mismo test a propósito: un arreglo de
    #     parseo que rompe los formatos que ya entraban bien no es un arreglo.
    ("$ 1.234.567,89", 1234567.89, "moneda es: miles con punto, decimal coma"),
    ("1,234,567.89", 1234567.89, "moneda en: miles con coma"),
    ("UYU 5.000", 5000.0, "con código de moneda"),
    ("45%", 0.45, "porcentaje"),
    ("1.234", 1234.0, "miles sin decimales"),
    ("1.23", 1.23, "decimal con punto"),
    ("-5.000", -5000.0, "negativo al principio"),
    ("+5.000", 5000.0, "signo más explícito"),
    ("1.234.567", 1234567.0, "tres grupos de miles"),
    ("0,5", 0.5, "decimal con coma"),
    ("1 234 567", 1234567.0, "miles separados con espacio"),
    ("1'234'567", 1234567.0, "miles con apóstrofe"),

    # --- Lo que entraba MAL, en silencio.
    ("1.23E+09", 1.23e9, "Excel: número grande exportado en notación científica"),
    ("1,23E+09", 1.23e9, "ídem, con coma decimal (locale es)"),
    ("1.5e6", 1.5e6, "notación científica en minúscula"),
    ("8.9E+05", 890000.0, "exponente de dos dígitos"),
    ("(5.000)", -5000.0, "paréntesis contables = negativo"),
    ("(1.234.567,89)", -1234567.89, "ídem con miles y decimales"),
    ("$(2.500,50)", -2500.5, "ídem con la moneda afuera del paréntesis"),
    ("1.234,00-", -1234.0, "signo al final (SAP)"),
    ("5.000-", -5000.0, "ídem sin decimales"),
]

VACIOS = ["", "N/A", "-", "   ", "sin dato"]


@pytest.mark.parametrize("entrada,esperado,por_que", FORMATOS)
def test_los_numeros_del_excel_de_un_cliente_entran_bien(entrada, esperado, por_que):
    obtenido = cm._a_numero(entrada)
    assert not math.isnan(obtenido), f"{entrada!r} quedó sin leer ({por_que})"
    assert abs(obtenido - esperado) < 1e-6, (
        f"{entrada!r} entró como {obtenido!r} y significa {esperado!r} ({por_que})")


@pytest.mark.parametrize("entrada", VACIOS)
def test_lo_que_no_es_un_numero_queda_como_nan_y_no_como_cero(entrada):
    """Un cero es un monto; un dato que falta no lo es. Confundirlos baja el
    promedio de la cartera sin que nadie lo note."""
    assert math.isnan(cm._a_numero(entrada)), f"{entrada!r} no es un número"


def test_una_deuda_en_notacion_cientifica_no_se_encoge_nueve_ordenes():
    """El caso completo, de punta a punta, porque es el que importa.

    Antes: `1.23E+09` entraba como 1,2309. El deudor más grande de la cartera
    —1.230 millones— aparecía con una deuda de un peso con veintitrés, caía al
    decil más bajo, y la cartera total que informaba el programa era 25.900
    veces menor que la real. Sin un solo error en pantalla.
    """
    bruto = pd.DataFrame({
        "Nombre": ["Deudor grande", "Deudor chico", "Nota de credito"],
        "Telefono": ["099000001", "099000002", "099000003"],
        "Deuda": ["1.23E+09", "45.000", "(2.500,50)"],
        "Dias mora": ["120", "30", "60"],
    })
    out = cm.importar_y_scorear(bruto)
    montos = dict(zip(out["nombre"], out["monto_deuda"]))

    assert montos["Deudor grande"] == pytest.approx(1.23e9)
    assert montos["Deudor chico"] == pytest.approx(45000.0)
    assert montos["Nota de credito"] == pytest.approx(-2500.5), (
        "una nota de crédito tiene que RESTAR de la cartera, no sumar")
    assert out["monto_deuda"].sum() == pytest.approx(1_230_000_000 + 45_000 - 2_500.5)


# ---------------------------------------------------------------------------
# Extrapolar está bien; no avisar que se está extrapolando, no
# ---------------------------------------------------------------------------

def test_una_cartera_dentro_del_rango_no_dispara_ningun_aviso():
    _, tope = cm.rango_referencia()
    assert cm.aviso_fuera_de_rango([tope / 2, tope / 10, 1000.0]) is None


def test_los_montos_por_encima_del_rango_entrenado_se_avisan():
    """A una cartera nueva se la puntúa con el modelo de referencia, porque
    todavía no trae histórico de pagos propio. Para un monto muy por arriba de
    lo que ese modelo vio, la logística satura y ProbPago se va a cero — y el
    porcentaje aparecía en pantalla con la misma cara de certeza que el de un
    deudor de $U 45.000, justo en las cuentas más grandes del cliente."""
    _, tope = cm.rango_referencia()
    aviso = cm.aviso_fuera_de_rango([1000.0, tope * 10, tope * 100])
    assert aviso is not None
    assert "2 de 3" in aviso, "tiene que decir a cuántos deudores les pasa"
    assert "extrapolación" in aviso
    assert "histórico" in aviso, "y cómo se sale de ahí"


def test_el_aviso_no_se_cae_con_una_cartera_sin_montos_legibles():
    assert cm.aviso_fuera_de_rango([]) is None
    assert cm.aviso_fuera_de_rango(["", "N/A"]) is None
