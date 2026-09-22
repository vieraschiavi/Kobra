# © 2026 Martín Viera. Todos los derechos reservados.

"""Ingeniería de datos: perfilar, encontrar las claves y unir las tablas.

Es el trabajo que va ANTES de poder usar el resto del producto. El motor de
cobranzas no sirve hasta que alguien entiende la base del cliente, y eso se
hacía a mano en cada implementación.

Lo que se fija acá es lo que, si se rompe, no da error — devuelve un número
distinto. Que es la clase de falla que llega hasta el informe del cliente.
"""
import pandas as pd
import pytest

from kobra import fuentes_datos as fd
from kobra import ingenieria_datos as ing


# --- Tipado: la corrupción silenciosa ---------------------------------------
@pytest.mark.parametrize("valores", [
    ["Cliente 0", "Cliente 1", "Cliente 2"],          # nombres
    ["c0@x.com", "c1@x.com", "c2@x.com"],             # mails
    ["C000", "C001", "C002"],                         # códigos
    ["Suc. 3", "Suc. 4", "Suc. 5"],                   # sucursales
])
def test_una_columna_de_texto_no_se_convierte_en_numeros(valores):
    """El defecto que este módulo tuvo y que hay que dejar cerrado.

    El atajo clásico para leer '$ 1.234,56' es borrar todo lo que no sea
    dígito. Con eso, `"Cliente 7"` queda en `"7"` y `"c3@x.com"` en `"3"`: la
    conversión funciona en el 100% de las filas, así que ningún control de
    "convirtió bien" la frena, y una columna de nombres o de mails termina
    convertida en números. Sin error y sin aviso.
    """
    r = ing._a_numero(pd.Series(valores))
    assert r.isna().all(), (
        f"{valores[0]!r} se convirtió a número: una columna de texto quedaría "
        "destruida sin que nada falle")


def test_el_texto_sobrevive_al_tipado_completo():
    """Y lo mismo por el camino real (`tipar`), no solo en la función suelta."""
    df = pd.DataFrame({"nombre": ["Ana Pérez", "Luis Gómez"],
                       "email": ["a@x.com", "l@x.com"],
                       "monto": ["1.234,56", "9.876,54"]})
    salida, cambios = ing.tipar(df)
    assert salida["nombre"].dtype == object or str(salida["nombre"].dtype) == "str"
    assert pd.api.types.is_numeric_dtype(salida["monto"])
    assert [c["columna"] for c in cambios] == ["monto"]


@pytest.mark.parametrize("crudo,esperado", [
    ("1.234,56", 1234.56),      # formato uruguayo/argentino
    ("1,234.56", 1234.56),      # formato anglosajón
    ("$ 1.234,56", 1234.56),    # con símbolo
    ("(1.234,56)", -1234.56),   # negativo contable
    ("12,00", 12.0),
])
def test_el_separador_decimal_sale_de_la_forma_del_dato(crudo, esperado):
    """Un export uruguayo (`1.234,56`) leído con criterio anglosajón da
    `1.23456`. No rompe nada —por eso es peligroso— y el error es de tres
    órdenes de magnitud sobre una columna de plata."""
    r = ing._a_numero(pd.Series([crudo, crudo]))
    assert float(r.iloc[0]) == pytest.approx(esperado)


# --- Roles -----------------------------------------------------------------
def test_una_categoria_de_tabla_chica_sigue_siendo_categoria():
    """Con la regla de proporción sola, `sucursal` con 3 valores en 50 filas
    da 6% y quedaba como texto libre — cuando es una categoría de manual."""
    df = pd.DataFrame({"sucursal": ["Centro", "Norte", "Sur"] * 17})
    assert ing.rol_columna("sucursal", df["sucursal"]) == ing.DIMENSION


def test_muchos_valores_distintos_no_son_una_categoria():
    """Y la regla absoluta sola falla al revés: 40.000 valores distintos no
    son una categoría por más que sean pocos al lado del total de filas."""
    s = pd.Series(range(300_000)).mod(40_000)
    assert ing.rol_columna("cosa", s) != ing.DIMENSION


