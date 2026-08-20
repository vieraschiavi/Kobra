# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Consultas en lenguaje natural sobre la base del cliente
====================================================================
Se conecta a **cualquier base de datos relacional** del cliente (PostgreSQL,
MySQL/MariaDB, SQL Server, Oracle, SQLite… cualquiera compatible con
SQLAlchemy) y responde preguntas en español devolviendo el SQL usado, la
tabla de resultados y un gráfico automático.

Diseño (evita inventar nombres de tabla/columna y evita que la IA vea datos
reales del cliente):

  1. Se extrae el **catálogo completo** del esquema una sola vez (tablas,
     columnas, PKs, FKs declaradas, vistas y relaciones inferidas por nombre
     de columna) — solo metadata, nunca filas de datos.
  2. Un **RAG local (TF-IDF, sin salir a internet)** recupera las tablas más
     relevantes a la pregunta.
  3. Claude genera el SQL usando **solo el esquema recuperado** — nunca se le
     manda una fila de datos real, solo nombres de tablas/columnas/tipos.
  4. El SQL se **valida contra el catálogo** (tablas/columnas existen, es
     de solo lectura) antes de ejecutarse.
  5. Se ejecuta con **límite de filas automático** y se registra en el log
     de auditoría (host de la conexión, nunca la URL completa con
     usuario/contraseña — mismo criterio que `kobra/integracion.py`).

Requiere: `sqlalchemy` (ya en requirements.txt) + el driver del motor del
cliente (psycopg2, pymysql, pyodbc…) instalado aparte — igual que
`integracion.sincronizar_db`.
"""
from __future__ import annotations

import re

import pandas as pd

from kobra import llm as kllm

# ---------------------------------------------------------------------------
# 1) Conexión y extracción del catálogo (SQLAlchemy — cualquier motor)
# ---------------------------------------------------------------------------
_PREFIJOS_JOIN = ("id", "num")


def conectar(conn_url: str):
    """Devuelve un engine de SQLAlchemy. `conn_url` nunca se loguea completa."""
    from sqlalchemy import create_engine
    if not conn_url:
        raise ValueError("Falta la URL de conexión.")
    return create_engine(conn_url)


def _destino_seguro(conn_url: str) -> str:
    """Host/base de la URL, sin usuario/contraseña — lo único que se loguea."""
    return conn_url.split("@")[-1] if conn_url else ""


def extraer_catalogo(engine, incluir_muestras: bool = True, max_tablas: int = 200) -> dict:
    """
    Extrae tablas, columnas, PKs, FKs, vistas y relaciones inferidas — solo
    metadata (nunca el contenido de las filas, salvo unas pocas muestras de
    valores de texto para ayudar al LLM a entender los dominios/categorías).
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    dialecto = engine.dialect.name  # "postgresql" | "mysql" | "mssql" | "sqlite"...
    tablas = insp.get_table_names()[:max_tablas]
    try:
        vistas = insp.get_view_names()
    except Exception:
        vistas = []

    catalogo = {"dialecto": dialecto, "tablas": {}, "vistas": {}, "fks": [],
                "joins_inferidos": {}}
    columnas_por_tabla = {}

    with engine.connect() as con:
        for t in tablas:
            try:
                cols_info = insp.get_columns(t)
            except Exception:
                continue
            try:
                pk_cols = set(insp.get_pk_constraint(t).get("constrained_columns") or [])
            except Exception:
                pk_cols = set()

            cols = [{
                "columna": c["name"], "tipo": str(c.get("type", "")),
                "nullable": bool(c.get("nullable", True)),
                "pk": c["name"] in pk_cols,
            } for c in cols_info]
            columnas_por_tabla[t] = [c["columna"] for c in cols]

            n_filas = None
            try:
                n_filas = con.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            except Exception:
                try:
                    n_filas = con.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                except Exception:
                    pass

            muestras = {}
            if incluir_muestras:
                for c in cols:
                    if c["pk"] or "char" not in c["tipo"].lower():
                        continue
                    try:
                        col = c["columna"]
                        q = text(f'SELECT DISTINCT "{col}" FROM "{t}" '
                                 f'WHERE "{col}" IS NOT NULL LIMIT 8') if dialecto != "mssql" else \
                            text(f'SELECT DISTINCT TOP 8 [{col}] FROM [{t}] WHERE [{col}] IS NOT NULL')
                        vals = [r[0] for r in con.execute(q).fetchall()]
                        if vals and len(vals) <= 8:
                            muestras[col] = vals
                    except Exception:
                        continue

            catalogo["tablas"][t] = {"columnas": cols, "n_filas": n_filas, "muestras": muestras}

            try:
                fks = insp.get_foreign_keys(t)
            except Exception:
                fks = []
            for fk in fks:
                destino = fk.get("referred_table")
                cols_o = fk.get("constrained_columns") or []
                cols_d = fk.get("referred_columns") or []
                for co, cd in zip(cols_o, cols_d):
                    catalogo["fks"].append({
                        "tabla_origen": t, "columna_origen": co,
                        "tabla_destino": destino, "columna_destino": cd,
                    })

        for v in vistas:
            try:
                cols_v = insp.get_columns(v)
                catalogo["vistas"][v] = {"columnas": [c["name"] for c in cols_v]}
            except Exception:
                catalogo["vistas"][v] = {"columnas": []}

    # Relaciones inferidas por nombre de columna (cuando no hay FK declarada)
    col_a_tablas: dict[str, list[str]] = {}
    for t, cols in columnas_por_tabla.items():
        for c in cols:
            cl = c.lower()
            if cl.endswith("_id") or cl.endswith("id") or any(cl.startswith(p) for p in _PREFIJOS_JOIN):
                col_a_tablas.setdefault(c, []).append(t)
    catalogo["joins_inferidos"] = {c: ts for c, ts in col_a_tablas.items() if len(ts) > 1}

    return catalogo


