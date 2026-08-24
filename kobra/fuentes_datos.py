# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Lectura de fuentes de datos
==========================================
De dónde salen las tablas que después perfila `kobra.ingenieria_datos`:
archivos (CSV, Excel, Parquet, JSON), SQLite y **bases de datos vía
SQLAlchemy** — Postgres, SQL Server, MySQL, Oracle, Databricks.

Dos decisiones que no son de comodidad
--------------------------------------
**1. Una consulta escrita a mano no se ejecuta cruda.** Pasa por
`kobra.consulta_bd.validar_sql`, la misma validación que ya protege el resto
del producto: solo `SELECT`/`WITH`, una sola sentencia, y bloqueo de escritura,
lectura de archivos del servidor (`load_file`, `pg_read_file`) y conexiones
salientes (`dblink`, `openrowset`). Sin esto, una pantalla de "explorá tus
datos" es una consola SQL con los permisos del servicio.

**2. Todo lectura trae tope de filas.** Un `SELECT *` contra una tabla de
cientos de millones de filas no es un error del usuario, es lo que cualquiera
hace la primera vez. El tope convierte "el servidor se quedó sin memoria" en
"te muestro una muestra".
"""
from __future__ import annotations

import os

import pandas as pd

# Tope por defecto. Alcanza de sobra para perfilar —los porcentajes de nulos y
# la cardinalidad se estabilizan mucho antes— y no compromete la memoria del
# servicio.
LIMITE_FILAS = 50_000
# Cuántas tablas se traen cuando el usuario apunta a una base entera sin elegir.
MAX_TABLAS = 15

EXT_TABULAR = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".parquet",
               ".json", ".jsonl", ".ndjson")
EXT_SQLITE = (".db", ".sqlite", ".sqlite3", ".db3")


class FuenteInvalida(ValueError):
    """La fuente no se puede leer, y el mensaje dice por qué."""


def _leer_csv(path: str, sep: str | None = None, encoding: str | None = None,
              limite: int | None = LIMITE_FILAS) -> pd.DataFrame:
    """CSV real, no CSV de manual.

    Un export de un ERP latinoamericano llega en `latin-1` con `;` de
    separador tanto como en UTF-8 con comas. Se prueban las combinaciones
    hasta que una da una tabla con más de una columna: una sola columna casi
    siempre significa que el separador estaba mal, no que la tabla tenga una
    sola columna.
    """
    seps = [sep] if sep else [None, ";", ",", "\t", "|"]
    encodings = [encoding] if encoding else ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    ultimo_error = None
    respaldo = None
    for enc in encodings:
        for s in seps:
            try:
                df = pd.read_csv(path, sep=s, encoding=enc, nrows=limite,
                                 engine="python", on_bad_lines="skip")
            except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
                ultimo_error = exc
                continue
            if df.shape[1] == 1 and s in (None, ","):
                respaldo = df          # quizá el separador esté mal: seguir probando
                continue
            return df
    if respaldo is not None:
        return respaldo
    raise FuenteInvalida(f"No se pudo leer el CSV: {ultimo_error}")


def _leer_archivo(path: str, hoja: str | None = None,
                  limite: int | None = LIMITE_FILAS,
                  sep: str | None = None,
                  encoding: str | None = None) -> dict[str, pd.DataFrame]:
    ext = os.path.splitext(path)[1].lower()
    base = os.path.basename(path)
    if ext in (".csv", ".tsv", ".txt"):
        return {base: _leer_csv(path, sep, encoding, limite)}
    if ext in (".xlsx", ".xlsm", ".xls"):
        hojas = pd.read_excel(path, sheet_name=hoja if hoja else None, nrows=limite)
        if isinstance(hojas, pd.DataFrame):
            return {hoja or base: hojas}
        return {str(k): v for k, v in hojas.items()}
    if ext == ".parquet":
        df = pd.read_parquet(path)
        return {base: df.head(limite) if limite else df}
    if ext in (".json", ".jsonl", ".ndjson"):
        lineas = ext in (".jsonl", ".ndjson")
        try:
            df = pd.read_json(path, lines=lineas)
        except ValueError:
            df = pd.read_json(path, lines=not lineas)
        return {base: df.head(limite) if limite else df}
    if ext in EXT_SQLITE:
        return leer_sqlite(path, limite=limite)
    raise FuenteInvalida(
        f"Extensión no soportada: {ext}. Se leen {', '.join(EXT_TABULAR + EXT_SQLITE)}.")


def leer_sqlite(path: str, tabla: str | None = None,
                limite: int | None = LIMITE_FILAS) -> dict[str, pd.DataFrame]:
    import sqlite3
    cx = sqlite3.connect(path)
    try:
        nombres = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'", cx)["name"].tolist()
        if tabla:
            nombres = [t for t in nombres if t.lower() == str(tabla).lower()]
            if not nombres:
                raise FuenteInvalida(f"La tabla {tabla!r} no existe en {os.path.basename(path)}")
        salida = {}
        for t in nombres[:MAX_TABLAS]:
            # El nombre sale de sqlite_master, no del usuario: no hay
            # interpolación de entrada externa acá.
            lim = f" LIMIT {int(limite)}" if limite else ""
            salida[t] = pd.read_sql_query(f'SELECT * FROM "{t}"{lim}', cx)
        return salida
    finally:
        cx.close()


def _limitar(url: str, sql: str, limite: int) -> str:
    """Envuelve una consulta para que no pueda traer la tabla entera.

    Se envuelve en vez de concatenar `LIMIT`: la consulta del usuario puede ya
    tener su propio `LIMIT`, un `ORDER BY` o ser un `WITH`, y pegarle texto al
    final rompe los tres. SQL Server además no entiende `LIMIT`.
    """
    if url.startswith("mssql"):
        return f"SELECT TOP {int(limite)} * FROM (\n{sql}\n) AS consulta_kobra"
    return f"SELECT * FROM (\n{sql}\n) AS consulta_kobra LIMIT {int(limite)}"


def leer_base(url: str, tabla: str | None = None, query: str | None = None,
              esquema: str | None = None,
              limite: int | None = LIMITE_FILAS) -> dict[str, pd.DataFrame]:
    """Lee de una base vía SQLAlchemy.

    `query` NO se ejecuta tal cual: se valida contra el catálogo real de la
    base con la misma función que usa el asistente de consultas. Una pantalla
    que ejecute lo que le escriban es una consola SQL con los permisos del
    servicio, y este producto corre contra la base de producción del cliente.
    """
    from sqlalchemy import inspect, text

    from kobra import consulta_bd as kbd

    engine = kbd.conectar(url)
    limite = limite or LIMITE_FILAS

    with engine.connect() as cx:
        cx.execute(text("SELECT 1"))       # que falle acá y no a mitad de la lectura

        if query:
            catalogo = kbd.extraer_catalogo(engine, incluir_muestras=False)
            ok, problemas, _adv = kbd.validar_sql(query, catalogo)
            if not ok:
                raise FuenteInvalida("La consulta fue rechazada: " + "; ".join(problemas))
            return {"consulta": pd.read_sql_query(text(_limitar(url, query, limite)), cx)}

        inspector = inspect(engine)
        disponibles = inspector.get_table_names(schema=esquema)
        if tabla:
            # Contra la lista real del inspector: así el nombre que se
            # interpola en el SELECT nunca es texto libre del usuario.
            reales = [t for t in disponibles if t.lower() == str(tabla).lower()]
            if not reales:
                raise FuenteInvalida(
                    f"La tabla {tabla!r} no existe. Hay: {', '.join(disponibles[:20])}")
            objetivo = reales
        else:
            objetivo = disponibles[:MAX_TABLAS]
        if not objetivo:
            raise FuenteInvalida("La base no tiene tablas visibles para este usuario.")

        salida, fallidas = {}, []
        for t in objetivo:
            completo = f"{esquema}.{t}" if esquema else t
            try:
                salida[t] = pd.read_sql_query(
                    text(_limitar(url, f"SELECT * FROM {completo}", limite)), cx)
            except Exception as exc:            # noqa: BLE001 — una tabla sin permiso no corta el resto
                fallidas.append(f"{t} ({type(exc).__name__})")
        if not salida:
            raise FuenteInvalida("No se pudo leer ninguna tabla: " + ", ".join(fallidas))
        return salida


def cargar(fuente: str, tabla: str | None = None, query: str | None = None,
           hoja: str | None = None, esquema: str | None = None,
           limite: int | None = LIMITE_FILAS,
           sep: str | None = None, encoding: str | None = None
           ) -> dict[str, pd.DataFrame]:
    """Punto de entrada único: devuelve `{nombre_tabla: DataFrame}`.

    Una URL de conexión se distingue de una ruta por el `://`. `file://` no
    cuenta — es una ruta escrita de otra forma.
    """
    texto = str(fuente or "").strip()
    if not texto:
        raise FuenteInvalida("No se indicó ninguna fuente.")

    if "://" in texto and not texto.startswith("file://"):
        return leer_base(texto, tabla, query, esquema, limite)

    path = texto[len("file://"):] if texto.startswith("file://") else texto
    if os.path.isdir(path):
        salida, errores = {}, []
        for archivo in sorted(os.listdir(path)):
            ext = os.path.splitext(archivo)[1].lower()
            if ext not in EXT_TABULAR and ext not in EXT_SQLITE:
                continue
            try:
                salida.update(_leer_archivo(os.path.join(path, archivo),
                                            hoja, limite, sep, encoding))
            except (FuenteInvalida, OSError, ValueError) as exc:
                errores.append(f"{archivo}: {exc}")
        if not salida:
            detalle = (" Se saltearon: " + "; ".join(errores[:5])) if errores else ""
            raise FuenteInvalida(
                "La carpeta no tiene archivos tabulares legibles." + detalle)
        return salida

    if not os.path.exists(path):
        raise FuenteInvalida(f"No existe la ruta: {path}")
    return _leer_archivo(path, hoja, limite, sep, encoding)
