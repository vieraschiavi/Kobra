"""
MV Kobra AI · Cartera manual (modo "mi cartera de prueba")
=======================================================
Convierte una lista simple de contactos —nombre, teléfono, monto de deuda— en
una cartera completa que el pipeline puede scorear y negociar, para que puedas
**probar MV Kobra AI con tus propios casos** sin cargar todo el detalle de un ERP.

Los campos que no aportás (días de mora, score de buró, etc.) se completan con
**supuestos por defecto** claramente marcados: en una implementación real esos
datos vienen del ERP/CRM del cliente. Podés sobreescribir cualquiera por
contacto (columna en el CSV o clave en el dict).

> ⚠️ Privacidad: si cargás nombres y teléfonos **reales**, ese archivo es tuyo
> y privado (`data/mi_cartera_prueba.csv` está en `.gitignore`). El producto
> que se vende sigue siendo 100 % sintético. No subas datos personales al repo.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd

from kobra.probpago import CAT_FEATURES, NUM_FEATURES

# Supuestos por defecto para las features que no vienen cargadas.
# En producción se reemplazan por los valores reales del ERP.
DEFAULTS = {
    "segmento": "Retail",
    "producto": "Préstamo personal",
    "departamento": "Montevideo",
    "canal_preferido": "Llamada",
    "dias_mora": 60,
    "cuotas_atrasadas": 2,
    "antiguedad_cliente_meses": 24,
    "score_buro": 600,
    "ingreso_estimado": 45_000,
    "pagos_ultimos_12m": 6,
    "promesas_cumplidas": 1,
    "promesas_incumplidas": 1,
    "contactabilidad": 0.7,
    "gestiones_previas": 2,
}

_TRAMO_BINS = [-1, 30, 60, 90, 180, 10_000]
_TRAMO_LABELS = ["1-30", "31-60", "61-90", "91-180", "180+"]


def cargar_manual(contactos: list[dict], prefijo: str = "MP") -> pd.DataFrame:
    """
    `contactos`: lista de dicts con al menos `monto_deuda`; opcional `nombre`,
    `telefono`, `id_deudor` y cualquier feature de `DEFAULTS` para sobreescribir.
    Devuelve un DataFrame con el esquema del modelo + `nombre` y `telefono`.
    """
    rows = []
    for k, c in enumerate(contactos, 1):
        row = dict(DEFAULTS)
        for key, val in c.items():
            if val is not None:
                row[key] = val
        row["id_deudor"] = str(c.get("id_deudor") or f"{prefijo}-{k:03d}")
        row["monto_deuda"] = float(c["monto_deuda"])
        row["nombre"] = str(c.get("nombre", "")).strip()
        row["telefono"] = str(c.get("telefono", "")).strip()
        rows.append(row)

    df = pd.DataFrame(rows)
    df["tramo_mora"] = pd.cut(df["dias_mora"], bins=_TRAMO_BINS, labels=_TRAMO_LABELS)
    return df


def puntuar(model, df: pd.DataFrame) -> pd.DataFrame:
    """
    Scorea una cartera chica sin depender de deciles (qcut necesita muchas
    filas): calcula ProbPago con el modelo y la propensión por umbrales.
    """
    out = df.copy()
    pipe = getattr(model, "pipeline", model)
    out["probpago"] = pipe.predict_proba(out[NUM_FEATURES + CAT_FEATURES])[:, 1]
    out["segmento_propension"] = pd.cut(
        out["probpago"], bins=[-0.01, 0.35, 0.65, 1.01],
        labels=["Baja", "Media", "Alta"])
    return out


def brief_desde_fila(fila) -> dict:
    """Arma el brief que consume el Gestor IA a partir de una fila scoreada."""
    return {
        "id_deudor": fila["id_deudor"],
        "nombre": fila.get("nombre", ""),
        "telefono": fila.get("telefono", ""),
        "monto_deuda": float(fila["monto_deuda"]),
        "probpago": float(fila["probpago"]),
        "estrategia": fila["estrategia"],
        "descuento_recomendado": float(fila["descuento_recomendado"]),
        "plan_cuotas": int(fila["plan_cuotas"]),
        "segmento_propension": str(fila.get("segmento_propension", "Media")),
        "canal_recomendado": fila.get("canal_recomendado", "Llamada"),
    }


_NUMERICAS = ("monto_deuda", "dias_mora", "cuotas_atrasadas",
              "antiguedad_cliente_meses", "score_buro", "ingreso_estimado",
              "pagos_ultimos_12m", "promesas_cumplidas", "promesas_incumplidas",
              "contactabilidad", "gestiones_previas")

# Sinonimos por campo canonico (ya NORMALIZADOS: minusculas, sin acentos,
# separadores colapsados a "_"). El archivo del cliente casi nunca usa nuestros
# nombres exactos: puede venir de un ERP, de un export de ProbPago, en otro
# idioma o con mayusculas/espacios distintos. Mapeamos cualquiera de estos al
# campo interno. Orden: el 1er sinonimo EXACTO que aparezca gana; si ninguno
# matchea exacto, se prueba por "contiene" y luego por parecido (fuzzy).
_SINONIMOS = {
    "monto_deuda": [
        "monto_deuda", "montodeuda", "monto_de_deuda", "deuda", "divida", "monto",
        "importe", "importe_deuda", "saldo", "saldo_deuda", "saldo_capital",
        "saldo_actual", "saldo_vencido", "saldo_total", "deuda_total", "deuda_capital",
        "monto_total", "monto_adeudado", "monto_vencido", "capital", "capital_adeudado",
        "total_deuda", "total_adeudado", "valor_deuda", "valor", "montante", "adeudado",
        "monto_cuota_atrasada", "importe_total",
        "debt", "total_debt", "debt_amount", "amount", "amount_due", "balance",
        "outstanding", "outstanding_balance", "balance_due"],
    "nombre": [
        "nombre", "nombre_cliente", "nombre_completo", "nombre_y_apellido",
        "nombre_apellido", "apellido_nombre", "cliente", "deudor", "titular",
        "razon_social", "razonsocial", "nome", "nome_cliente", "name", "full_name",
        "socio_nombre", "nombre_socio"],
    "telefono": [
        "telefono", "telefonos", "tel", "telefono_movil", "telefono_celular",
        "celular", "cel", "movil", "phone", "telefone", "whatsapp", "wpp", "contacto",
        "numero_telefono", "nro_telefono", "num_telefono", "telefono_contacto"],
    "id_deudor": [
        "id_deudor", "id", "id_cliente", "idcliente", "id_socio", "idsocio",
        "codigo_cliente", "cod_cliente", "nro_cliente", "numero_cliente", "cliente_id",
        "documento", "nro_documento", "cedula", "ci", "dni", "rut", "cuit", "cuil",
        "cpf", "cnpj", "identificacion", "socio", "legajo", "expediente"],
    "dias_mora": [
        "dias_mora", "diasmora", "dias_de_mora", "dias_en_mora", "dias_atraso",
        "diasatraso", "dias_de_atraso", "dias_atrasado", "dias_vencido", "dias_vencidos",
        "atraso", "atraso_dias", "mora", "mora_dias", "antiguedad_mora", "atraso_maximo",
        "dias_atraso_max", "max_dias_atraso",
        "days_overdue", "days_past_due", "overdue_days", "dpd", "days_late", "days_in_arrears"],
    "cuotas_atrasadas": [
        "cuotas_atrasadas", "cuotas_atrasada", "cuotas_vencidas", "cuotas_impagas",
        "cuotas_en_mora", "cant_cuotas_atrasadas", "cuotas_adeudadas", "cuotas_pendientes"],
    "score_buro": [
        "score_buro", "score", "score_crediticio", "puntaje_buro", "puntaje",
        "score_bureau", "bureau_score", "score_externo", "calificacion_crediticia"],
    "ingreso_estimado": [
        "ingreso_estimado", "ingreso", "ingresos", "salario", "sueldo", "renta",
        "ingreso_mensual", "ingreso_declarado", "ingreso_neto"],
    "segmento": ["segmento", "segment", "categoria", "categoria_cliente", "tipo_cliente"],
    "producto": ["producto", "tipo_producto", "linea", "linea_producto", "product"],
    "departamento": [
        "departamento", "depto", "provincia", "estado", "region", "ciudad",
        "localidad", "zona"],
}


# Puntaje de "que tan de DEUDA es" el nombre de una columna. Un archivo real
# suele traer VARIAS columnas de plata (Ultimo Pago, Cobro, Importe, Saldo,
# Capital, Deuda Vencida...); no alcanza con "la primera que matchea": hay que
# ELEGIR la de deuda. Cuanto mas peso, mas seguro que es la deuda a cobrar.
#  - deuda/adeudo/vencido/saldo/divida  -> senal fuerte de deuda
#  - capital, a_vencer                  -> deuda-ish (parte del adeudo / por vencer)
#  - monto/importe/valor/balance        -> monto generico (2da opcion)
#  - pago/cobro/abonado/recaudado       -> lo YA cobrado, NO la deuda: peso minimo,
#                                          solo se usa si no hay nada mejor.
_PESO_DEUDA = [
    ("deuda", 10), ("adeudo", 10), ("adeudado", 10), ("adeud", 9), ("divida", 10),
    ("saldo_deuda", 10), ("saldo_vencido", 10), ("monto_vencido", 10),
    ("deuda_vencida", 10), ("deuda_total", 10), ("deuda_parcial", 10),
    ("debt", 10), ("outstanding", 9),
    ("capital_adeudado", 9), ("saldo_capital", 9),
    ("vencido", 7), ("vencida", 7), ("a_vencer", 7), ("por_vencer", 7),
    ("saldo", 6), ("capital", 6), ("balance", 5),
    ("monto", 4), ("importe", 4), ("montante", 4), ("amount", 4), ("valor", 3),
    ("pago", 1), ("pagado", 1), ("cobro", 1), ("cobrado", 1),
    ("abonado", 1), ("recaudado", 1),
]
_TOK_DEUDA = ("deuda", "adeud", "vencid", "divida", "saldo", "capital", "debt", "outstanding")
_TOK_MONTO = ("monto", "importe", "valor", "amount", "balance", "montante")


def _score_deuda(nombre_norm: str) -> int:
    """Puntaje de deuda de una columna ya normalizada. 0 = no parece plata."""
    score = max((peso for tok, peso in _PESO_DEUDA if tok in nombre_norm), default=0)
    # Combina un generico con una palabra de deuda ("monto_deuda", "saldo_vencido"):
    # es la mas segura de todas, la empujamos arriba de un "deuda" o "monto" sueltos.
    if (any(t in nombre_norm for t in _TOK_DEUDA)
            and any(t in nombre_norm for t in _TOK_MONTO)):
        score += 2
    return score


def _norm_col(c) -> str:
    """Normaliza un nombre de columna: sin acentos, minusculas, cualquier cosa
    que no sea letra/numero pasa a "_" (colapsado). "Monto Deuda" -> "monto_deuda",
    "MontoDeuda" -> "montodeuda", "Días de Atraso" -> "dias_de_atraso"."""
    s = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.strip().lower())
    return s.strip("_")


def _a_numero(v):
    """Convierte a numero tolerando formato de moneda es/en: '$ 1.234.567,89',
    '1,234,567.89', 'UYU 5.000', '45%'. Devuelve float o NaN."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return float("nan")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return float("nan")
    es_pct = "%" in s
    s = re.sub(r"[^0-9,.\-]", "", s)          # deja solo digitos, . , y signo
    if not s or s in ("-", ".", ","):
        return float("nan")
    if "," in s and "." in s:
        # El separador decimal es el ULTIMO que aparece; el otro es de miles.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # 1.234.567,89 -> 1234567.89
        else:
            s = s.replace(",", "")                       # 1,234,567.89 -> 1234567.89
    elif "," in s:
        # Solo coma: decimal si hay 1-2 digitos despues; si no, miles.
        ent, _, dec = s.rpartition(",")
        s = f"{ent.replace(',', '')}.{dec}" if 0 < len(dec) <= 2 else s.replace(",", "")
    else:
        # Solo puntos: si hay varios, o grupos de 3, son miles (1.234.567).
        if s.count(".") > 1 or re.search(r"\.\d{3}(\D|$)", s + " "):
            s = s.replace(".", "")
    try:
        n = float(s)
        return n / 100 if es_pct else n
    except ValueError:
        return float("nan")


