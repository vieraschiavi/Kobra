# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Campañas segmentadas, RFM y cohortes
==================================================
Módulo de la suite. Trabaja sobre las MISMAS tablas que `kobra/logistica.py`
—`productos`, `ventas`, `clientes`— y por eso no le pide al cliente cargar
nada nuevo: si ya usa logística, esto funciona el mismo día.

Contesta cuatro preguntas que no son la misma:

  1. **¿A quién le hablo?**      RFM: recencia, frecuencia y monto por cliente,
                                  resumido en un segmento con nombre.
  2. **¿Se quedan?**             Cohortes: de los que compraron por primera vez
                                  en marzo, cuántos seguían comprando en junio.
  3. **¿Cómo fue la campaña?**   Unidades, precio, rentabilidad y stock.
  4. **¿Comparado con qué?**     Contra el período normal, y contra la edición
                                  anterior de la MISMA campaña.

Por qué la comparación va por separado
---------------------------------------
"La campaña vendió 3.000 unidades" no dice nada solo. Puede ser el doble de lo
normal o la mitad de lo que hizo la misma campaña el año pasado — y las dos
comparaciones responden preguntas distintas:

  * **contra lo normal** dice si la campaña movió la aguja;
  * **contra la edición anterior** dice si la campaña está gastada.

Una campaña puede vender más que un día normal y aun así ser un fracaso, si
vendió la mitad que la edición pasada. Por eso están las dos, y ninguna se
presenta como "el" resultado.

Por qué el descuento puede no ser medible
------------------------------------------
Medir "precio de campaña vs precio normal" exige que el archivo del cliente
traiga el precio al que se vendió cada línea (`precio_unit`). Muchos ERP no lo
exportan. `logistica.enriquecer` en ese caso completa el hueco con el precio de
lista del producto — lo cual es correcto para estimar la venta, pero convierte
el descuento en CERO por construcción.

Informar "0% de descuento" ahí sería mentir con un número: no es que no hubo
descuento, es que no se puede saber. `descuento_medible()` lo detecta y el
resumen lo dice en vez de mostrar un cero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from kobra.logistica import DatosIncompletos, _exigir, enriquecer

# Un cliente que no compra hace más de esto se considera dormido.
DIAS_HIBERNANDO = 180
# Días de corte entre dos ediciones de la misma campaña: dos bloques de ventas
# del mismo nombre separados por más que esto son campañas distintas.
DIAS_ENTRE_EDICIONES = 30
# Con menos clientes que esto, los quintiles de RFM son ruido y no se calculan.
MINIMO_CLIENTES_RFM = 20
# Diferencia relativa a partir de la cual se considera que el precio de venta
# informado se despega del de lista (y por lo tanto el descuento es medible).
UMBRAL_DESCUENTO_MEDIBLE = 0.005

COLUMNAS_VENTAS_RFM = ("fecha", "sku", "cantidad", "cliente_id")

IDIOMA_DEFAULT = "es"
IDIOMAS = ("es", "pt", "en")

# Los nombres de segmento se traducen porque los lee una persona; las CLAVES
# (`campeones`, `en_riesgo`…) no, porque las consume la pantalla.
SEGMENTOS = ("campeones", "leales", "potenciales", "nuevos",
             "en_riesgo", "hibernando", "perdidos")