def test_un_id_que_se_repite_apunta_a_otra_tabla():
    """La diferencia entre identificador y clave foránea es la que hace útil
    el mapa de joins: uno identifica la fila, el otro apunta afuera."""
    propio = pd.Series([f"C{i}" for i in range(100)])
    ajeno = pd.Series([f"C{i % 10}" for i in range(100)])
    assert ing.rol_columna("id_cliente", propio) == ing.IDENTIFICADOR
    assert ing.rol_columna("id_cliente", ajeno) == ing.CLAVE_FORANEA


def test_un_monto_no_es_una_metrica_cualquiera():
    df = pd.DataFrame({"monto_deuda": [1.0, 2.0, 3.0] * 10,
                       "cantidad_cuotas": [1, 2, 3] * 10})
    p = ing.perfilar(df)
    roles = {c["columna"]: c["rol"] for c in p["detalle"]}
    assert roles["monto_deuda"] == ing.METRICA_MONETARIA
    assert roles["cantidad_cuotas"] == ing.METRICA


# --- Gobernanza: una sola definición de "dato personal" ---------------------
def test_el_perfilado_marca_el_dato_personal_con_la_clasificacion_del_producto():
    """La sensibilidad NO se define acá: sale de `kobra.gobernanza`. Tener dos
    listas de qué es dato personal en el mismo producto termina con una
    desactualizada, y la que se desactualiza es siempre la copia."""
    from kobra import gobernanza as kgob
    df = pd.DataFrame({"email": ["a@x.com"], "monto": [1.0]})
    p = ing.perfilar(df)
    sens = {c["columna"]: c["sensibilidad"] for c in p["detalle"]}
    assert sens["email"] == kgob.clasificar("email")
    assert sens["email"] in (kgob.PERSONAL, kgob.SENSIBLE)


# --- Joins: la mejora que justifica el módulo -------------------------------
def _dos_tablas():
    clientes = pd.DataFrame({"IdCliente": [f"C{i:03d}" for i in range(40)],
                             "sucursal": ["Centro", "Norte"] * 20})
    gestiones = pd.DataFrame({"id_gestion": range(120),
                              "cliente_id": [f"C{i % 40:03d}" for i in range(120)]})
    return {"clientes": clientes, "gestiones": gestiones}


def test_encuentra_el_join_aunque_las_columnas_no_se_llamen_igual():
    """En un ERP de verdad la misma entidad es `IdCliente` en una tabla y
    `cliente_id` en otra. Un detector que compara nombres literales no
    encuentra ninguno de esos joins — justo los que hacen falta."""
    tablas = _dos_tablas()
    js = ing.joins_sugeridos(tablas)
    assert js, "no encontró el join entre IdCliente y cliente_id"
    j = js[0]
    assert {j["columna_izquierda"], j["columna_derecha"]} == {"IdCliente", "cliente_id"}
    assert j["mismo_nombre"] is False
    assert j["solape_pct"] == pytest.approx(100.0)
    assert j["cardinalidad"] == "1:N"


def test_un_join_que_multiplica_filas_se_avisa_fuerte():
    """N:N es la forma más común de inflar un informe sin que nada falle: se
    duplican filas y por lo tanto se duplica cualquier suma de plata."""
    a = pd.DataFrame({"zona": ["N", "S"] * 30})
    b = pd.DataFrame({"zona": ["N", "S"] * 30})
    js = ing.joins_sugeridos({"a": a, "b": b})
    assert js and js[0]["cardinalidad"] == "N:N"
    assert js[0]["riesgo"].startswith("ALTO")
    assert "infla" in js[0]["riesgo"] or "multiplica" in js[0]["riesgo"]


def test_no_inventa_joins_entre_columnas_que_no_son_clave():
    """Sin la pista del nombre, dos columnas cuyos valores se pisan de
    casualidad no son un join. Comparar una fecha contra un monto porque
    coinciden los números es ruido."""
    a = pd.DataFrame({"monto": [1.0, 2.0, 3.0] * 10})
    b = pd.DataFrame({"cantidad": [1.0, 2.0, 3.0] * 10})
    assert ing.joins_sugeridos({"a": a, "b": b}) == []


def test_el_nombre_distinto_exige_mas_evidencia():
    """Cuando los nombres coinciden, el nombre ya es evidencia. Cuando no,
    la tiene que dar entera el dato — por eso la vara de solapamiento sube."""
    assert ing._SOLAPE_MINIMO_DISTINTO_NOMBRE > ing._SOLAPE_MINIMO