def mapear_columnas(columnas) -> dict:
    """Devuelve {columna_original: campo_canonico} adivinando a que campo interno
    corresponde cada columna del archivo del cliente. Match en 3 pasadas por
    prioridad: exacto por sinonimo, "contiene" un sinonimo, y parecido (fuzzy).
    Cada campo se asigna a lo sumo una vez (gana la mejor coincidencia)."""
    norm = {c: _norm_col(c) for c in columnas}
    mapeo, usados = {}, set()

    def _asignar(campo, col):
        mapeo[col] = campo
        usados.add(campo)

    # 0) DEUDA por puntaje (mirando TODO el dataset): entre varias columnas de
    #    plata elige la MAS de-deuda. Asi "Deuda Total" le gana a "Ultimo Pago",
    #    e "Importe" le gana a "Cobro Mensual" — no es la primera que aparece.
    puntajes = {c: _score_deuda(n) for c, n in norm.items()}
    mejor_col = max(puntajes, key=puntajes.get) if puntajes else None
    if mejor_col is not None and puntajes[mejor_col] >= 1:
        _asignar("monto_deuda", mejor_col)

    # 1) match exacto contra la lista de sinonimos, respetando su prioridad.
    for campo, syns in _SINONIMOS.items():
        if campo in usados:
            continue
        for syn in syns:
            hit = next((c for c, n in norm.items()
                        if n == syn and c not in mapeo), None)
            if hit is not None:
                _asignar(campo, hit)
                break
    # 2) "contiene": la columna incluye un sinonimo como token (o al reves).
    for campo, syns in _SINONIMOS.items():
        if campo in usados:
            continue
        for c, n in norm.items():
            if c in mapeo:
                continue
            if any(f"_{syn}_" in f"_{n}_" or n.startswith(syn) or n.endswith(syn)
                   for syn in syns if len(syn) >= 4):
                _asignar(campo, c)
                break
    # 3) fuzzy: parecido de cadena (>=0.86) contra cualquier sinonimo largo.
    for campo, syns in _SINONIMOS.items():
        if campo in usados:
            continue
        mejor, mejor_score = None, 0.86
        for c, n in norm.items():
            if c in mapeo or len(n) < 4:
                continue
            sc = max(difflib.SequenceMatcher(None, n, s).ratio()
                     for s in syns if len(s) >= 4)
            if sc > mejor_score:
                mejor, mejor_score = c, sc
        if mejor is not None:
            _asignar(campo, mejor)
    return mapeo