_TEXTOS = {
    "es": {
        "titulo_rfm": "Clientes por segmento (RFM)",
        "titulo_cohortes": "Retención por cohorte",
        "titulo_campanias": "Campañas",
        "seg_campeones": "Campeones",
        "seg_leales": "Leales",
        "seg_potenciales": "Potenciales",
        "seg_nuevos": "Nuevos",
        "seg_en_riesgo": "En riesgo",
        "seg_hibernando": "Hibernando",
        "seg_perdidos": "Perdidos",
        "sin_precio": "Tu archivo de ventas no trae el precio al que se vendió "
                      "cada línea, así que el descuento de campaña no se puede "
                      "medir. Agregá la columna «precio_unit» para verlo.",
        "pocos_clientes": "Hay {n} clientes con compras: muy pocos para partir "
                          "en quintiles. El RFM necesita al menos {minimo}.",
        "sin_normal": "No hay ventas en el período previo comparable, así que "
                      "no se puede comparar contra lo normal.",
        "sin_anterior": "Es la primera edición de esta campaña: no hay una "
                        "anterior contra la cual compararla.",
    },
    "pt": {
        "titulo_rfm": "Clientes por segmento (RFM)",
        "titulo_cohortes": "Retenção por coorte",
        "titulo_campanias": "Campanhas",
        "seg_campeones": "Campeões",
        "seg_leales": "Leais",
        "seg_potenciales": "Potenciais",
        "seg_nuevos": "Novos",
        "seg_en_riesgo": "Em risco",
        "seg_hibernando": "Hibernando",
        "seg_perdidos": "Perdidos",
        "sin_precio": "Seu arquivo de vendas não traz o preço pelo qual cada "
                      "linha foi vendida, então o desconto da campanha não pode "
                      "ser medido. Adicione a coluna «precio_unit» para vê-lo.",
        "pocos_clientes": "Há {n} clientes com compras: poucos demais para "
                          "dividir em quintis. O RFM precisa de pelo menos "
                          "{minimo}.",
        "sin_normal": "Não há vendas no período anterior comparável, então não "
                      "dá para comparar com o normal.",
        "sin_anterior": "É a primeira edição desta campanha: não há uma anterior "
                        "para comparar.",
    },
    "en": {
        "titulo_rfm": "Customers by segment (RFM)",
        "titulo_cohortes": "Cohort retention",
        "titulo_campanias": "Campaigns",
        "seg_campeones": "Champions",
        "seg_leales": "Loyal",
        "seg_potenciales": "Promising",
        "seg_nuevos": "New",
        "seg_en_riesgo": "At risk",
        "seg_hibernando": "Hibernating",
        "seg_perdidos": "Lost",
        "sin_precio": "Your sales file doesn't carry the price each line sold "
                      "at, so the campaign discount can't be measured. Add a "
                      "«precio_unit» column to see it.",
        "pocos_clientes": "There are {n} customers with purchases: too few to "
                          "split into quintiles. RFM needs at least {minimo}.",
        "sin_normal": "There are no sales in a comparable prior period, so this "
                      "can't be compared against normal.",
        "sin_anterior": "This is the first run of this campaign: there's no "
                        "previous one to compare against.",
    },
}


def _idioma(idioma: str | None) -> str:
    corto = str(idioma or "").strip().lower().replace("_", "-").split("-")[0]
    return corto if corto in IDIOMAS else IDIOMA_DEFAULT


def titulos(idioma: str = IDIOMA_DEFAULT) -> dict:
    t = _TEXTOS[_idioma(idioma)]
    return {clave: t[f"titulo_{clave}"] for clave in ("rfm", "cohortes", "campanias")}


def nombres_segmentos(idioma: str = IDIOMA_DEFAULT) -> dict:
    t = _TEXTOS[_idioma(idioma)]
    return {s: t[f"seg_{s}"] for s in SEGMENTOS}


# ---------------------------------------------------------------------------
# RFM
# ---------------------------------------------------------------------------
def _quintil(serie: pd.Series, invertir: bool = False) -> pd.Series:
    """Puntaje 1-5 por posición relativa, no por corte fijo.

    Se usa el rango percentil y no `pd.qcut` a propósito: con empates —y en
    frecuencia hay muchísimos, media cartera compró 1 sola vez— `qcut` revienta
    con "Bin edges must be unique" o deja quintiles vacíos. El rango reparte
    los empates y nunca falla.
    """
    r = serie.rank(pct=True, method="average")
    if invertir:
        r = 1 - r
    return np.ceil(r * 5).clip(1, 5).astype(int)


def _etiqueta(r: int, fm: int) -> str:
    """Segmento a partir de recencia (r) y del promedio de frecuencia+monto.

    La tabla es la clásica de RFM, simplificada a lo que cambia una decisión:
    a quién cuidar, a quién despertar y a quién dejar ir.
    """
    if r >= 4 and fm >= 4:
        return "campeones"
    if r >= 3 and fm >= 3:
        return "leales"
    if r >= 4 and fm <= 2:
        return "nuevos"            # compró recién, todavía poco volumen
    if r == 3:
        return "potenciales"
    if r == 2:
        return "en_riesgo"         # solía comprar y se está enfriando
    return "hibernando" if fm >= 3 else "perdidos"


