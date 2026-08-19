# © 2026 Martín Viera. Todos los derechos reservados.

"""Medidas calculadas: que calculen bien y que no sean una puerta abierta.

La mitad interesante de este archivo es la de seguridad. El módulo existe para
que un usuario escriba una fórmula y el programa la ejecute — o sea, ejecución
de código provista por el usuario, que es exactamente la clase de cosa que hay
que probar suponiendo mala fe y no solo errores de tipeo.

La implementación obvia (`eval`) hace pasar todos los tests de cálculo y
ninguno de los de abajo. Por eso los de abajo existen: son la diferencia entre
un motor de medidas y un intérprete de Python con otro nombre.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import medidas as km  # noqa: E402


@pytest.fixture()
def cartera():
    return pd.DataFrame({
        "monto_deuda": [100.0, 200.0, 300.0, 400.0],
        "dias_mora": [10, 95, 120, 5],
        "cuotas_atrasadas": [1, 3, 4, 0],
        "segmento": ["Pyme", "Individuo", "Pyme", "Corp"],
    })


# ---------------------------------------------------------------------------
# Que calcule
# ---------------------------------------------------------------------------
def test_agregaciones_simples(cartera):
    assert km.evaluar("suma(monto_deuda)", cartera) == 1000.0
    assert km.evaluar("promedio(monto_deuda)", cartera) == 250.0
    assert km.evaluar("minimo(monto_deuda)", cartera) == 100.0
    assert km.evaluar("maximo(monto_deuda)", cartera) == 400.0
    assert km.evaluar("distintos(segmento)", cartera) == 3.0


def test_aritmetica_entre_agregaciones(cartera):
    """El caso real: una tasa es un cociente entre dos sumas."""
    assert km.evaluar("suma(monto_deuda) / contar()", cartera) == 250.0
    assert km.evaluar("suma(monto_deuda) * 2 - 500", cartera) == 1500.0


def test_conteo_con_condicion(cartera):
    assert km.evaluar("contar()", cartera) == 4.0
    assert km.evaluar("contar_si(dias_mora > 90)", cartera) == 2.0
    assert km.evaluar("contar_si(dias_mora > 90) / contar() * 100", cartera) == 50.0


def test_condiciones_combinadas(cartera):
    """`and`/`or` se escriben como los escribiría un usuario, y por dentro se
    traducen al operador vectorizado de pandas."""
    assert km.evaluar(
        "contar_si(dias_mora > 90 and cuotas_atrasadas > 3)", cartera) == 1.0
    assert km.evaluar(
        "contar_si(dias_mora > 100 or cuotas_atrasadas == 0)", cartera) == 2.0


def test_dividir_por_cero_da_sin_datos_y_no_infinito(cartera):
    """Es el caso más común de una medida recién escrita: el filtro todavía no
    trajo filas. Un tablero que dice `inf` parece roto; uno que dice 0 miente."""
    vacia = cartera.iloc[0:0]
    m = km.Medida("tasa", "suma(monto_deuda) / contar()")
    r = m.calcular(vacia)
    assert r["valor"] is None
    assert "sin datos" in r["error"]


# ---------------------------------------------------------------------------
# Que NO sea una puerta abierta
# ---------------------------------------------------------------------------
# Cada uno de estos pasa sin problema con `eval`. Ese es el punto.
@pytest.mark.parametrize("ataque", [
    # Ejecutar comandos del sistema
    "__import__('os').system('id')",
    "__import__('subprocess').run(['ls'])",
    # Llegar a los builtins por la cadena de clases
    "(1).__class__.__bases__[0].__subclasses__()",
    "''.__class__.__mro__[1].__subclasses__()",
    # Leer archivos
    "open('/etc/passwd').read()",
    # Atributos y métodos arbitrarios sobre el DataFrame
    "monto_deuda.__class__",
    "monto_deuda.to_csv('/tmp/robado.csv')",
    # Construcciones que permiten evaluar código
    "eval('1+1')",
    "exec('x=1')",
    "compile('1', '<s>', 'eval')",
    "globals()",
    "vars()",
    # Lambdas y comprensiones
    "(lambda: 1)()",
    "[x for x in (1, 2)]",
    # Asignación morsa (dejaría estado entre evaluaciones)
    "(x := 1)",
    # f-strings, que permiten evaluar expresiones anidadas
    "f'{1+1}'",
    # Indexado y slicing
    "monto_deuda[0]",
])
def test_lo_que_no_es_una_medida_se_rechaza(ataque, cartera):
    """Lista blanca: lo que no está explícitamente permitido, no entra.

    Si este test empieza a fallar, alguien reemplazó el parser por `eval` o
    aflojó la lista blanca — y el módulo pasó a ejecutar lo que el usuario
    quiera, en la máquina del cliente y con sus permisos.
    """
    with pytest.raises(km.FormulaInvalida):
        km.evaluar(ataque, cartera)


def test_el_rechazo_no_filtra_detalles_internos(cartera):
    """El mensaje es para quien escribe la fórmula: tiene que decir qué se
    puede usar, no volcar un traceback de Python."""
    with pytest.raises(km.FormulaInvalida) as e:
        km.evaluar("open('/etc/passwd')", cartera)
    texto = str(e.value)
    assert "Traceback" not in texto
    assert "suma" in texto, "el mensaje no dice qué funciones hay disponibles"


def test_una_formula_absurdamente_larga_se_corta(cartera):
    """Un tope contra una fórmula anidada que consuma el proceso al parsear."""
    with pytest.raises(km.FormulaInvalida):
        km.evaluar("suma(monto_deuda)" + " + 1" * 400, cartera)


# ---------------------------------------------------------------------------
# Errores del usuario: mensajes que sirvan
# ---------------------------------------------------------------------------
def test_una_columna_que_no_existe_lista_las_que_si(cartera):
    with pytest.raises(km.FormulaInvalida) as e:
        km.evaluar("suma(monto_deudda)", cartera)
    assert "monto_deuda" in str(e.value), \
        "el error no ayuda a encontrar el nombre correcto"


def test_una_funcion_que_no_existe_lista_las_que_si(cartera):
    with pytest.raises(km.FormulaInvalida) as e:
        km.evaluar("mediana_movil(monto_deuda)", cartera)
    assert "promedio" in str(e.value)


def test_una_formula_que_da_una_columna_lo_explica(cartera):
    """El error más frecuente de quien recién empieza: olvidarse la agregación.
    El mensaje tiene que decir qué falta, no solo que está mal."""
    with pytest.raises(km.FormulaInvalida) as e:
        km.evaluar("monto_deuda * 2", cartera)
    assert "suma" in str(e.value)


def test_sintaxis_rota_no_muestra_un_error_de_python(cartera):
    with pytest.raises(km.FormulaInvalida) as e:
        km.evaluar("suma(monto_deuda", cartera)
    assert "no se entiende" in str(e.value)


def test_formula_vacia(cartera):
    with pytest.raises(km.FormulaInvalida):
        km.evaluar("   ", cartera)


# ---------------------------------------------------------------------------
# Validación al guardar
# ---------------------------------------------------------------------------
def test_validar_acepta_una_formula_correcta():
    r = km.validar("suma(monto_deuda) / contar()", ["monto_deuda", "dias_mora"])
    assert r["ok"] is True


def test_validar_rechaza_antes_de_guardar():
    """Sin esto, el error aparece recién cuando alguien abre el tablero — y le
    aparece a otra persona, no a quien escribió la medida."""
    r = km.validar("suma(no_existe)", ["monto_deuda"])
    assert r["ok"] is False
    assert "no_existe" in r["error"]


# ---------------------------------------------------------------------------
# Medidas guardadas
# ---------------------------------------------------------------------------
def test_una_medida_rota_no_deja_el_tablero_en_blanco(cartera):
    """Seis medidas y una mal escrita: se muestran cinco y el error de la
    sexta. Que caiga todo por una es lo que hace que se desconfíe del tablero.
    """
    medidas = [
        km.Medida("Buena", "suma(monto_deuda)"),
        km.Medida("Rota", "suma(columna_fantasma)"),
        km.Medida("Otra buena", "contar()"),
    ]
    r = km.calcular_todas(medidas, cartera)
    assert r[0]["valor"] == 1000.0
    assert r[1]["valor"] is None and r[1]["error"]
    assert r[2]["valor"] == 4.0


def test_la_medida_va_y_vuelve_de_dict(cartera):
    """Se guardan en configuración, así que tienen que serializar sin perder
    nada."""
    original = km.Medida("Tasa", "contar_si(dias_mora > 90) / contar() * 100",
                         "Mora alta", "porcentaje")
    copia = km.Medida.de_dict(original.a_dict())
    assert copia.calcular(cartera) == original.calcular(cartera)
    assert copia.formato == "porcentaje"


def test_las_medidas_de_ejemplo_funcionan_sobre_la_cartera(cartera):
    """Sirven de documentación viva: si dejaran de andar, el usuario que las
    copia para empezar recibe un error como primera impresión."""
    for m in km.medidas_de_ejemplo():
        r = m.calcular(cartera)
        assert r["error"] is None, f"{m.nombre}: {r['error']}"
        assert r["valor"] is not None


def test_una_medida_sin_nombre_se_rechaza():
    with pytest.raises(km.FormulaInvalida):
        km.Medida("", "suma(monto_deuda)")