def desde_dataframe(df: pd.DataFrame) -> list[dict]:
    """Normaliza un DataFrame de contactos (tabla editable o archivo subido en
    el dashboard) a la lista de contactos, ADAPTANDOSE a nombres de columna
    parecidos (ver mapear_columnas): 'MontoDeuda', 'Saldo Vencido', 'Divida',
    'Deuda Total', etc. se reconocen como el monto de deuda. Telefono como texto
    (conserva el 0 inicial); columnas numericas y montos con formato de moneda
    coercionados; nombres/vacios tolerados."""
    df = df.copy()
    mapeo = mapear_columnas(df.columns)
    if mapeo:
        df = df.rename(columns=mapeo)
    # Columnas no mapeadas: normalizadas por si ya son un campo interno exacto
    # (ej. 'contactabilidad', 'gestiones_previas') que no esta en los sinonimos.
    df.columns = [c if c in _SINONIMOS or c in mapeo.values() else _norm_col(c)
                  for c in df.columns]
    # Duplicados tras el mapeo (dos columnas al mismo campo): queda la 1a.
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]

    if "telefono" in df.columns:
        df["telefono"] = df["telefono"].apply(
            lambda v: "" if pd.isna(v) else str(v).strip())
    for col in _NUMERICAS:
        if col in df.columns:
            df[col] = df[col].map(_a_numero)
    contactos = []
    for row in df.to_dict("records"):
        # descartar filas sin deuda válida y columnas numéricas vacías
        if pd.isna(row.get("monto_deuda")):
            continue
        contactos.append({k: v for k, v in row.items()
                          if not (k in _NUMERICAS and pd.isna(v))})
    return contactos


