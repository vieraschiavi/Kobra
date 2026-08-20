# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Medidas calculadas definidas por el cliente
=========================================================
Módulo de la suite (`plan.exigir("dax")`). Deja que un usuario defina sus
propios KPIs con una fórmula, sin tocar código ni pedir un desarrollo:

    tasa_recupero = suma(monto_recuperado) / suma(monto_deuda) * 100
    ticket_promedio = promedio(monto_deuda)
    mora_alta = contar_si(dias_mora > 90) / contar() * 100

Es el mismo lugar que ocupa DAX en Power BI: la métrica la define quien conoce
el negocio, no quien programa.

Por qué NO se usa `eval`
------------------------
La forma corta de implementar esto es `eval(formula, {...})`, y es una puerta
abierta a ejecutar cualquier cosa. `eval` no se arregla con una lista negra:
desde una expresión se llega a `__builtins__`, y de ahí a abrir archivos o
lanzar procesos. En la edición instalada la fórmula corre en la máquina del
cliente con sus permisos, y en la hosted contra el servidor — o sea que el peor
caso es "un usuario escribe una medida y se lleva el sistema".

Acá se parsea la fórmula con el módulo `ast` en modo `eval`, se recorre el
árbol y **se rechaza todo nodo que no esté en una lista blanca**: números,
nombres de columna, los cinco operadores aritméticos, comparaciones y las
funciones de agregación declaradas en `FUNCIONES`. No hay llamadas a métodos,
ni atributos, ni indexado, ni comprensiones, ni lambdas. Lo que no está
explícitamente permitido, no entra — que es la única forma que funciona.