# --- Claves ----------------------------------------------------------------
def test_encuentra_la_clave_primaria():
    df = pd.DataFrame({"id": range(100), "valor": [1] * 100})
    ks = ing.claves(df, ing.perfilar(df), "t")
    assert any(k["columna"] == "id" and k["confianza"] == "alta" for k in ks["pk"])


def test_encuentra_una_clave_compuesta_cuando_no_hay_simple():
    """Una tabla de movimientos no tiene columna única: la identifica el par
    cliente + fecha."""
    df = pd.DataFrame({"id_cliente": ["A", "A", "B", "B"],
                       "fecha": pd.to_datetime(["2026-01-01", "2026-01-02"] * 2),
                       "monto_pago": [100.0, 100.0, 250.0, 250.0]})
    ks = ing.claves(df, ing.perfilar(df), "t")
    assert any(k["tipo"] == "PK compuesta" for k in ks["pk"])


def test_un_importe_unico_de_casualidad_no_se_propone_como_clave():
    """En una muestra chica, que ningún saldo se repita es lo esperable — no
    evidencia de que sea una clave. Proponerlo llena la pantalla de candidatas
    falsas y entierra la verdadera."""
    df = pd.DataFrame({"id": ["A", "A", "B", "B"],
                       "monto_deuda": [1.0, 2.0, 3.0, 4.0]})
    ks = ing.claves(df, ing.perfilar(df), "t")
    assert not any(k["columna"] == "monto_deuda" for k in ks["pk"])


# --- DDL: el nombre de columna es entrada del cliente -----------------------
def test_un_nombre_de_columna_hostil_no_se_cuela_en_el_ddl():
    """El nombre de columna lo pone el archivo del cliente, así que es entrada
    externa y termina dentro de un CREATE TABLE. Se construye por lista blanca
    y no escapando lo peligroso: filtrar lo malo siempre deja algo afuera."""
    df = pd.DataFrame({"ok": [1, 2], "x); DROP TABLE clientes;--": [3, 4]})
    ddl = ing.generar_ddl("t", ing.perfilar(df))
    # Lo que importa no es que la PALABRA "drop" desaparezca —dentro de un
    # identificador es inofensiva— sino que no queden los caracteres capaces
    # de cerrar la sentencia y abrir otra.
    for peligroso in [");", ";--", "--", ")", ";"]:
        assert peligroso not in ddl.split("CREATE TABLE")[1].split("(")[1].split(")")[0], (
            f"el identificador conserva {peligroso!r}: puede cerrar el CREATE "
            "TABLE y encadenar otra sentencia")
    assert "x___DROP_TABLE_clientes" in ddl   # neutralizado, no borrado


def test_una_columna_que_empieza_con_numero_sigue_siendo_valida():
    df = pd.DataFrame({"2026_total": [1, 2]})
    ddl = ing.generar_ddl("t", ing.perfilar(df))
    assert "c_2026_total" in ddl


# --- Features ---------------------------------------------------------------
def test_la_feature_que_mira_el_futuro_viene_marcada():
    """`dias_desde_max` se calcula contra el máximo del DATASET. En producción
    esa fecha todavía no existe: la feature es útil, pero usarla sin
    recalcular el corte es fuga temporal, y el modelo miente para arriba."""
    df = pd.DataFrame({"fecha_pago": pd.date_range("2026-01-01", periods=40),
                       "monto": range(40)})
    _f, dicc = ing.features(df, ing.perfilar(df))
    fuga = [d for d in dicc if d["aviso"]]
    assert fuga, "ninguna feature avisa de fuga temporal"
    assert any("dias_desde_max" in d["feature"] for d in fuga)


def test_toda_feature_trae_su_formula():
    """Una feature que nadie puede explicar no se defiende ante un comité de
    riesgo, y en cobranzas eso significa que no se puede usar."""
    df = pd.DataFrame({"fecha": pd.date_range("2026-01-01", periods=40),
                       "saldo": range(40)})
    _f, dicc = ing.features(df, ing.perfilar(df))
    assert dicc
    for d in dicc:
        assert d["formula"] and d["origen"]


# --- Fuentes de datos -------------------------------------------------------
def test_una_consulta_a_mano_no_se_ejecuta_cruda():
    """Una pantalla de 'explorá tus datos' que ejecute lo que le escriban es
    una consola SQL con los permisos del servicio — contra la base de
    PRODUCCIÓN del cliente. Se valida con la misma función que ya protege el
    asistente de consultas."""
    fuente = (fd.__file__)
    texto = open(fuente, encoding="utf-8").read()
    assert "validar_sql" in texto, "la consulta del usuario no pasa por la validación"