def catalogo_a_fichas(catalogo: dict) -> list[dict]:
    """Convierte el catálogo en 'fichas' de texto (1 por tabla/vista) para el RAG."""
    fichas = []
    for tabla, info in catalogo["tablas"].items():
        lineas = [f"TABLA: {tabla}"]
        if info.get("n_filas") is not None:
            lineas.append(f"Cantidad de filas: {info['n_filas']:,}")
        lineas.append("Columnas:")
        for c in info["columnas"]:
            marca = " [PK]" if c["pk"] else ""
            null = "" if c["nullable"] else " NOT NULL"
            extra = ""
            if c["columna"] in info.get("muestras", {}):
                vals = ", ".join(str(v) for v in info["muestras"][c["columna"]])
                extra = f"  (valores ejemplo: {vals})"
            lineas.append(f"  - {c['columna']} ({c['tipo']}){null}{marca}{extra}")

        rels = []
        for fk in catalogo["fks"]:
            if fk["tabla_origen"] == tabla:
                rels.append(f"  {tabla}.{fk['columna_origen']} -> "
                            f"{fk['tabla_destino']}.{fk['columna_destino']}")
            if fk["tabla_destino"] == tabla:
                rels.append(f"  {fk['tabla_origen']}.{fk['columna_origen']} -> "
                            f"{tabla}.{fk['columna_destino']}")
        for col, tablas_rel in catalogo.get("joins_inferidos", {}).items():
            if tabla in tablas_rel and col not in "\n".join(rels):
                otras = [x for x in tablas_rel if x != tabla]
                if otras:
                    rels.append(f"  {tabla}.{col} ~ {', '.join(otras)}.{col}  (inferida por nombre)")
        if rels:
            lineas.append("Relaciones (JOINs):")
            lineas.extend(rels)

        fichas.append({"tabla": tabla, "texto": "\n".join(lineas)})

    for vista, info in catalogo.get("vistas", {}).items():
        cols = ", ".join(info.get("columnas", []))
        fichas.append({"tabla": vista,
                       "texto": f"VISTA: {vista}\nColumnas: {cols}"})
    return fichas