def rfm(v: pd.DataFrame, hoy=None, idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Recencia, frecuencia y monto por cliente, con su segmento.

    `hoy` existe para que el cálculo sea reproducible: si se tomara la fecha
    del sistema, el mismo archivo daría segmentos distintos cada día y ningún
    test podría fijarlo. Por defecto es la última venta del período, que además
    es lo correcto cuando se analiza un histórico cerrado.
    """
    _exigir(v, COLUMNAS_VENTAS_RFM, "ventas")
    if "venta" not in v.columns:
        raise DatosIncompletos(
            "La tabla de ventas no está enriquecida: falta la columna «venta». "
            "Pasala por logistica.enriquecer() antes.")
    d = v.dropna(subset=["cliente_id"]).copy()
    d["fecha"] = pd.to_datetime(d["fecha"], format="mixed", errors="coerce")
    d = d.dropna(subset=["fecha"])
    if d.empty:
        return pd.DataFrame(columns=["cliente_id", "recencia_dias", "frecuencia",
                                     "monto", "r", "f", "m", "segmento",
                                     "segmento_nombre"])
    corte = pd.to_datetime(hoy) if hoy is not None else d["fecha"].max()

    g = d.groupby("cliente_id").agg(
        ultima_compra=("fecha", "max"),
        frecuencia=("fecha", "nunique"),     # días con compra, no líneas
        monto=("venta", "sum"))
    g["recencia_dias"] = (corte - g["ultima_compra"]).dt.days

    g["r"] = _quintil(g["recencia_dias"], invertir=True)   # menos días = mejor
    g["f"] = _quintil(g["frecuencia"])
    g["m"] = _quintil(g["monto"])
    fm = ((g["f"] + g["m"]) / 2).round().astype(int)
    g["segmento"] = [_etiqueta(r, x) for r, x in zip(g["r"], fm)]

    # La recencia manda sobre el puntaje cuando ya pasó demasiado tiempo: un
    # cliente que compró mucho pero hace un año no es "leal", está dormido.
    dormido = g["recencia_dias"] > DIAS_HIBERNANDO
    g.loc[dormido & g["segmento"].isin(("campeones", "leales", "potenciales")),
          "segmento"] = "hibernando"

    nombres = nombres_segmentos(idioma)
    g["segmento_nombre"] = g["segmento"].map(nombres)
    return (g.reset_index()
             .drop(columns=["ultima_compra"])
             .sort_values("monto", ascending=False)
             .reset_index(drop=True))


def resumen_segmentos(tabla_rfm: pd.DataFrame,
                      idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Una fila por segmento: cuántos clientes y cuánta plata representan.

    Es la tabla con la que se arma una campaña segmentada: dice a cuántos le
    vas a hablar y cuánto vale ese grupo.
    """
    nombres = nombres_segmentos(idioma)
    if tabla_rfm.empty:
        return pd.DataFrame(columns=["segmento", "segmento_nombre", "clientes",
                                     "monto", "monto_pct", "recencia_mediana"])
    g = (tabla_rfm.groupby("segmento", as_index=False)
                  .agg(clientes=("cliente_id", "nunique"),
                       monto=("monto", "sum"),
                       recencia_mediana=("recencia_dias", "median")))
    total = g["monto"].sum()
    g["monto_pct"] = np.where(total > 0, g["monto"] / total * 100, 0.0)
    g["segmento_nombre"] = g["segmento"].map(nombres)
    orden = {s: i for i, s in enumerate(SEGMENTOS)}
    return (g.sort_values("segmento", key=lambda s: s.map(orden))
             .reset_index(drop=True))


# ---------------------------------------------------------------------------
# Cohortes
# ---------------------------------------------------------------------------
def cohortes(v: pd.DataFrame, meses: int = 12) -> pd.DataFrame:
    """Retención por cohorte de primera compra.

    Fila = mes en que el cliente compró por primera vez. Columna = cuántos
    meses después. Valor = qué porcentaje de esa cohorte volvió a comprar.

    La diagonal siempre da 100 (el mes 0 es la propia compra que define la
    cohorte); lo que se mira es cuánto cae después.
    """
    _exigir(v, ("fecha", "cliente_id"), "ventas")
    d = v.dropna(subset=["cliente_id"]).copy()
    d["fecha"] = pd.to_datetime(d["fecha"], format="mixed", errors="coerce")
    d = d.dropna(subset=["fecha"])
    if d.empty:
        return pd.DataFrame()

    d["mes"] = d["fecha"].dt.to_period("M")
    primera = d.groupby("cliente_id")["mes"].min().rename("cohorte")
    d = d.merge(primera, on="cliente_id", how="left")
    d["indice"] = (d["mes"] - d["cohorte"]).apply(lambda x: x.n)
    d = d[(d["indice"] >= 0) & (d["indice"] < meses)]

    activos = (d.groupby(["cohorte", "indice"])["cliente_id"]
                .nunique().unstack(fill_value=0))
    if activos.empty:
        return pd.DataFrame()
    base = activos[0].replace(0, np.nan)
    ret = activos.div(base, axis=0).mul(100).round(1)
    ret.index = ret.index.astype(str)
    ret.columns = [f"mes_{c}" for c in ret.columns]
    ret.insert(0, "clientes", activos[0].values)
    return ret.reset_index().rename(columns={"index": "cohorte"})


# ---------------------------------------------------------------------------
# Campañas: detección de ediciones
# ---------------------------------------------------------------------------
def _con_precio_lista(v: pd.DataFrame,
                      productos: pd.DataFrame | None) -> pd.DataFrame:
    """`v` con una columna `precio_lista` traída de productos.

    Hace falta porque `logistica.enriquecer` se lleva puesta la columna
    `precio` al renombrarla (`v["precio_unit"] = v.pop("precio")`): después de
    enriquecer, el precio de lista ya no está en la tabla de trabajo y hay que
    volver a buscarlo. Sin esto, comparar precio de campaña contra precio
    normal era comparar la columna contra sí misma, y el descuento daba 0
    siempre — el mismo cero engañoso que este módulo existe para no informar.
    """
    if "precio_lista" in v.columns:
        return v
    if productos is None or "precio" not in getattr(productos, "columns", []):
        return v
    lista = productos[["sku", "precio"]].rename(columns={"precio": "precio_lista"})
    return v.merge(lista, on="sku", how="left")


def descuento_medible(v: pd.DataFrame,
                      productos: pd.DataFrame | None = None) -> bool:
    """¿El archivo trae precio de venta propio, o `enriquecer` lo completó?

    Si `precio_unit` es idéntico al precio de lista en todas las filas, no es
    que no hubo descuento: es que el dato no vino. Ver el docstring del módulo.
    """
    d = _con_precio_lista(v, productos)
    if "precio_unit" not in d.columns or "precio_lista" not in d.columns:
        return False
    a = pd.to_numeric(d["precio_unit"], errors="coerce")
    b = pd.to_numeric(d["precio_lista"], errors="coerce")
    ok = a.notna() & b.notna() & (b > 0)
    if not ok.any():
        return False
    return bool((((a[ok] - b[ok]).abs() / b[ok]) > UMBRAL_DESCUENTO_MEDIBLE).any())


def ediciones(v: pd.DataFrame) -> pd.DataFrame:
    """Una fila por edición de campaña: nombre, desde, hasta, número.

    Dos bloques de ventas de la misma campaña separados por más de
    `DIAS_ENTRE_EDICIONES` son ediciones distintas. Es lo que permite comparar
    "el Hot Sale de este año" contra "el del año pasado" sin pedirle al cliente
    que numere nada.
    """
    if "campania" not in v.columns:
        return pd.DataFrame(columns=["campania", "edicion", "desde", "hasta", "dias"])
    d = v.dropna(subset=["campania"]).copy()
    d["fecha"] = pd.to_datetime(d["fecha"], format="mixed", errors="coerce")
    d = d.dropna(subset=["fecha"])
    d = d[d["campania"].astype(str).str.strip() != ""]
    if d.empty:
        return pd.DataFrame(columns=["campania", "edicion", "desde", "hasta", "dias"])

    filas = []
    for nombre, g in d.groupby("campania"):
        dias = pd.Index(sorted(g["fecha"].dt.normalize().unique()))
        corte = dias.to_series().diff().dt.days.fillna(0) > DIAS_ENTRE_EDICIONES
        bloque = corte.cumsum()
        for _, fechas in dias.to_series().groupby(bloque.values):
            filas.append({"campania": nombre,
                          "desde": fechas.min(), "hasta": fechas.max(),
                          "dias": int((fechas.max() - fechas.min()).days) + 1})
    e = pd.DataFrame(filas).sort_values(["campania", "desde"])
    e["edicion"] = e.groupby("campania").cumcount() + 1
    return e[["campania", "edicion", "desde", "hasta", "dias"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Campañas: métricas y comparaciones
# ---------------------------------------------------------------------------
def _metricas(v: pd.DataFrame, productos: pd.DataFrame | None = None) -> dict:
    """Unidades, venta, margen, precio y clientes de un tramo de ventas."""
    if v.empty:
        return {"unidades": 0, "venta": 0.0, "margen": 0.0, "margen_pct": 0.0,
                "precio_promedio": 0.0, "clientes": 0, "skus": 0,
                "descuento_pct": None}
    unidades = float(v["cantidad"].sum())
    venta = float(v["venta"].sum())
    margen = float(v["margen"].sum()) if "margen" in v.columns else 0.0
    m = {
        "unidades": unidades,
        "venta": venta,
        "margen": margen,
        "margen_pct": (margen / venta * 100) if venta else 0.0,
        # Precio promedio PONDERADO por unidad, no promedio de precios: el
        # promedio simple le da el mismo peso a un SKU que vendió 1 que a uno
        # que vendió 900.
        "precio_promedio": (venta / unidades) if unidades else 0.0,
        "clientes": int(v["cliente_id"].nunique()) if "cliente_id" in v.columns else 0,
        "skus": int(v["sku"].nunique()),
        "descuento_pct": None,
    }
    if descuento_medible(v, productos):
        d = _con_precio_lista(v, productos)
        lista = float((d["cantidad"] * d["precio_lista"].fillna(0)).sum())
        # Lo que se habría facturado a precio de lista contra lo que se facturó
        # de verdad. Queda en None —y no en 0— cuando el precio no se puede
        # medir, para no inventar "no hubo descuento".
        m["descuento_pct"] = ((lista - venta) / lista * 100) if lista else None
    return m


def _variacion(actual: float, base: float) -> float | None:
    """Variación porcentual, o None si no hay base contra la cual medir.

    Devolver 0 —o peor, infinito— cuando la base es cero convierte "no tengo
    con qué comparar" en "no cambió nada", que es una afirmación distinta.
    """
    if base in (0, None) or pd.isna(base):
        return None
    return (actual - base) / abs(base) * 100


def _comparar(actual: dict, base: dict) -> dict:
    campos = ("unidades", "venta", "margen", "precio_promedio", "clientes")
    return {c: _variacion(actual[c], base[c]) for c in campos}


def tramo(v: pd.DataFrame, desde, hasta) -> pd.DataFrame:
    # Mismo motivo que en `logistica.enriquecer`: formatos mezclados en
    # la misma columna, que sin esto se convierten en NaT y quedan fuera
    # del tramo sin que nadie lo note.
    f = pd.to_datetime(v["fecha"], format="mixed", errors="coerce")
    return v[(f >= pd.to_datetime(desde)) & (f <= pd.to_datetime(hasta))]


def contra_normal(v: pd.DataFrame, desde, hasta,
                  productos: pd.DataFrame | None = None,
                  idioma: str = IDIOMA_DEFAULT) -> dict:
    """La campaña contra el período normal inmediatamente anterior.

    El período de comparación tiene la MISMA cantidad de días y termina justo
    antes de que empiece la campaña, y se le sacan los días que pertenecen a
    otra campaña: comparar contra un tramo que también estaba en promoción
    haría ver a la campaña peor de lo que fue, sin que nadie se dé cuenta.
    """
    desde, hasta = pd.to_datetime(desde), pd.to_datetime(hasta)
    dias = (hasta - desde).days + 1
    fin_previo = desde - pd.Timedelta(days=1)
    ini_previo = fin_previo - pd.Timedelta(days=dias - 1)

    previo = tramo(v, ini_previo, fin_previo)
    if "campania" in previo.columns:
        limpio = previo["campania"].isna() | (
            previo["campania"].astype(str).str.strip() == "")
        previo = previo[limpio]

    if previo.empty:
        return {"hay_base": False,
                "motivo": _TEXTOS[_idioma(idioma)]["sin_normal"],
                "desde": str(ini_previo.date()), "hasta": str(fin_previo.date())}
    base = _metricas(previo, productos)
    actual = _metricas(tramo(v, desde, hasta), productos)
    return {"hay_base": True, "desde": str(ini_previo.date()),
            "hasta": str(fin_previo.date()), "dias": dias,
            "normal": base, "campania": actual, "variacion": _comparar(actual, base)}


def contra_anterior(v: pd.DataFrame, campania: str, edicion: int | None = None,
                    productos: pd.DataFrame | None = None,
                    idioma: str = IDIOMA_DEFAULT) -> dict:
    """Una edición de la campaña contra la edición anterior de la misma.

    Responde la pregunta que no contesta la comparación contra lo normal: si
    la campaña se está gastando. Vender más que un día común y menos que la
    edición pasada son las dos cosas a la vez, y hay que ver las dos.
    """
    e = ediciones(v)
    e = e[e["campania"] == campania]
    if e.empty:
        raise DatosIncompletos(f"No hay ventas de la campaña «{campania}».")
    if edicion is None:
        edicion = int(e["edicion"].max())
    fila = e[e["edicion"] == edicion]
    if fila.empty:
        raise DatosIncompletos(
            f"La campaña «{campania}» no tiene una edición {edicion}.")
    fila = fila.iloc[0]

    previa = e[e["edicion"] == edicion - 1]
    actual = _metricas(tramo(v, fila["desde"], fila["hasta"]), productos)
    if previa.empty:
        return {"hay_anterior": False,
                "motivo": _TEXTOS[_idioma(idioma)]["sin_anterior"],
                "campania": campania, "edicion": int(edicion), "actual": actual}
    p = previa.iloc[0]
    base = _metricas(tramo(v, p["desde"], p["hasta"]), productos)
    return {"hay_anterior": True, "campania": campania, "edicion": int(edicion),
            "edicion_anterior": int(p["edicion"]),
            "desde_anterior": str(pd.to_datetime(p["desde"]).date()),
            "hasta_anterior": str(pd.to_datetime(p["hasta"]).date()),
            "anterior": base, "actual": actual,
            "variacion": _comparar(actual, base)}


def stock_de_campania(v: pd.DataFrame, productos: pd.DataFrame,
                      desde, hasta) -> pd.DataFrame:
    """Qué pasó con el stock de lo que se promocionó.

    `cobertura_dias` usa el ritmo de venta DE LA CAMPAÑA y no el histórico: es
    lo que contesta "si sigo a este ritmo, ¿me alcanza el stock?", que es la
    pregunta que se hace en el medio de una promoción.
    """
    _exigir(productos, ("sku", "stock"), "productos")
    t = tramo(v, desde, hasta)
    if t.empty:
        return pd.DataFrame(columns=["sku", "unidades", "stock", "cobertura_dias"])
    dias = max((pd.to_datetime(hasta) - pd.to_datetime(desde)).days + 1, 1)
    g = t.groupby("sku", as_index=False).agg(unidades=("cantidad", "sum"))
    cols = [c for c in ("sku", "nombre", "stock") if c in productos.columns]
    g = g.merge(productos[cols], on="sku", how="left")
    ritmo = g["unidades"] / dias
    g["cobertura_dias"] = np.where(ritmo > 0, g["stock"] / ritmo, np.inf)
    return g.sort_values("unidades", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
def todas(productos: pd.DataFrame, ventas: pd.DataFrame,
          clientes: pd.DataFrame | None = None,
          campania: str | None = None,
          idioma: str = IDIOMA_DEFAULT) -> dict:
    """Todo lo que muestra la pantalla del módulo, en un solo cálculo."""
    v = enriquecer(ventas, productos, clientes)
    t = _TEXTOS[_idioma(idioma)]
    medible = descuento_medible(v, productos)

    tabla_rfm = rfm(v, idioma=idioma)
    n_clientes = int(tabla_rfm["cliente_id"].nunique()) if not tabla_rfm.empty else 0
    aviso_rfm = (None if n_clientes >= MINIMO_CLIENTES_RFM
                 else t["pocos_clientes"].format(n=n_clientes,
                                                 minimo=MINIMO_CLIENTES_RFM))

    e = ediciones(v)
    elegida = campania or (e["campania"].iloc[-1] if not e.empty else None)
    detalle = None
    if elegida is not None:
        fila = e[e["campania"] == elegida].iloc[-1]
        detalle = {
            "campania": elegida,
            "desde": str(pd.to_datetime(fila["desde"]).date()),
            "hasta": str(pd.to_datetime(fila["hasta"]).date()),
            "contra_normal": contra_normal(v, fila["desde"], fila["hasta"],
                                           productos, idioma),
            "contra_anterior": contra_anterior(v, elegida, productos=productos,
                                               idioma=idioma),
            "stock": stock_de_campania(v, productos, fila["desde"], fila["hasta"]),
        }

    return {
        "titulos": titulos(idioma),
        "rfm": tabla_rfm,
        "segmentos": resumen_segmentos(tabla_rfm, idioma),
        "aviso_rfm": aviso_rfm,
        "cohortes": cohortes(v),
        "ediciones": e,
        "detalle": detalle,
        "descuento_medible": medible,
        "aviso_descuento": None if medible else t["sin_precio"],
    }