def test_toda_lectura_tiene_tope_de_filas():
    """Un `SELECT *` contra una tabla de cientos de millones de filas no es un
    error del usuario: es lo que cualquiera hace la primera vez."""
    assert fd.LIMITE_FILAS > 0
    envuelta = fd._limitar("postgresql://x", "SELECT * FROM t", 100)
    assert "LIMIT 100" in envuelta
    # SQL Server no entiende LIMIT.
    assert "TOP 100" in fd._limitar("mssql+pyodbc://x", "SELECT * FROM t", 100)


def test_el_tope_envuelve_la_consulta_en_vez_de_pegarle_texto():
    """La consulta del usuario puede traer su propio LIMIT, un ORDER BY o ser
    un WITH. Concatenar al final rompe los tres casos."""
    envuelta = fd._limitar("postgresql://x", "SELECT a FROM t ORDER BY a", 50)
    assert envuelta.strip().startswith("SELECT")
    assert "ORDER BY a" in envuelta


def test_una_fuente_vacia_dice_que_falta(tmp_path):
    with pytest.raises(fd.FuenteInvalida, match="No se indicó"):
        fd.cargar("")
    with pytest.raises(fd.FuenteInvalida, match="No existe"):
        fd.cargar(str(tmp_path / "no_esta.csv"))


def test_lee_un_csv_con_punto_y_coma_y_latin1(tmp_path):
    """El export de un ERP latinoamericano no llega en UTF-8 con comas."""
    p = tmp_path / "cartera.csv"
    p.write_bytes("nombre;ciudad\nJosé;Montevideo\nAndrés;Salto\n".encode("latin-1"))
    tablas = fd.cargar(str(p))
    df = tablas["cartera.csv"]
    assert list(df.columns) == ["nombre", "ciudad"]
    assert len(df) == 2


def test_lee_un_sqlite_con_varias_tablas(tmp_path):
    import sqlite3
    p = tmp_path / "erp.db"
    cx = sqlite3.connect(p)
    cx.execute("CREATE TABLE clientes (id TEXT, nombre TEXT)")
    cx.execute("INSERT INTO clientes VALUES ('C1','Ana'), ('C2','Luis')")
    cx.execute("CREATE TABLE pagos (id_pago INTEGER, id TEXT)")
    cx.execute("INSERT INTO pagos VALUES (1,'C1'), (2,'C1'), (3,'C2')")
    cx.commit()
    cx.close()
    tablas = fd.cargar(str(p))
    assert set(tablas) == {"clientes", "pagos"}
    assert len(tablas["pagos"]) == 3


def test_el_recorrido_completo_sobre_dos_tablas():
    """La prueba de integración: de tablas crudas a joins, claves y DDL."""
    r = ing.analizar(_dos_tablas())
    assert set(r["tablas"]) == {"clientes", "gestiones"}
    assert r["joins"], "no encontró cómo se unen las tablas"
    assert r["claves"]["gestiones"]["pk"]
    assert "CREATE TABLE" in r["ddl"]["clientes"]
    assert "version: 2" in r["dbt"]["clientes"]


def test_una_tabla_vacia_no_rompe_el_analisis():
    """Un cliente sube un CSV con encabezados y ninguna fila. No puede tirar
    una excepción sin explicación."""
    r = ing.analizar({"vacia": pd.DataFrame({"a": [], "b": []})})
    assert r["perfiles"]["vacia"]["filas"] == 0


