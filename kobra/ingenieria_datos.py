# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Ingeniería de datos
==================================
Le da a un cliente la respuesta a las preguntas que aparecen ANTES de poder
usar el resto del producto: qué hay en mis datos, cómo se unen mis tablas,
cuál es la clave, qué está roto y qué features puedo derivar.

Hasta acá eso se resolvía a mano —o con un script suelto por cliente— y era
justo el trabajo que frenaba una implementación: el motor de cobranzas es
inútil hasta que alguien entiende la base del cliente.

Qué NO se reimplementa acá
--------------------------
Este módulo se apoya en lo que ya existe en vez de duplicarlo, que es lo que
lo mantiene chico y coherente con el resto:

* `kobra.gobernanza` — clasificación (público/interno/personal/sensible) y las
  seis dimensiones DAMA. El perfilado marca el dato personal usando ESA
  clasificación, no una lista propia que se desincronice.
* `kobra.consulta_bd` — conexión SQLAlchemy y, sobre todo, `validar_sql`. Una
  consulta escrita por el usuario NO se ejecuta cruda: pasa por la misma
  validación que el resto del producto, que bloquea escrituras, lectura de
  archivos y conexiones salientes.
* `kobra.automl` — el modelado. Acá se preparan features; entrenar es de allá.

Lo que sí es propio
-------------------
1. **Perfilado con rol de columna.** No solo el dtype: si una columna es
   identificador, clave foránea, dimensión, métrica, monto o fecha. El rol es
   lo que después decide qué feature tiene sentido derivar y qué join
   proponer.
2. **Detección de claves.** PK simple, PK candidata y PK compuesta.
3. **Joins sugeridos entre tablas**, con solapamiento real de valores,
   cardinalidad y riesgo — incluyendo columnas que **no se llaman igual**,
   que es el caso normal en un ERP de verdad.
4. **Features derivadas** con aviso de fuga temporal.
5. **DDL y modelo dbt** a partir de lo perfilado.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from kobra import gobernanza as kgob

# --- Roles de columna ------------------------------------------------------
# El rol es una lectura de NEGOCIO, no un tipo de dato: `monto_deuda` y
# `cantidad_cuotas` son las dos numéricas y no se tratan igual.
IDENTIFICADOR = "identificador"
CLAVE_FORANEA = "clave_foranea"
DIMENSION = "dimension"
METRICA = "metrica"
METRICA_MONETARIA = "metrica_monetaria"
FECHA = "fecha"
TEXTO_LIBRE = "texto_libre"
BOOLEANO = "booleano"
CONSTANTE = "constante"

_PAT_FECHA = re.compile(r"(fec|fch|date|dt_|_dt|fecha|periodo|mes|alta|baja|vto|venc)", re.I)
_PAT_ID = re.compile(r"(^id|_id$|codigo|cod_|nro|numero|documento|cedula|ruc|cuit|clave|key)", re.I)
_PAT_MONTO = re.compile(
    r"(monto|importe|saldo|valor|precio|total|deuda|cobrad|pagad|amount|revenue)", re.I)

# Una dimensión es una columna con pocos valores distintos. Hacen falta las
# dos reglas y no alcanza con ninguna sola:
#
# * La PROPORCIÓN sola falla en tablas chicas: `sucursal` con 3 valores en 50
#   filas da 6% y quedaría afuera, cuando es una categoría de manual.
# * El ABSOLUTO solo falla en tablas grandes: en 10 millones de filas, una
#   columna con 400.000 valores distintos no es una categoría por más que
#   "400.000" suene a poco al lado de 10 millones.
#
# Así que alcanza con cumplir cualquiera de las dos, con un techo duro arriba.
_MAX_CARDINALIDAD_DIMENSION = 0.05
_DIMENSION_SIEMPRE_HASTA = 25      # tan pocos valores que es categoría sí o sí
_TOPE_ABSOLUTO_DIMENSION = 200     # techo: más que esto no es una categoría