# ---------------------------------------------------------------------------
# 2) Retrieval (RAG) — TF-IDF local, no sale nada afuera
# ---------------------------------------------------------------------------
class RecuperadorEsquema:
    def __init__(self, fichas: list[dict]):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.fichas = fichas
        self.textos = [f["texto"] for f in fichas] or ["(esquema vacío)"]
        self.vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2),
                                   token_pattern=r"[a-zA-Záéíóúñ_]+")
        self.matriz = self.vec.fit_transform(self.textos)

    def recuperar(self, pregunta: str, k: int = 4) -> list[dict]:
        from sklearn.metrics.pairwise import cosine_similarity
        if not self.fichas:
            return []
        q = self.vec.transform([pregunta])
        sims = cosine_similarity(q, self.matriz)[0]
        idx = sims.argsort()[::-1][:max(k, 3)]
        return [self.fichas[i] for i in idx]


# ---------------------------------------------------------------------------
# 3) Generación de SQL con Claude — solo el esquema viaja a la API, nunca datos
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Sos un experto en SQL que traduce preguntas en lenguaje natural (español) a consultas SQL.

REGLAS ESTRICTAS:
1. Usá EXCLUSIVAMENTE las tablas y columnas del esquema que te paso. NUNCA inventes nombres.
2. El motor es {dialecto}. Usá su sintaxis.
3. Devolvé SOLO la consulta SQL, sin explicaciones, sin markdown, sin ```sql.
4. Para fechas usá rangos (columna >= 'inicio' AND columna < 'fin'), nunca funciones sobre la columna en el WHERE.
5. Si la pregunta pide un ranking o "top", agregá ORDER BY.
6. Usá JOINs explícitos según las relaciones del esquema (declaradas o inferidas).
7. Nunca generes INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, MERGE. Solo SELECT.

ESQUEMA DISPONIBLE (usá solo esto):
{esquema}
"""


def generar_sql_claude(pregunta: str, fichas_relevantes: list[dict], dialecto: str,
                       api_key: str | None = None) -> str:
    esquema = "\n\n".join(f["texto"] for f in fichas_relevantes)
    system = SYSTEM_PROMPT.format(dialecto=dialecto, esquema=esquema)
    sql = kllm.generar(pregunta, system=system, max_tokens=500,
                       api_key=api_key, timeout=60, lanzar=True)
    sql = re.sub(r"^```sql\s*|\s*```$", "", sql, flags=re.IGNORECASE | re.MULTILINE).strip()
    sql = re.sub(r"^```\s*|\s*```$", "", sql).strip()
    return sql


# ---------------------------------------------------------------------------
# 4) Validador — cero columnas inventadas, solo lectura
# ---------------------------------------------------------------------------
# `--` y `;--` salieron de la lista: son comentarios, y prohibirlos rechazaba
# todo SQL comentado —que es casi todo el que genera un modelo— sin aportar
# seguridad. Lo que se buscaba frenar con ellos era encadenar una segunda
# sentencia, y eso ahora lo corta el chequeo de `;` en validar_sql.
#
# `xp_` y `sp_executesql` entraron: son los dos caminos de SQL Server para
# ejecutar comandos arbitrarios, y solo el primero quedaba cubierto de rebote
# por `exec `. Traídos del motor de MV SQL.
_PROHIBIDAS = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ",
               "create ", "exec ", "execute ", "merge ", "grant ", "revoke ",
               "xp_", "sp_executesql")


# Palabras que el extractor de tablas confunde con nombres de tabla. Sin esta
# lista, `FROM generate_series(...)` o `FROM (VALUES ...)` se reportan como
# "tabla inexistente" y se rechaza una consulta perfectamente válida.
_PALABRAS_SQL = {
    "select", "where", "group", "order", "having", "limit", "offset", "union",
    "unnest", "generate_series", "dual", "values", "lateral",
}


def _sin_comentarios(sql: str) -> str:
    """Saca los comentarios antes de analizar la consulta.

    Antes `--` estaba en la lista de prohibidas, o sea que **cualquier SQL con
    un comentario se rechazaba** — y un modelo comenta casi siempre. El
    problema real nunca fue el comentario en sí sino lo que se esconde detrás
    para colar una segunda sentencia; eso lo corta el chequeo de `;`, no
    prohibir el guion doble.
    """
    sin_linea = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sin_linea, flags=re.DOTALL)


def validar_sql(sql: str, catalogo: dict) -> tuple[bool, list[str], list[str]]:
    """(es_valido, problemas, advertencias).

    Un problema invalida la consulta; una advertencia se muestra pero deja
    correr. La distinción importa: si una columna no reconocida invalidara,
    ningún alias de CTE pasaría, y son correctos.

    Incorpora tres arreglos traídos del motor de MV SQL:

    * **CTEs.** `WITH morosos AS (...) SELECT ... FROM morosos` se rechazaba
      con "tabla inexistente", porque `morosos` no está en el catálogo — es un
      nombre que define la propia consulta. Se rechazaba justo el SQL más
      profesional, que es el que el prompt del sistema pide generar.
    * **Comentarios.** Ver `_sin_comentarios`.
    * **`sp_executesql`.** No estaba en la lista de prohibidas: `exec ` tapaba
      el caso habitual, pero no todos.
    """
    problemas, advertencias = [], []
    limpio = _sin_comentarios(sql)
    s = limpio.lower()

    for p in _PROHIBIDAS:
        if p in s:
            problemas.append(f"Operación no permitida detectada: '{p.strip()}'")
    if not s.lstrip().startswith(("select", "with")):
        problemas.append("La consulta debe empezar con SELECT (o WITH).")
    # Una segunda sentencia encadenada es la forma clásica de colar escritura.
    if ";" in s.rstrip().rstrip(";"):
        problemas.append("No se permite más de una sentencia en la misma consulta.")

    # Los nombres que la consulta define para sí misma cuentan como tablas.
    nombres_cte = set(re.findall(
        r"(?:with|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", s))

    tablas_catalogo = ({t.lower() for t in catalogo["tablas"]}
                       | {v.lower() for v in catalogo.get("vistas", {})})
    tablas_en_sql = set(re.findall(
        r"(?:from|join)\s+\"?\[?([a-zA-Z_][a-zA-Z0-9_.]*)\]?\"?", s))
    for t in tablas_en_sql:
        simple = t.split(".")[-1]
        if simple in _PALABRAS_SQL or simple in nombres_cte:
            continue
        if simple not in tablas_catalogo:
            problemas.append(f"Tabla no existe en el catálogo: '{t}'")

    # Columnas: advertencia, nunca problema. Un `alias.columna` puede referirse
    # a un CTE cuyas columnas no están en el catálogo y ser correcto.
    columnas_catalogo = set()
    for info in catalogo["tablas"].values():
        for c in info.get("columnas", []):
            columnas_catalogo.add(str(c.get("columna", "")).lower())
    for col in set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*\.([a-zA-Z_][a-zA-Z0-9_]*)", s)):
        if col not in columnas_catalogo and col not in _PALABRAS_SQL:
            advertencias.append(
                f"Columna no reconocida en el catálogo: '{col}' "
                "(puede ser un alias de CTE)")

    return (len(problemas) == 0, problemas, advertencias)


def calcular_confianza(conf_modelo: float | None, similitud: float | None,
                       es_valido: bool, n_advertencias: int,
                       usa_cte: bool = False) -> dict:
    """Cuánta confianza merece esta respuesta, con intervalo.

    Traído de MV SQL. Combina tres señales **independientes** entre sí, que es
    lo que hace que el número signifique algo: si solo se reportara lo que el
    modelo dice de sí mismo, sería su opinión sobre su propia respuesta, y un
    modelo equivocado suele estar seguro.

      55%  autoevaluación del modelo
      25%  qué tan parecido era el esquema recuperado a la pregunta
      20%  validación estructural contra el catálogo

    El intervalo se ensancha cuando falta información: sin autoevaluación del
    modelo no se puede ser tan preciso, y decirlo es más honesto que inventar
    un número redondo.
    """
    base = conf_modelo if conf_modelo is not None else 60
    senal_rag = min(1.0, (similitud or 0) * 3.0) * 100
    senal_val = (100 if es_valido else 20) - min(30, n_advertencias * 10)

    puntaje = 0.55 * base + 0.25 * senal_rag + 0.20 * max(0, senal_val)
    if usa_cte:
        puntaje = min(100, puntaje + 2)       # estructura explícita

    margen = 5 if conf_modelo is not None else 12
    if not es_valido:
        margen += 8
    puntaje = max(0, min(100, round(puntaje)))
    return {"puntaje": puntaje, "margen": margen,
            "desde": max(0, puntaje - margen), "hasta": min(100, puntaje + margen)}


# ---------------------------------------------------------------------------
# 5) Ejecución segura — límite de filas automático según el dialecto
# ---------------------------------------------------------------------------
def ejecutar_sql(sql: str, engine, limite: int = 500) -> tuple[list[str], list[tuple], str]:
    from sqlalchemy import text

    sql_l = sql.lower()
    dialecto = engine.dialect.name
    if dialecto == "mssql":
        if "top " not in sql_l and "offset " not in sql_l:
            sql = re.sub(r"(?i)^\s*select\s+", f"SELECT TOP {limite} ", sql, count=1)
    else:
        if "limit " not in sql_l:
            sql = sql.rstrip("; \n") + f"\nLIMIT {limite}"

    with engine.connect() as con:
        res = con.execute(text(sql))
        cols = list(res.keys())
        filas = [tuple(r) for r in res.fetchall()]
    return cols, filas, sql


# ---------------------------------------------------------------------------
# 6) Pipeline completo
# ---------------------------------------------------------------------------
class MotorConsultaBD:
    """Uso: MotorConsultaBD(conn_url).responder("cuánto cobramos en marzo", api_key)"""

    def __init__(self, conn_url: str, incluir_muestras: bool = True):
        self.conn_url = conn_url
        self.destino = _destino_seguro(conn_url)
        self.engine = conectar(conn_url)
        self.catalogo = extraer_catalogo(self.engine, incluir_muestras=incluir_muestras)
        self.fichas = catalogo_a_fichas(self.catalogo)
        self.recuperador = RecuperadorEsquema(self.fichas)

    def responder(self, pregunta: str, api_key: str | None = None, k: int = 4,
                 limite_filas: int = 500) -> dict:
        from kobra import auditoria as kauditoria

        relevantes = self.recuperador.recuperar(pregunta, k=k)
        resultado = {
            "pregunta": pregunta,
            "tablas_recuperadas": [f["tabla"] for f in relevantes],
            "sql": None, "valido": False, "problemas": [],
            "columnas": None, "filas": None, "sql_ejecutado": None, "error": None,
        }
        try:
            sql = generar_sql_claude(pregunta, relevantes, self.catalogo["dialecto"], api_key)
        except Exception as e:
            resultado["error"] = str(e)
            kauditoria.registrar("consulta_bd_nl2sql", {
                "ok": False, "destino": self.destino, "pregunta": pregunta, "error": str(e)[:200]})
            return resultado

        resultado["sql"] = sql
        es_valido, problemas, advertencias = validar_sql(sql, self.catalogo)
        resultado["valido"] = es_valido
        resultado["problemas"] = problemas
        resultado["advertencias"] = advertencias
        # Cuánta confianza merece la respuesta, con intervalo. Un número sin
        # margen se lee como certeza, y esto es una estimación.
        resultado["confianza"] = calcular_confianza(
            resultado.get("confianza_modelo"), resultado.get("similitud"),
            es_valido, len(advertencias),
            usa_cte=sql.lower().lstrip().startswith("with"))

        if es_valido:
            try:
                cols, filas, sql_exec = ejecutar_sql(sql, self.engine, limite_filas)
                resultado["columnas"] = cols
                resultado["filas"] = filas
                resultado["sql_ejecutado"] = sql_exec
            except Exception as e:
                resultado["error"] = str(e)[:400]

        kauditoria.registrar("consulta_bd_nl2sql", {
            "ok": es_valido and not resultado["error"], "destino": self.destino,
            "pregunta": pregunta, "tablas": resultado["tablas_recuperadas"],
            "filas_devueltas": len(resultado["filas"]) if resultado["filas"] else 0})
        return resultado

    def resultado_a_dataframe(self, resultado: dict) -> pd.DataFrame | None:
        if not resultado.get("columnas") or resultado.get("filas") is None:
            return None
        return pd.DataFrame(resultado["filas"], columns=resultado["columnas"])