# --- Cuando NO hay clave: decir cuál de los tres caminos fue ----------------
# «No se encontró una columna que identifique cada fila» es el mensaje que
# recibió un archivo real de cobranzas de 504 filas × 23 columnas. Hay tres
# caminos distintos que terminan ahí y desde la pantalla se veían iguales, así
# que no había nada que hacer con el aviso salvo adivinar.
def _cartera_de_cobranzas(filas: int = 504, repetidas: int = 17):
    """La forma de un export de cobranzas que de verdad NO tiene clave.

    `repetidas` filas son idénticas en TODAS las columnas salvo el importe:
    el mismo cliente, el mismo comprobante, el mismo vencimiento, dos veces,
    con montos distintos. Es la forma normal de un export que trae una fila
    por movimiento del comprobante —cuota, nota de crédito, ajuste— y es la
    razón más probable de que un archivo así no tenga clave: lo único que
    distingue esas filas es una columna de plata, que se descarta a propósito.

    Importa que el fixture sea así y no «casi único»: con una columna que se
    repite pero filas distintas en lo demás, el par cliente + comprobante SÍ
    es clave y el camino que se quiere probar nunca se ejecuta.
    """
    base = filas - repetidas
    idx = list(range(base)) + list(range(repetidas))   # las últimas, repetidas
    return pd.DataFrame({
        "cod_cliente": [f"C{i % 120:04d}" for i in idx],
        "nro_documento": [f"D{i:05d}" for i in idx],
        "sucursal": [f"Suc. {i % 8}" for i in idx],
        "fecha_vto": pd.to_datetime("2026-01-01") + pd.to_timedelta(
            [i % 90 for i in idx], unit="D"),
        "dias_de_atraso": [i % 300 for i in idx],
        # Lo único distinto entre las filas repetidas, y es plata.
        "saldo_vencido": [1000.0 + i for i in range(filas)],
    })


def test_el_fixture_de_cobranzas_no_tiene_clave_de_verdad():
    """Si esta forma tuviera clave, los dos tests de abajo se saltearían
    solos y pasarían sin afirmar nada. Se fija acá, explícito."""
    df = _cartera_de_cobranzas()
    assert len(df) == 504
    assert ing.claves(df, ing.perfilar(df), "cobranzas")["pk"] == []


def test_sin_clave_se_dice_cual_columna_estuvo_cerca_y_por_cuanto():
    """«487 de 504» no se lee igual que «12 de 504»: el número es lo que
    dice si falta un ajuste o si la tabla directamente no tiene clave."""
    df = _cartera_de_cobranzas()
    ks = ing.claves(df, ing.perfilar(df), "cobranzas")
    diag = ks["diagnostico"]
    assert diag["filas"] == 504
    assert diag["mejor"]["columna"] == "nro_documento"
    assert diag["mejor"]["repetidas"] == 17


def test_el_importe_descartado_se_nombra_en_vez_de_desaparecer():
    """Un saldo único de casualidad no es una clave y por eso se saltea. Pero
    si no se dice, el usuario ve «no hay clave» mirando una columna que él
    sabe única y concluye que el programa está roto."""
    df = pd.DataFrame({"categoria": ["A", "A", "B", "B"],
                       "monto_deuda": [1.0, 2.0, 3.0, 4.0]})
    ks = ing.claves(df, ing.perfilar(df), "t")
    diag = ks.get("diagnostico")
    assert diag is not None
    assert "monto_deuda" in diag["descartadas_monto"]
    assert "monto_deuda" in ing.explicar_falta_de_clave(diag)


def test_la_clave_compuesta_se_busca_por_cardinalidad_y_no_por_posicion():
    """El defecto que hacía fallar una tabla ancha: se tomaban las primeras
    6 columnas POR POSICIÓN. En un export de 23 columnas, la candidata
    verdadera se quedaba afuera por estar en la posición 11."""
    relleno = {f"marca_{i}": ["si", "no"] * 6 for i in range(9)}
    df = pd.DataFrame({
        **relleno,                                    # 9 columnas de relleno
        "cod_cliente": [f"C{i:02d}" for i in range(12)],
        "periodo": pd.to_datetime("2026-01-01") + pd.to_timedelta(
            [0] * 12, unit="D"),
    })
    ks = ing.claves(df, ing.perfilar(df), "ancha")
    assert any(k["tipo"] in ("PK simple", "PK candidata", "PK compuesta")
               for k in ks["pk"]), ks


def test_cuando_hay_clave_no_se_arrastra_un_diagnostico_al_pedo():
    df = pd.DataFrame({"id": range(100), "valor": [1] * 100})
    assert "diagnostico" not in ing.claves(df, ing.perfilar(df), "t")


def test_la_explicacion_nombra_las_columnas_que_se_probaron():
    """Sin la lista, «se probaron todos los pares» es una afirmación que el
    usuario no puede verificar ni corregir."""
    df = _cartera_de_cobranzas()
    ks = ing.claves(df, ing.perfilar(df), "cobranzas")
    texto = ing.explicar_falta_de_clave(ks["diagnostico"])
    for col in ks["diagnostico"]["compuesta_probadas"]:
        assert f"`{col}`" in texto