def rol_columna(nombre: str, serie: pd.Series) -> str:
    """Qué ES esta columna para el negocio, no de qué tipo es."""
    filas = len(serie)
    unicos = int(serie.nunique(dropna=True))
    if filas == 0 or unicos <= 1:
        return CONSTANTE
    if pd.api.types.is_datetime64_any_dtype(serie):
        return FECHA
    # El nombre se mira ANTES que la heurística de dos valores. Una tabla con
    # dos clientes tiene `id_cliente` con dos valores distintos, y llamarla
    # "booleano" la saca de la búsqueda de claves y del mapa de joins — que es
    # exactamente para lo que sirve. Una columna que se llama `id_cliente`
    # nunca es un booleano, tenga los valores que tenga.
    if _PAT_ID.search(nombre or ""):
        # Un id que no se repite identifica la fila; uno que se repite apunta a
        # otra tabla. Esa diferencia es la que hace útil el mapa de joins.
        return IDENTIFICADOR if unicos >= filas * 0.95 else CLAVE_FORANEA
    if pd.api.types.is_bool_dtype(serie) or (unicos == 2 and not
                                             pd.api.types.is_numeric_dtype(serie)):
        return BOOLEANO
    if pd.api.types.is_numeric_dtype(serie):
        return METRICA_MONETARIA if _PAT_MONTO.search(nombre or "") else METRICA
    por_proporcion = unicos <= filas * _MAX_CARDINALIDAD_DIMENSION
    if (unicos <= _DIMENSION_SIEMPRE_HASTA or por_proporcion) and \
            unicos <= _TOPE_ABSOLUTO_DIMENSION:
        return DIMENSION
    return TEXTO_LIBRE


# --- Tipado ----------------------------------------------------------------
# Lo que puede rodear a un número sin dejar de serlo: símbolos de moneda,
# espacios (incluido el duro de Excel) y el signo entre paréntesis contable.
_RUIDO_MONEDA = re.compile(r"[\s $€£¥]|(?:^\()|(?:\)$)|(?:^(?:USD|UYU|ARS|BRL|EUR)\b)",
                           re.I)
# Y cómo tiene que quedar después de sacarle eso para ser un número.
_FORMA_NUMERO = re.compile(r"^-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?$|^-?\d+(?:[.,]\d+)?$")


def _a_numero(serie: pd.Series) -> pd.Series:
    """Texto tipo '1.234,56', '$ 1,234.56' o '(1.234)' a número.

    Dos cuidados, y los dos vienen de haber visto el daño:

    **No se borran las letras.** El atajo de sacar todo lo que no sea dígito
    deja `"Cliente 7"` en `"7"` y `"c3@x.com"` en `"3"`: la conversión
    "funciona" en el 100% de las filas y una columna de nombres o de mails
    queda convertida en números, sin error y sin aviso. Acá el valor tiene que
    tener FORMA de número una vez sacado el ruido de moneda; si le quedan
    letras, no es un número y se descarta.

    **El decimal se decide por la forma del dato, no por el locale del
    servidor.** Una exportación uruguaya (`1.234,56`) leída con criterio
    anglosajón da `1.23456`: el error es de tres órdenes de magnitud y no
    rompe nada, que es lo que lo hace peligroso.
    """
    s = serie.astype("string").str.strip()
    limpio = s.str.replace(_RUIDO_MONEDA, "", regex=True)

    # Si la mayoría de los valores no tienen forma de número, esta columna es
    # texto: no se toca ninguno.
    presentes = limpio.notna() & (limpio.str.len() > 0)
    if presentes.sum() == 0:
        return pd.Series(pd.NA, index=serie.index, dtype="Float64")
    parece = limpio[presentes].str.match(_FORMA_NUMERO)
    if parece.mean() < 0.9:
        return pd.Series(pd.NA, index=serie.index, dtype="Float64")

    # Si el último separador es la coma, la coma es el decimal.
    ultima_coma = limpio.str.rfind(",")
    ultimo_punto = limpio.str.rfind(".")
    coma_decimal = bool(((ultima_coma > ultimo_punto) & (ultima_coma >= 0)).mean() > 0.5)
    if coma_decimal:
        limpio = limpio.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        limpio = limpio.str.replace(",", "", regex=False)
    # El paréntesis contable ya se sacó arriba; recuperar el signo negativo.
    negativos = s.str.startswith("(", na=False) & s.str.endswith(")", na=False)
    valores = pd.to_numeric(limpio, errors="coerce")
    return valores.mask(negativos, -valores)