Qué devuelve
------------
`evaluar` da un número, o levanta `FormulaInvalida` con un mensaje que le sirve
a quien escribió la fórmula (qué token falló y qué se esperaba), no un
traceback de Python.
"""
from __future__ import annotations

import ast
import math

import pandas as pd


class FormulaInvalida(ValueError):
    """La fórmula no se puede evaluar. El mensaje va a la pantalla."""


# ---------------------------------------------------------------------------
# Funciones de agregación disponibles
# ---------------------------------------------------------------------------
# Cada una recibe una Serie de pandas (o el DataFrame, para `contar`) y
# devuelve un número. Se declaran acá y en ningún otro lado: la lista blanca
# del parser se arma de este diccionario, así que agregar una función es
# agregarla acá y nada más.
def _suma(s):      return float(pd.to_numeric(s, errors="coerce").sum())
def _promedio(s):  return float(pd.to_numeric(s, errors="coerce").mean())
def _minimo(s):    return float(pd.to_numeric(s, errors="coerce").min())
def _maximo(s):    return float(pd.to_numeric(s, errors="coerce").max())
def _mediana(s):   return float(pd.to_numeric(s, errors="coerce").median())
def _desvio(s):    return float(pd.to_numeric(s, errors="coerce").std())
def _distintos(s): return float(s.nunique())


FUNCIONES = {
    "suma": _suma,
    "promedio": _promedio,
    "minimo": _minimo,
    "maximo": _maximo,
    "mediana": _mediana,
    "desvio": _desvio,
    "distintos": _distintos,
}

# `contar` y `contar_si` son aparte: no operan sobre una columna sino sobre
# filas, así que reciben otra cosa y el evaluador las trata distinto.
FUNCIONES_FILA = ("contar", "contar_si")

NOMBRES_FUNCION = tuple(FUNCIONES) + FUNCIONES_FILA

# Operadores permitidos. La división se maneja aparte para no devolver `inf`
# cuando el denominador es cero — una medida que dice "infinito" en un tablero
# es peor que una que dice "sin datos".
_BINARIOS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: _dividir(a, b),
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b if b else float("nan"),
}

_COMPARADORES = {
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


def _dividir(a, b):
    """División que no explota ni miente.

    Dividir por cero es el caso más común de una medida recién escrita (el
    filtro todavía no trajo filas). Devolver `nan` deja que la pantalla muestre
    "sin datos", que es la verdad; devolver 0 diría que la tasa es cero, que es
    falso, y `inf` rompería el formato del número.
    """
    try:
        if b == 0:
            return float("nan")
        return a / b
    except (TypeError, ZeroDivisionError):
        return float("nan")


# ---------------------------------------------------------------------------
# Evaluador
# ---------------------------------------------------------------------------
class _Evaluador(ast.NodeVisitor):
    """Recorre el árbol y calcula. Todo nodo no contemplado se rechaza.

    Hereda de `NodeVisitor` pero define `generic_visit` como un rechazo
    explícito: así, un tipo de nodo que nadie previó (un walrus, un f-string,
    una comprensión) falla cerrado en vez de caer en un camino por defecto.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df

    # --- rechazo por defecto ------------------------------------------------
    def generic_visit(self, node):
        raise FormulaInvalida(
            f"no se permite {type(node).__name__} en una fórmula. "
            "Se pueden usar columnas, números, + - * / y las funciones: "
            + ", ".join(sorted(NOMBRES_FUNCION)))

    # --- nodos permitidos ---------------------------------------------------
    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaInvalida(
                f"solo se admiten números como valores fijos, no {node.value!r}")
        return float(node.value)

    def visit_Name(self, node):
        """Un nombre suelto es una columna."""
        if node.id in self.df.columns:
            return self.df[node.id]
        raise FormulaInvalida(
            f"la columna {node.id!r} no existe. Disponibles: "
            + ", ".join(sorted(self.df.columns)))

    def visit_UnaryOp(self, node):
        valor = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -valor
        if isinstance(node.op, ast.UAdd):
            return valor
        raise FormulaInvalida("operador unario no permitido")

    def visit_BinOp(self, node):
        fn = _BINARIOS.get(type(node.op))
        if fn is None:
            raise FormulaInvalida(
                f"operador no permitido: {type(node.op).__name__}")
        return fn(self.visit(node.left), self.visit(node.right))

    def visit_Compare(self, node):
        """`dias_mora > 90` — da una Serie de booleanos, para `contar_si`."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FormulaInvalida(
                "las comparaciones encadenadas (a < b < c) no están soportadas; "
                "escribilas como dos condiciones")
        fn = _COMPARADORES.get(type(node.ops[0]))
        if fn is None:
            raise FormulaInvalida(
                f"comparador no permitido: {type(node.ops[0]).__name__}")
        return fn(self.visit(node.left), self.visit(node.comparators[0]))

    def visit_BoolOp(self, node):
        """`y`/`o` de pandas sobre Series: & y |.

        Se acepta `and`/`or` de Python porque es lo que un usuario escribe
        naturalmente, y se traduce al operador vectorizado.
        """
        valores = [self.visit(v) for v in node.values]
        combinar = (lambda a, b: a & b) if isinstance(node.op, ast.And) else (lambda a, b: a | b)
        resultado = valores[0]
        for v in valores[1:]:
            resultado = combinar(resultado, v)
        return resultado

    def visit_Call(self, node):
        # Solo se llama a un NOMBRE de la lista blanca. Nada de `obj.metodo()`:
        # `node.func` tiene que ser un `Name`, no un `Attribute`. Es lo que
        # cierra el camino a `(1).__class__.__bases__` y similares.
        if not isinstance(node.func, ast.Name):
            raise FormulaInvalida(
                "solo se pueden llamar las funciones de agregación por nombre")
        nombre = node.func.id
        if node.keywords:
            raise FormulaInvalida("las funciones no llevan argumentos con nombre")

        if nombre == "contar":
            if node.args:
                raise FormulaInvalida("contar() no lleva argumentos; "
                                      "para contar con condición usá contar_si(...)")
            return float(len(self.df))

        if nombre == "contar_si":
            if len(node.args) != 1:
                raise FormulaInvalida("contar_si() lleva una condición, "
                                      "por ejemplo: contar_si(dias_mora > 90)")
            cond = self.visit(node.args[0])
            if not isinstance(cond, pd.Series):
                raise FormulaInvalida(
                    "contar_si() espera una condición sobre una columna, "
                    "por ejemplo: contar_si(dias_mora > 90)")
            return float(cond.sum())

        fn = FUNCIONES.get(nombre)
        if fn is None:
            raise FormulaInvalida(
                f"la función {nombre!r} no existe. Disponibles: "
                + ", ".join(sorted(NOMBRES_FUNCION)))
        if len(node.args) != 1:
            raise FormulaInvalida(f"{nombre}() lleva exactamente una columna")
        serie = self.visit(node.args[0])
        if not isinstance(serie, pd.Series):
            raise FormulaInvalida(
                f"{nombre}() espera una columna, no un número suelto")
        if serie.empty:
            return float("nan")
        return fn(serie)


def evaluar(formula: str, df: pd.DataFrame) -> float:
    """Calcula la fórmula sobre el DataFrame. Devuelve un número.

    Levanta `FormulaInvalida` con un mensaje para el usuario ante cualquier
    problema: sintaxis, columna inexistente, función desconocida o construcción
    no permitida.
    """
    if not isinstance(formula, str) or not formula.strip():
        raise FormulaInvalida("la fórmula está vacía")
    if len(formula) > 500:
        # Un tope evita que una fórmula absurdamente anidada consuma el
        # proceso al parsear. Ninguna medida legítima se acerca.
        raise FormulaInvalida("la fórmula es demasiado larga (máximo 500 caracteres)")
    try:
        arbol = ast.parse(formula, mode="eval")
    except SyntaxError as e:
        raise FormulaInvalida(f"no se entiende la fórmula: {e.msg}") from e

    resultado = _Evaluador(df).visit(arbol)
    if isinstance(resultado, pd.Series):
        raise FormulaInvalida(
            "la fórmula da una columna entera y no un número. "
            "Envolvela en una agregación, por ejemplo: suma(...) o promedio(...)")
    try:
        return float(resultado)
    except (TypeError, ValueError) as e:
        raise FormulaInvalida("la fórmula no da un número") from e


def validar(formula: str, columnas) -> dict:
    """¿La fórmula es válida para una tabla con estas columnas?

    Se usa al guardar la medida, para no descubrir el error recién cuando
    alguien abra el tablero. Prueba contra una tabla vacía con esas columnas:
    alcanza para detectar sintaxis, columnas inexistentes y funciones que no
    existen, que es donde están los errores reales.
    """
    vacio = pd.DataFrame({c: pd.Series(dtype="float64") for c in columnas})
    try:
        evaluar(formula, vacio)
        return {"ok": True, "error": None}
    except FormulaInvalida as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Medidas guardadas
# ---------------------------------------------------------------------------
class Medida:
    """Una medida definida por el cliente."""

    def __init__(self, nombre: str, formula: str, descripcion: str = "",
                 formato: str = "numero"):
        if not nombre or not nombre.strip():
            raise FormulaInvalida("la medida necesita un nombre")
        self.nombre = nombre.strip()
        self.formula = formula
        self.descripcion = descripcion
        # Cómo mostrarla: cambia el formato en pantalla, no el cálculo.
        self.formato = formato if formato in ("numero", "moneda", "porcentaje") else "numero"

    def calcular(self, df: pd.DataFrame) -> dict:
        """Nunca lanza: un tablero con seis medidas no puede quedar en blanco
        porque una esté mal escrita. La que falla se muestra con su error y las
        demás siguen."""
        try:
            valor = evaluar(self.formula, df)
        except FormulaInvalida as e:
            return {"nombre": self.nombre, "valor": None, "error": str(e),
                    "formato": self.formato, "descripcion": self.descripcion}
        if isinstance(valor, float) and math.isnan(valor):
            return {"nombre": self.nombre, "valor": None,
                    "error": "sin datos para calcular",
                    "formato": self.formato, "descripcion": self.descripcion}
        return {"nombre": self.nombre, "valor": valor, "error": None,
                "formato": self.formato, "descripcion": self.descripcion}

    def a_dict(self) -> dict:
        return {"nombre": self.nombre, "formula": self.formula,
                "descripcion": self.descripcion, "formato": self.formato}

    @staticmethod
    def de_dict(d: dict) -> Medida:
        return Medida(d.get("nombre", ""), d.get("formula", ""),
                      d.get("descripcion", ""), d.get("formato", "numero"))


def calcular_todas(medidas, df: pd.DataFrame) -> list[dict]:
    """Evalúa una lista de medidas contra la tabla."""
    return [m.calcular(df) for m in medidas]


def medidas_de_ejemplo() -> list[Medida]:
    """Tres medidas que sirven de arranque y de documentación viva.

    Un campo de fórmula en blanco no lo usa nadie: no se sabe qué se puede
    escribir. Estas muestran las tres formas (agregación simple, cociente entre
    agregaciones, y conteo con condición) sobre columnas que la cartera siempre
    tiene.
    """
    return [
        Medida("Ticket promedio", "promedio(monto_deuda)",
               "Cuánto debe en promedio cada deudor de la cartera", "moneda"),
        Medida("Deuda total", "suma(monto_deuda)",
               "El total que hay para cobrar", "moneda"),
        Medida("% en mora alta", "contar_si(dias_mora > 90) / contar() * 100",
               "Qué parte de la cartera pasó los 90 días", "porcentaje"),
    ]