def leer_csv(ruta: str) -> list[dict]:
    """Lee un CSV de contactos (columnas: nombre, telefono, monto_deuda/deuda, …)."""
    return desde_dataframe(pd.read_csv(ruta, dtype=str).fillna(""))


_MODELO_PRIOR = None


def modelo_prior():
    """Modelo ProbPago entrenado sobre la cartera de referencia (la demo
    sintética, o la que ya haya en `data/kobra_cartera.csv`) — se usa para
    puntuar carteras chicas nuevas sin reentrenar en cada subida. Una real
    recién subida no trae la columna de resultado histórico (`pago`), así
    que no se puede entrenar sobre ella directamente; se aplica este modelo
    ya entrenado, y `puntuar()` no depende de deciles (sirve para pocas filas)."""
    global _MODELO_PRIOR
    if _MODELO_PRIOR is None:
        from kobra.pipeline import _load_or_generate
        from kobra.probpago import ProbPagoModel
        base = _load_or_generate()
        _MODELO_PRIOR = ProbPagoModel().fit_seleccionado(base)
    return _MODELO_PRIOR


def importar_y_scorear(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """Toma un DataFrame crudo subido por el cliente (CSV/Excel con nombre,
    telefono, deuda[, dias_mora, ...]) y devuelve la cartera completa
    scoreada + con estrategia de negociación — lista para reemplazar los
    datos de demo del dashboard. Lanza ValueError si no hay ninguna fila
    con un monto de deuda válido."""
    from kobra import explicabilidad, negociador

    contactos = desde_dataframe(df_bruto)
    if not contactos:
        cols = ", ".join(str(c) for c in df_bruto.columns[:12])
        mapeo = mapear_columnas(df_bruto.columns)
        if "monto_deuda" not in mapeo.values():
            raise ValueError(
                "No reconocí ninguna columna con el monto de deuda. Renombrá la "
                "columna del importe a 'deuda' (o 'monto', 'saldo', 'importe') y "
                f"reintentá. Columnas que leí: {cols}.")
        raise ValueError(
            "Reconocí la columna de deuda pero ninguna fila tiene un monto válido "
            "(¿están todas vacías o en cero?). Revisá el archivo y reintentá. "
            f"Columnas que leí: {cols}.")
    df = cargar_manual(contactos)
    model = modelo_prior()
    scored = puntuar(model, df)
    try:
        scored["decil"] = pd.qcut(scored["probpago"].rank(method="first"), 10,
                                  labels=False, duplicates="drop") + 1
    except Exception:
        # Muy pocas filas para deciles reales (qcut necesita variedad): decil
        # aproximado por percentil, funciona incluso con una sola fila.
        scored["decil"] = (scored["probpago"].rank(pct=True) * 9 + 1).round().astype(int)
    full = negociador.recomendar(scored)
    full["motivo_probpago"] = explicabilidad.explicar_cartera(model, full)
    return full


def desde_base_de_datos(conn_url: str, consulta: str, limite: int | None = None) -> list[dict]:
    """
    Trae la cartera directamente desde la base de datos del cliente (Postgres,
    MySQL, SQL Server, SQLite… lo que soporte SQLAlchemy) y la normaliza al
    mismo esquema que el CSV/tabla: la consulta debe devolver al menos una
    columna de deuda (`monto_deuda`, `deuda` o `monto`) y opcionalmente
    `nombre`, `telefono`, `id_deudor`, `dias_mora`, etc.

    `limite`: por defecto None = sin límite de tamaño (trae toda la cartera que
    devuelva la consulta). Pasá un entero solo si querés recortar a las primeras
    N filas.

    Solo lectura a nivel de aplicación: se rechaza cualquier consulta que no
    empiece en SELECT/WITH o que contenga palabras de escritura — mismo
    criterio que el validador de kobra/consulta_bd.py. La URL de conexión
    nunca se loguea completa.
    """
    sql = (consulta or "").strip().rstrip(";")
    if not sql:
        raise ValueError("Escribí la consulta SQL que devuelve tu cartera.")
    plano = " " + " ".join(sql.lower().split()) + " "
    if not (plano.lstrip().startswith("select") or plano.lstrip().startswith("with")):
        raise ValueError("Solo se permiten consultas de lectura (SELECT/WITH).")
    from kobra.consulta_bd import _PROHIBIDAS
    for p in _PROHIBIDAS:
        if p in plano:
            raise ValueError(f"Consulta rechazada: contiene '{p.strip()}' (solo lectura).")

    from sqlalchemy import create_engine, text
    eng = create_engine(conn_url)
    try:
        with eng.connect() as conn:
            df = pd.read_sql(text(sql), conn)
    finally:
        eng.dispose()
    if limite is not None and len(df) > limite:
        df = df.head(limite)
    return desde_dataframe(df)