def tipar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Convierte columnas de texto que en realidad son número o fecha.

    Solo convierte si la conversión funciona en la gran mayoría de las filas:
    convertir a medias deja una columna con más nulos que datos, que es peor
    que no haberla tocado.
    """
    salida = df.copy()
    cambios = []
    for col in salida.columns:
        s = salida[col]
        if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
            continue
        no_nulos = s.notna().sum()
        if no_nulos == 0:
            continue
        if _PAT_FECHA.search(str(col)):
            conv = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=True)
            if conv.notna().sum() >= no_nulos * 0.9:
                salida[col] = conv
                cambios.append({"columna": str(col), "de": "texto", "a": "fecha"})
                continue
        conv = _a_numero(s)
        if conv.notna().sum() >= no_nulos * 0.9:
            salida[col] = conv
            cambios.append({"columna": str(col), "de": "texto", "a": "número"})
    return salida, cambios


# --- Perfilado -------------------------------------------------------------
def perfilar(df: pd.DataFrame, catalogo: dict | None = None) -> dict:
    """Ficha de cada columna: tipo, rol, nulos, únicos y sensibilidad.

    La sensibilidad sale de `kobra.gobernanza`, no de una lista propia: si
    mañana se agrega un patrón de dato personal allá, este perfilado lo toma
    solo. Duplicar esa lista sería tener dos definiciones de "dato personal"
    en el mismo producto.
    """
    filas = len(df)
    detalle = []
    for col in df.columns:
        s = df[col]
        nulos = int(s.isna().sum())
        unicos = int(s.nunique(dropna=True))
        ficha = {
            "columna": str(col),
            "dtype": str(s.dtype),
            "rol": rol_columna(str(col), s),
            "nulos": nulos,
            "nulos_pct": round(nulos / filas * 100, 2) if filas else 0.0,
            "unicos": unicos,
            "unicos_pct": round(unicos / filas * 100, 2) if filas else 0.0,
            "sensibilidad": kgob.clasificar(str(col), catalogo),
        }
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            ficha.update({
                "minimo": float(s.min()), "maximo": float(s.max()),
                "media": float(s.mean()), "mediana": float(s.median()),
                "negativos": int((s < 0).sum()), "ceros": int((s == 0).sum()),
            })
        elif pd.api.types.is_datetime64_any_dtype(s) and s.notna().any():
            ficha.update({"desde": str(s.min()), "hasta": str(s.max())})
        else:
            largos = s.dropna().astype(str).str.len()
            ficha["largo_max"] = int(largos.max()) if len(largos) else 0
            top = s.value_counts(dropna=True).head(5)
            ficha["frecuentes"] = [{"valor": str(k), "veces": int(v)}
                                   for k, v in top.items()]
        detalle.append(ficha)
    return {"filas": filas, "columnas": len(df.columns), "detalle": detalle}


# --- Claves ----------------------------------------------------------------
def claves(df: pd.DataFrame, perfil: dict, nombre: str = "tabla") -> dict:
    """Candidatas a clave primaria y foránea.

    La PK compuesta se busca solo si no hay simple, y sobre las columnas cuyo
    ROL puede formar clave: probar todos los pares de un dataset ancho es
    combinatorio y no aporta.
    """
    filas = max(len(df), 1)
    pks, fks = [], []
    for c in perfil["detalle"]:
        col = c["columna"]
        # Un importe no es una clave por más que sus valores no se repitan.
        # En una muestra de 100 filas, que ningún saldo coincida es lo
        # esperable, no evidencia de nada: proponerlo como PK llena la
        # pantalla de candidatas falsas y entierra la verdadera.
        if c["rol"] == METRICA_MONETARIA:
            continue
        if c["nulos"] == 0 and c["unicos"] == filas and filas > 1:
            pks.append({"columna": col, "tipo": "PK simple", "confianza": "alta"})
        elif c["unicos"] >= filas * 0.98 and c["nulos_pct"] < 1 and filas > 50:
            pks.append({"columna": col, "tipo": "PK candidata", "confianza": "media"})
        if c["rol"] in (CLAVE_FORANEA, IDENTIFICADOR) and c["unicos"] < filas * 0.9:
            fks.append(col)

    if not pks and filas > 1:
        cands = [c["columna"] for c in perfil["detalle"]
                 if c["rol"] in (CLAVE_FORANEA, IDENTIFICADOR, DIMENSION, FECHA)][:6]
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                par = [cands[i], cands[j]]
                try:
                    if not df.duplicated(subset=par).any():
                        pks.append({"columna": " + ".join(par),
                                    "tipo": "PK compuesta", "confianza": "media"})
                        break
                except (KeyError, TypeError):
                    continue
            if pks:
                break
    return {"tabla": nombre, "pk": pks, "fk_candidatas": fks}


# --- Joins -----------------------------------------------------------------
# Cuánto se tienen que pisar los valores de dos columnas para considerarlas la
# misma cosa. Por debajo de esto, coincidir es casualidad.
_SOLAPE_MINIMO = 20.0
# Cuando las columnas NO se llaman igual, la vara sube: el nombre ya no aporta
# evidencia, así que la tiene que dar entera el dato.
_SOLAPE_MINIMO_DISTINTO_NOMBRE = 60.0
_MUESTRA_VALORES = 20_000


def _normalizar(nombre: str) -> str:
    """`ID_Cliente`, `id_cliente` y `cliente_id` colapsan al mismo token."""
    n = re.sub(r"[^a-z0-9]+", "", str(nombre).lower())
    for pre in ("id", "cod", "codigo", "nro", "numero"):
        if n.startswith(pre):
            n = n[len(pre):]
        if n.endswith(pre):
            n = n[: -len(pre)]
    return n


def _valores(serie: pd.Series) -> set:
    return set(serie.dropna().astype(str).unique()[:_MUESTRA_VALORES])


def joins_sugeridos(tablas: dict[str, pd.DataFrame],
                    perfiles: dict[str, dict] | None = None,
                    tope: int = 25) -> list[dict]:
    """Cómo se unen estas tablas, con el riesgo de cada unión.

    Mejora sobre el enfoque habitual: no exige que las columnas se llamen
    igual. En un ERP real la misma entidad aparece como `IdCliente`,
    `cliente_id` y `COD_CLI`, y un detector que compara nombres literales no
    encuentra ninguno de esos joins — justo los que hacen falta.

    Para candidatas de distinto nombre la exigencia de solapamiento sube: sin
    la pista del nombre, la evidencia tiene que estar toda en los datos.
    """
    perfiles = perfiles or {}
    nombres = list(tablas)
    sugerencias = []

    for i in range(len(nombres)):
        for j in range(i + 1, len(nombres)):
            ta, tb = nombres[i], nombres[j]
            da, db = tablas[ta], tablas[tb]
            roles_a = {c["columna"]: c["rol"] for c in perfiles.get(ta, {}).get("detalle", [])}
            roles_b = {c["columna"]: c["rol"] for c in perfiles.get(tb, {}).get("detalle", [])}

            pares = []
            for ca in da.columns:
                for cb in db.columns:
                    mismo_nombre = str(ca) == str(cb)
                    if mismo_nombre:
                        pares.append((ca, cb, True))
                        continue
                    # Distinto nombre: solo vale la pena mirar si AMBAS pueden
                    # ser clave. Comparar una fecha contra un monto porque los
                    # valores se pisan es ruido, no un join.
                    ra = roles_a.get(str(ca)) or rol_columna(str(ca), da[ca])
                    rb = roles_b.get(str(cb)) or rol_columna(str(cb), db[cb])
                    if ra not in (IDENTIFICADOR, CLAVE_FORANEA):
                        continue
                    if rb not in (IDENTIFICADOR, CLAVE_FORANEA):
                        continue
                    if _normalizar(ca) and _normalizar(ca) == _normalizar(cb):
                        pares.append((ca, cb, False))

            for ca, cb, mismo_nombre in pares:
                try:
                    va, vb = _valores(da[ca]), _valores(db[cb])
                except (TypeError, ValueError):
                    continue
                if not va or not vb:
                    continue
                solape = len(va & vb) / min(len(va), len(vb)) * 100
                minimo = _SOLAPE_MINIMO if mismo_nombre else _SOLAPE_MINIMO_DISTINTO_NOMBRE
                if solape < minimo:
                    continue
                ua, ub = bool(da[ca].is_unique), bool(db[cb].is_unique)
                card = "1:1" if (ua and ub) else ("1:N" if ua else ("N:1" if ub else "N:N"))
                sugerencias.append({
                    "izquierda": ta, "derecha": tb,
                    "columna_izquierda": str(ca), "columna_derecha": str(cb),
                    "mismo_nombre": mismo_nombre,
                    "solape_pct": round(solape, 1),
                    "cardinalidad": card,
                    "riesgo": _riesgo(card, solape),
                    "sql": (f"SELECT a.*, b.*\nFROM {ta} a\n"
                            f"LEFT JOIN {tb} b ON a.{ca} = b.{cb};"),
                })
    return sorted(sugerencias, key=lambda s: -s["solape_pct"])[:tope]


def _riesgo(cardinalidad: str, solape: float) -> str:
    """El aviso que evita el error caro.

    Un N:N multiplica filas y por lo tanto multiplica los montos que se sumen
    después: es la forma más común de inflar un informe sin que nada falle.
    """
    if cardinalidad == "N:N":
        return "ALTO — N:N multiplica filas y por lo tanto infla cualquier suma"
    if solape < 80:
        return "MEDIO — parte de las claves no encuentra pareja: validar granularidad"
    return "BAJO"


# --- Features --------------------------------------------------------------
# Marca de fuga: una feature calculada contra el máximo del dataset usa
# información que en producción todavía no existe.
FUGA_TEMPORAL = "recalcular con la fecha de corte real en producción"


def features(df: pd.DataFrame, perfil: dict, objetivo: str | None = None,
             tope: int = 200) -> tuple[pd.DataFrame, list[dict]]:
    """Features derivadas del perfilado, cada una con su fórmula explicada.

    El diccionario que devuelve no es documentación de adorno: una feature que
    nadie puede explicar no se puede defender ante un comité de riesgo, y en
    cobranzas eso significa que no se puede usar.
    """
    salida = pd.DataFrame(index=df.index)
    dicc: list[dict] = []

    def agregar(nombre, serie, origen, formula, aviso=""):
        if len(dicc) >= tope or nombre in salida.columns:
            return
        try:
            salida[nombre] = serie
        except (ValueError, TypeError):
            return
        dicc.append({"feature": nombre, "origen": origen, "formula": formula,
                     "aviso": aviso})

    det = perfil["detalle"]
    fechas = [c["columna"] for c in det if c["rol"] == FECHA]
    nums = [c["columna"] for c in det
            if c["rol"] in (METRICA, METRICA_MONETARIA) and c["columna"] != objetivo]

    for col in fechas[:5]:
        s = pd.to_datetime(df[col], errors="coerce")
        b = re.sub(r"[^a-z0-9]+", "_", str(col).lower())[:20]
        agregar(f"{b}_anio", s.dt.year, col, "año")
        agregar(f"{b}_mes", s.dt.month, col, "mes 1-12")
        agregar(f"{b}_trimestre", s.dt.quarter, col, "trimestre")
        agregar(f"{b}_dia_semana", s.dt.dayofweek, col, "día de semana (0=lunes)")
        agregar(f"{b}_es_finde", (s.dt.dayofweek >= 5).astype("Int8"), col,
                "cae sábado o domingo")
        # Codificación cíclica: para un modelo, diciembre (12) y enero (1) son
        # meses consecutivos, no los dos extremos de una recta.
        agregar(f"{b}_mes_sin", np.sin(2 * np.pi * s.dt.month / 12), col,
                "codificación cíclica (seno)")
        agregar(f"{b}_mes_cos", np.cos(2 * np.pi * s.dt.month / 12), col,
                "codificación cíclica (coseno)")
        ref = s.max()
        if pd.notna(ref):
            agregar(f"{b}_dias_desde_max", (ref - s).dt.days, col,
                    "días hasta la fecha máxima del dataset", FUGA_TEMPORAL)

    for col in nums[:25]:
        s = pd.to_numeric(df[col], errors="coerce")
        b = re.sub(r"[^a-z0-9]+", "_", str(col).lower())[:20]
        if s.notna().sum() < 5:
            continue
        # log1p solo si además de positiva está sesgada: aplicarlo a una
        # variable simétrica no arregla nada y hace el modelo menos legible.
        if (s.dropna() >= 0).all() and abs(float(s.skew() or 0)) > 1.5:
            agregar(f"{b}_log1p", np.log1p(s), col, "log(1+x) para corregir asimetría")
        if s.isna().any():
            agregar(f"{b}_es_nulo", s.isna().astype("Int8"), col,
                    "marca de faltante — que un dato falte suele ser informativo")

    salida = salida.loc[:, ~salida.columns.duplicated()]
    return salida, dicc


# --- Salidas ---------------------------------------------------------------
_TIPO_SQL = {"int64": "BIGINT", "Int64": "BIGINT", "int32": "INT", "Int8": "TINYINT",
             "float64": "DECIMAL(18,4)", "float32": "DECIMAL(18,4)", "bool": "BIT"}


def _ident(nombre: str, largo: int = 60) -> str:
    """Identificador SQL seguro.

    Se construye por lista blanca de caracteres y no escapando lo peligroso:
    esto termina dentro de un CREATE TABLE, y filtrar lo malo siempre deja
    algo afuera.
    """
    limpio = re.sub(r"[^A-Za-z0-9_]", "_", str(nombre)).strip("_")
    if not limpio or limpio[0].isdigit():
        limpio = f"c_{limpio}"
    return limpio[:largo]


def generar_ddl(nombre: str, perfil: dict, ks: dict | None = None) -> str:
    """CREATE TABLE + los tres tests que valen la pena tener desde el día uno."""
    ks = ks or {"pk": []}
    campos = []
    for c in perfil["detalle"]:
        dt = c["dtype"]
        if "datetime" in dt:
            tipo = "DATETIME2"
        elif dt in _TIPO_SQL:
            tipo = _TIPO_SQL[dt]
        elif "int" in dt.lower():
            tipo = "BIGINT"
        elif "float" in dt.lower():
            tipo = "DECIMAL(18,4)"
        else:
            largo = int(min(max(c.get("largo_max", 50) or 50, 10) * 2, 4000))
            tipo = f"NVARCHAR({largo})"
        nulo = "NOT NULL" if c["nulos"] == 0 else "NULL"
        campos.append(f"    {_ident(c['columna']):<40} {tipo:<16} {nulo}")

    tabla = _ident(nombre, 40)
    lineas = [f"-- Tabla derivada del perfilado de '{nombre}'",
              f"CREATE TABLE {tabla} (", ",\n".join(campos)]
    pk_altas = [k for k in ks["pk"] if k.get("confianza") == "alta"]
    if pk_altas:
        lineas.append(f"    ,CONSTRAINT PK_{tabla} PRIMARY KEY "
                      f"({_ident(pk_altas[0]['columna'])})")
    lineas += [");", "", "-- Tests de calidad"]
    if pk_altas:
        k = _ident(pk_altas[0]["columna"])
        lineas.append(f"SELECT {k}, COUNT(*) AS repetidos FROM {tabla} "
                      f"GROUP BY {k} HAVING COUNT(*) > 1;")
    for c in [c for c in perfil["detalle"] if c["nulos"] == 0][:6]:
        col = _ident(c["columna"])
        lineas.append(f"SELECT COUNT(*) AS nulos_{col} FROM {tabla} WHERE {col} IS NULL;")
    fechas = [c["columna"] for c in perfil["detalle"] if c["rol"] == FECHA]
    if fechas:
        lineas.append(f"SELECT MAX({_ident(fechas[0])}) AS ultima_carga FROM {tabla};")
    return "\n".join(lineas)


def generar_dbt(nombre: str, perfil: dict, ks: dict | None = None) -> str:
    """Modelo dbt con los tests que se desprenden del perfilado."""
    ks = ks or {"pk": []}
    pk = ks["pk"][0]["columna"] if ks["pk"] else None
    y = ["version: 2", "", "models:", f"  - name: stg_{_ident(nombre, 40)}",
         f"    description: 'Staging de {nombre} — derivado del perfilado'",
         "    columns:"]
    for c in perfil["detalle"][:25]:
        y.append(f"      - name: {_ident(c['columna'])}")
        tests = []
        if pk and c["columna"] == pk:
            tests += ["unique", "not_null"]
        elif c["nulos"] == 0:
            tests.append("not_null")
        if tests:
            y.append("        tests:")
            y += [f"          - {t}" for t in tests]
    return "\n".join(y)


def analizar(tablas: dict[str, pd.DataFrame],
             objetivo: str | None = None,
             catalogo: dict | None = None) -> dict:
    """El recorrido completo sobre un conjunto de tablas."""
    perfiles, llaves, ddl, dbt, cambios = {}, {}, {}, {}, {}
    tipadas = {}
    for nombre, df in tablas.items():
        df2, camb = tipar(df)
        tipadas[nombre] = df2
        cambios[nombre] = camb
        perfiles[nombre] = perfilar(df2, catalogo)
        llaves[nombre] = claves(df2, perfiles[nombre], nombre)
        ddl[nombre] = generar_ddl(nombre, perfiles[nombre], llaves[nombre])
        dbt[nombre] = generar_dbt(nombre, perfiles[nombre], llaves[nombre])
    return {
        "tablas": list(tablas),
        "perfiles": perfiles, "claves": llaves,
        "tipado": cambios,
        "joins": joins_sugeridos(tipadas, perfiles),
        "ddl": ddl, "dbt": dbt,
        "objetivo": objetivo,
    }
