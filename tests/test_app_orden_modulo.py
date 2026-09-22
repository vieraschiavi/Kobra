"""El tablero es un guion, no un módulo: el orden de las líneas ES el programa.

`app/app.py` corre de arriba abajo cada vez que Streamlit lo recarga. Una
función definida DEBAJO de donde se la llama no es un detalle de estilo:
revienta con `NameError` en el arranque, con la app entera en blanco.

Y no lo ve nadie de los controles que ya hay. `python3 -m py_compile` sólo
parsea; `ruff` marca nombres que no existen en ningún lado, no los que
existen más abajo. La única forma de verlo sin navegador era abrir la app —
que acá pide contraseña.

Ya pasó dos veces en este archivo: `_mostrar_gestores()` llamada antes de
definirla, y `cargar_gestiones()` movida a `_fuente_activa()` cuando la
definición quedó veinte líneas más abajo. Las dos veces el módulo compilaba.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app" / "app.py"

#: Hasta dónde se sigue la cadena de llamadas. Con 6 alcanza y sobra para
#: un guion plano, y corta cualquier recursión mutua sin llevar un set de
#: visitados por rama.
PROFUNDIDAD = 6


def _defs_de_modulo(arbol: ast.Module) -> dict[str, ast.FunctionDef]:
    """Las funciones definidas en el cuerpo del módulo, por nombre."""
    return {n.name: n for n in arbol.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _nombres_llamados(nodo: ast.AST) -> set[str]:
    """Los nombres que `nodo` invoca como función, en cualquier nivel."""
    return {h.func.id for h in ast.walk(nodo)
            if isinstance(h, ast.Call) and isinstance(h.func, ast.Name)}


def _usos_prematuros(arbol: ast.Module) -> list[str]:
    """Llamadas de módulo a funciones que todavía no existen en esa línea."""
    defs = _defs_de_modulo(arbol)
    faltas: list[str] = []

    def _revisar(nodo: ast.AST, linea_ejecucion: int, camino: str,
                 resto: int) -> None:
        if resto == 0:
            return
        for nombre in sorted(_nombres_llamados(nodo)):
            definida = defs.get(nombre)
            if definida is None:          # builtin, import o método: no es asunto
                continue
            if definida.lineno > linea_ejecucion:
                faltas.append(
                    f"línea {linea_ejecucion}: {camino} llama a `{nombre}()`, "
                    f"que recién se define en la línea {definida.lineno}")
                continue
            # Se definió antes, pero su CUERPO puede llamar a algo que no.
            _revisar(definida, linea_ejecucion, f"{camino} → {nombre}()",
                     resto - 1)

    for sentencia in arbol.body:
        if isinstance(sentencia, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
            continue                      # cuerpo diferido: corre después
        _revisar(sentencia, sentencia.lineno, "el módulo", PROFUNDIDAD)

    return faltas


def test_ninguna_funcion_se_usa_antes_de_existir():
    faltas = _usos_prematuros(ast.parse(APP.read_text(encoding="utf-8")))
    assert not faltas, "app/app.py revienta al arrancar:\n" + "\n".join(faltas)


def test_el_control_detecta_el_caso_que_se_le_escapo_a_py_compile():
    """El guardia tiene que fallar con el defecto real, no sólo pasar.

    Esto es el bug tal como estaba: `_fuente_activa()` se ejecutaba en la
    línea 243 y llamaba a `cargar_gestiones`, definida en la 248.
    """
    roto = ast.parse(
        "def temprano():\n"
        "    return tarde()\n"
        "valor = temprano()\n"
        "def tarde():\n"
        "    return 1\n")
    faltas = _usos_prematuros(roto)
    assert len(faltas) == 1
    assert "`tarde()`" in faltas[0]
    assert "temprano()" in faltas[0]


def test_el_control_no_acusa_al_orden_correcto():
    """Sin esto, un guardia que devuelve siempre una falta también pasaría
    el test de arriba."""
    sano = ast.parse(
        "def tarde():\n"
        "    return 1\n"
        "def temprano():\n"
        "    return tarde()\n"
        "valor = temprano()\n")
    assert _usos_prematuros(sano) == []