def test_sin_diagnostico_la_explicacion_no_revienta():
    """La app la llama con `.get(...) or {}`: nunca puede tirar."""
    assert ing.explicar_falta_de_clave({}) == ""


# --- El archivo real: «cobranzas al 3105», 504 filas × 23 columnas ----------
# El usuario reportó «No se encontró una columna que identifique cada fila»
# sobre una tabla que tiene clave perfecta. La causa, medida sobre el archivo:
# la tabla es un agregado mensual con grano
# `Año + Mes + Estado + TipoCliente` — 36 períodos × 14 combinaciones = 504 —
# y el detector fallaba por DOS razones independientes, las dos necesarias:
#
#   1. `Año` y `Mes` son enteros, y toda columna numérica se leía como
#      métrica. Las métricas no entran a la búsqueda de claves, así que las
#      únicas candidatas eran `Estado` (13) y `TipoCliente` (3): 39
#      combinaciones para 504 filas.
#   2. La búsqueda sólo probaba PARES. Aun con las cuatro candidatas, el par
#      de mayor cardinalidad da 13 × 12 = 156. Ninguna búsqueda por pares
#      podía encontrarla, por exhaustiva que fuera.
def _cobranza_mensual():
    """La forma exacta del archivo: 4 años × ... = 36 períodos × 14 combos."""
    estados = ["Cobranza/Mora Temprana", "Cobranza/Negociación",
               "Comercial/Normal", "Comercial/Promesa Gerencia",
               "Comercial/Suspensión SC", "Contaduría/Fallecido",
               "Contaduría/Socios a Gestionar", "Contaduría/Venta",
               "Jurídica/Extrajudicial", "Jurídica/Extrajudicial SOMA",
               "Jurídica/Judicial", "Prejurídica/Gestión", "Suspendidos/Baja"]
    # 14 combinaciones: `Cobranza/Negociación` viene partida en Puro/Impuro.
    combos = [(e, "N/A") for e in estados if e != "Cobranza/Negociación"]
    combos += [("Cobranza/Negociación", "Puro"),
               ("Cobranza/Negociación", "Impuro")]
    periodos = [(a, m) for a in (2023, 2024, 2025, 2026) for m in range(1, 13)]
    filas = [{"FechaObs": "00:00.0", "Año": a, "Mes": m,
              "Estado": e, "TipoCliente": t,
              "MontoACobrarVencido": float(1000 + i),
              "SociosCobrados": i % 97}
             for i, ((a, m), (e, t)) in enumerate(
                 (p, c) for p in periodos[:36] for c in combos)]
    return pd.DataFrame(filas)


def test_el_archivo_de_cobranzas_del_cliente_tiene_clave_y_se_encuentra():
    df = _cobranza_mensual()
    assert df.shape[0] == 504, "el fixture tiene que ser el tamaño del real"
    ks = ing.claves(df, ing.perfilar(df), "cobranzas al 3105")
    assert ks["pk"], "volvió a quedarse sin clave: " + str(ks.get("diagnostico"))
    cols = set(ks["pk"][0]["columna"].split(" + "))
    assert cols == {"Año", "Mes", "Estado", "TipoCliente"}, cols
    # Y es clave de verdad, no una casualidad del detector.
    assert len(df.drop_duplicates(subset=list(cols))) == len(df)


def test_un_ano_y_un_mes_son_dimension_temporal_y_no_una_medida():
    """Causa 1. Sumar meses no significa nada; promediar años tampoco. Con
    rol de métrica quedaban fuera de la búsqueda de claves."""
    df = _cobranza_mensual()
    roles = {c["columna"]: c["rol"] for c in ing.perfilar(df)["detalle"]}
    assert roles["Año"] == ing.FECHA
    assert roles["Mes"] == ing.FECHA


@pytest.mark.parametrize("columna", ["meses_de_atraso", "semanas_sin_pagar",
                                     "cantidad_cuotas"])
def test_una_cantidad_medida_en_meses_sigue_siendo_una_medida(columna):
    """El contra-caso, que es lo que hace estrecha la regla: `mes` tiene que
    pegar en `Mes` y NO en `meses_de_atraso`, que sí se promedia."""
    s = pd.Series([1, 2, 3, 4, 5] * 20)
    assert ing.rol_columna(columna, s) == ing.METRICA


