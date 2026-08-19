# © 2026 Martín Viera. Todos los derechos reservados.

"""El validador de SQL generado: qué deja pasar y qué corta.

Es la única barrera entre lo que escribe un modelo de lenguaje y la base de
datos de producción del cliente, así que tiene dos formas de fallar y las dos
importan:

  * **de más** — rechazar SQL correcto. El costo no es cosmético: si el SQL
    profesional (con CTEs, comentado) se rechaza, el cliente aprende que la
    función no anda y deja de usarla. Es la falla que más se subestima porque
    no aparece como error de seguridad.
  * **de menos** — dejar pasar una escritura o una ejecución de comandos.

Los tres arreglos que se prueban acá vienen del motor de MV SQL, que ya los
tenía resueltos, y los tres estaban rotos en Kobra:

  1. una consulta con CTE se rechazaba con "tabla inexistente";
  2. cualquier consulta comentada se rechazaba, porque `--` estaba prohibido;
  3. `sp_executesql` pasaba sin bloquearse.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import consulta_bd as kcbd  # noqa: E402


@pytest.fixture()
def catalogo():
    return {
        "dialecto": "postgresql",
        "tablas": {
            "cartera": {"columnas": [{"columna": "id_deudor"},
                                     {"columna": "monto_deuda"},
                                     {"columna": "dias_mora"}]},
            "gestiones": {"columnas": [{"columna": "id_deudor"},
                                       {"columna": "resultado"}]},
        },
        "vistas": {},
    }


# ---------------------------------------------------------------------------
# Que no rechace de más
# ---------------------------------------------------------------------------
def test_una_consulta_con_cte_es_valida(catalogo):
    """El bug: `morosos` no está en el catálogo porque lo define la propia
    consulta. Se rechazaba justo el SQL que el prompt del sistema pide."""
    sql = ("WITH morosos AS (SELECT * FROM cartera WHERE dias_mora > 90) "
           "SELECT count(*) FROM morosos")
    ok, problemas, _ = kcbd.validar_sql(sql, catalogo)
    assert ok, problemas


def test_varios_cte_encadenados_tambien(catalogo):
    sql = ("WITH morosos AS (SELECT * FROM cartera WHERE dias_mora > 90), "
           "con_gestion AS (SELECT m.* FROM morosos m JOIN gestiones g "
           "ON g.id_deudor = m.id_deudor) SELECT count(*) FROM con_gestion")
    ok, problemas, _ = kcbd.validar_sql(sql, catalogo)
    assert ok, problemas


def test_una_consulta_comentada_es_valida(catalogo):
    """Un modelo comenta el SQL casi siempre. Prohibir `--` rechazaba todo eso
    sin aportar seguridad: lo que se quería frenar era encadenar sentencias."""
    sql = "-- deudores con más de 90 días\nSELECT * FROM cartera"
    ok, problemas, _ = kcbd.validar_sql(sql, catalogo)
    assert ok, problemas


def test_un_comentario_de_bloque_tambien(catalogo):
    ok, problemas, _ = kcbd.validar_sql(
        "/* reporte mensual */ SELECT * FROM cartera", catalogo)
    assert ok, problemas


def test_una_columna_desconocida_avisa_pero_no_bloquea(catalogo):
    """Si invalidara, ningún alias de CTE pasaría — y son correctos."""
    sql = ("WITH t AS (SELECT id_deudor, count(*) AS veces FROM gestiones "
           "GROUP BY id_deudor) SELECT t.veces FROM t")
    ok, problemas, advertencias = kcbd.validar_sql(sql, catalogo)
    assert ok, problemas
    assert any("veces" in a for a in advertencias)


def test_las_funciones_de_tabla_no_se_confunden_con_tablas(catalogo):
    """`FROM generate_series(...)` no es una tabla del catálogo y es válido."""
    ok, problemas, _ = kcbd.validar_sql(
        "SELECT * FROM generate_series(1, 10)", catalogo)
    assert ok, problemas


# ---------------------------------------------------------------------------
# Que no deje pasar de menos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sql", [
    "DELETE FROM cartera WHERE 1=1",
    "UPDATE cartera SET monto_deuda = 0",
    "DROP TABLE cartera",
    "INSERT INTO cartera VALUES (1)",
    "TRUNCATE TABLE cartera",
    "GRANT SELECT ON cartera TO publico",
    "REVOKE ALL ON cartera FROM publico",
])
def test_toda_escritura_se_bloquea(catalogo, sql):
    ok, problemas, _ = kcbd.validar_sql(sql, catalogo)
    assert not ok, f"pasó una escritura: {sql}"
    assert problemas


@pytest.mark.parametrize("sql", [
    "SELECT * FROM cartera; EXEC xp_cmdshell 'dir'",
    "SELECT * FROM cartera WHERE 1=1 AND sp_executesql N'DROP TABLE cartera'",
    "SELECT * FROM cartera WHERE x = xp_cmdshell('dir')",
])
def test_la_ejecucion_de_comandos_se_bloquea(catalogo, sql):
    """`sp_executesql` no estaba en la lista: `exec ` tapaba el caso habitual
    pero no todos. Es ejecución de SQL arbitrario en SQL Server."""
    ok, problemas, _ = kcbd.validar_sql(sql, catalogo)
    assert not ok, f"pasó una ejecución de comandos: {sql}"


def test_no_se_puede_encadenar_una_segunda_sentencia(catalogo):
    """La forma clásica de colar una escritura detrás de un SELECT válido."""
    ok, problemas, _ = kcbd.validar_sql(
        "SELECT * FROM cartera; SELECT 1", catalogo)
    assert not ok
    assert any("una sentencia" in p for p in problemas)


def test_una_escritura_escondida_tras_un_comentario_no_pasa(catalogo):
    """Sacar `--` de las prohibidas no puede haber abierto esta puerta."""
    ok, _, _ = kcbd.validar_sql(
        "SELECT * FROM cartera -- inocente\n; DROP TABLE cartera", catalogo)
    assert not ok


def test_una_tabla_inventada_se_bloquea(catalogo):
    """El otro modo de fallar del modelo: alucinar un nombre de tabla."""
    ok, problemas, _ = kcbd.validar_sql("SELECT * FROM tabla_fantasma", catalogo)
    assert not ok
    assert any("no existe" in p for p in problemas)


def test_debe_empezar_con_select_o_with(catalogo):
    ok, problemas, _ = kcbd.validar_sql("CALL algun_procedimiento()", catalogo)
    assert not ok


# ---------------------------------------------------------------------------
# Confianza con intervalo
# ---------------------------------------------------------------------------
def test_la_confianza_viene_con_margen(catalogo):
    """Un número sin margen se lee como certeza, y esto es una estimación."""
    c = kcbd.calcular_confianza(85, 0.4, True, 0)
    assert c["desde"] < c["puntaje"] < c["hasta"]
    assert 0 <= c["desde"] and c["hasta"] <= 100


def test_sin_autoevaluacion_del_modelo_el_margen_se_ensancha(catalogo):
    """Decir 'no sé cuánto sé' es más honesto que inventar un número redondo."""
    con = kcbd.calcular_confianza(85, 0.4, True, 0)
    sin = kcbd.calcular_confianza(None, 0.4, True, 0)
    assert sin["margen"] > con["margen"]


def test_un_sql_invalido_baja_la_confianza(catalogo):
    valido = kcbd.calcular_confianza(85, 0.4, True, 0)
    invalido = kcbd.calcular_confianza(85, 0.4, False, 0)
    assert invalido["puntaje"] < valido["puntaje"]
    assert invalido["margen"] > valido["margen"]


def test_las_advertencias_bajan_la_confianza(catalogo):
    limpio = kcbd.calcular_confianza(85, 0.4, True, 0)
    con_dudas = kcbd.calcular_confianza(85, 0.4, True, 3)
    assert con_dudas["puntaje"] < limpio["puntaje"]


def test_la_confianza_nunca_se_va_de_rango(catalogo):
    """Un puntaje de 112% o -4% en pantalla destruye la credibilidad de todo
    lo demás que muestre el programa."""
    for conf in (None, 0, 50, 100):
        for sim in (None, 0, 0.5, 1.0, 99):
            for valido in (True, False):
                c = kcbd.calcular_confianza(conf, sim, valido, 0, usa_cte=True)
                assert 0 <= c["puntaje"] <= 100, c
                assert 0 <= c["desde"] <= 100 and 0 <= c["hasta"] <= 100, c