def test_una_clave_de_cuatro_columnas_no_se_encuentra_probando_pares():
    """Causa 2, aislada: con las cuatro candidatas bien clasificadas, el par
    de MAYOR cardinalidad da 13 × 12 = 156 para 504 filas. Si alguien vuelve
    a bajar la aridad a 2, este test lo agarra."""
    assert ing._MAX_ARIDAD_COMPUESTA >= 4
    df = _cobranza_mensual()
    mejores = [("Estado", "Mes"), ("Estado", "Año"), ("Mes", "TipoCliente")]
    for par in mejores:
        assert df.duplicated(subset=list(par)).any(), par


def test_la_clave_compuesta_no_arrastra_columnas_que_no_hacen_falta():
    """La búsqueda agrega de a una; sin podar, `FechaObs` —que tiene UN solo
    valor en las 504 filas— podía quedar adentro de la clave."""
    df = _cobranza_mensual()
    ks = ing.claves(df, ing.perfilar(df), "t")
    assert "FechaObs" not in ks["pk"][0]["columna"]


# --- Tamaño: el tope tiene que PROTEGER, no sólo recortar lo que se ve ------
# La diferencia se ve en la memoria, no en el resultado: `read(...)` seguido
# de `.head(tope)` devuelve exactamente lo mismo que un lector que se corta
# solo, y por eso el defecto sobrevive a cualquier test de contenido. Medido
# sobre un parquet de 5.000.000 de filas: devolver 50.000 costaba un pico de
# 1.230 MiB, contra 212 MiB leyendo por grupos de filas.
def _parquet_grande(tmp_path, filas=300_000):
    ruta = tmp_path / "grande.parquet"
    pd.DataFrame({"id": range(filas),
                  "texto": [f"v{i % 977}" for i in range(filas)],
                  "monto": [float(i) for i in range(filas)]}).to_parquet(ruta)
    return ruta


def test_el_parquet_se_lee_por_grupos_y_no_entero(tmp_path):
    from kobra import fuentes_datos as fd
    ruta = _parquet_grande(tmp_path)
    df = next(iter(fd.cargar(str(ruta), limite=1_000).values()))
    assert len(df) == 1_000
    assert list(df.columns) == ["id", "texto", "monto"]
    # Y el contenido es el principio del archivo, no una muestra al azar.
    assert df["id"].tolist() == list(range(1_000))


def test_el_lector_de_parquet_no_materializa_el_archivo_entero(tmp_path):
    """El control que distingue «recorta» de «protege».

    Se cuenta cuántas filas ve pyarrow: si el camino fuera
    `read_parquet(...).head(n)`, las vería TODAS.
    """
    import pyarrow.parquet as pq

    from kobra import fuentes_datos as fd
    ruta = _parquet_grande(tmp_path)
    vistas = 0
    original = pq.ParquetFile.iter_batches

    def espia(self, *a, **k):
        nonlocal vistas
        for lote in original(self, *a, **k):
            vistas += lote.num_rows
            yield lote

    pq.ParquetFile.iter_batches = espia
    try:
        fd.cargar(str(ruta), limite=1_000)
    finally:
        pq.ParquetFile.iter_batches = original
    assert 0 < vistas < 300_000, (
        f"leyó {vistas:,} filas para devolver 1.000: el tope no protege nada")


def test_se_avisa_cuando_el_excel_es_grande_y_por_que():
    """Veinte segundos de espera sin explicación se leen como «el programa
    es lento». Con la explicación se leen como «cambiá el formato»."""
    from kobra import fuentes_datos as fd
    assert fd.MAX_FILAS_XLSX == 1_048_576


def test_un_csv_chico_no_arrastra_la_advertencia(tmp_path):
    from kobra import fuentes_datos as fd
    p = tmp_path / "chico.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    assert fd.advertencia_tamano(str(p)) == ""


def test_un_excel_grande_dice_el_tope_del_formato_y_la_alternativa(tmp_path):
    from kobra import fuentes_datos as fd
    p = tmp_path / "gordo.xlsx"
    p.write_bytes(b"0" * (25 * 2 ** 20))     # no hace falta que sea válido
    aviso = fd.advertencia_tamano(str(p))
    assert "1.048.576" in aviso or "1,048,576" in aviso
    assert "parquet" in aviso and "CSV" in aviso
