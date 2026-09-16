# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Logística y reposición
====================================
Módulo de la suite, se vende aparte (`plan.exigir("logistica")`). Portado del
motor de Plania (`plania/analitica.py` + `plania/sugerencias.py`).

Convierte el stock y las ventas del cliente en cinco decisiones concretas:

  1. **Qué ofertar**   — lo que lleva demasiado tiempo parado inmovilizando plata
  2. **Qué reponer**   — lo que se agota antes de que llegue el proveedor
  3. **Qué re-precificar** — lo que vende bien pero deja poco margen
  4. **Qué zona atacar**  — dónde hay venta sin explotar
  5. **A quién recuperar** — el cliente que compraba y dejó de comprar

Por qué cada sugerencia lleva su "porqué"
------------------------------------------
Una lista de SKUs sin explicación no se usa: el encargado de compras no le
cree a una recomendación que no puede verificar, y con razón — es su plata.
Cada fila trae los números que la justifican ("quedan 4 días de stock y el
proveedor demora 12"), así que la decisión la sigue tomando una persona con
la cuenta a la vista, no el programa por ella.

Por qué el descuento tiene un piso
-----------------------------------
`MARGEN_MINIMO` impide sugerir una venta por debajo de costo + 8%. Sin ese
piso, la fórmula de descuento por sobrestock llega sola a regalar mercadería:
cuanto más parado está algo, más descuento pide, y el óptimo matemático de
"sacártelo de encima" es tirarlo. Vender a pérdida puede ser una decisión
válida del negocio, pero la toma el dueño, no una fórmula.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Piso de margen para cualquier oferta sugerida: nunca por debajo de costo+8%.
MARGEN_MINIMO = 0.08
# A partir de cuántos días de stock algo se considera parado.
DIAS_SOBRESTOCK = 90
# A cuántos días de stock se quiere llegar con la oferta.
DIAS_OBJETIVO = 45
# Días de aire sobre el tiempo de entrega del proveedor antes de alertar.
COLCHON_REPOSICION = 5

# Columnas mínimas de cada tabla. Se validan antes de calcular: un KeyError de
# pandas a mitad del cálculo no le dice al cliente qué le falta a su archivo.
COLUMNAS_PRODUCTOS = ("sku", "nombre", "categoria", "precio", "costo", "stock")
COLUMNAS_VENTAS = ("fecha", "sku", "cantidad")

# ---------------------------------------------------------------------------
# Idioma del texto VISIBLE (es · pt · en)
# ---------------------------------------------------------------------------
# El título de cada lista y el "por qué" de cada fila son lo único que lee una
# persona acá; el resto son números. Un cliente que eligió inglés veía el menú
# traducido y el motivo en castellano, que es peor que no explicar nada: la
# explicación es justamente lo que hace que le crea a la sugerencia.
#
# Las claves de las listas (`ofertas`, `reposicion`…) NO se traducen: son las
# del diccionario que devuelve `todas` y las que consume la pantalla.
IDIOMA_DEFAULT = "es"
IDIOMAS = ("es", "pt", "en")

_TEXTOS = {
    "es": {
        "titulo_ofertas": "Qué ofertar",
        "titulo_reposicion": "Qué reponer",
        "titulo_precios": "Qué re-precificar",
        "titulo_zonas": "Zonas",
        "titulo_recuperar": "Clientes a recuperar",
        "motivo_oferta": "{dias} días de stock ({unidades} un., venta diaria "
                         "{diaria}) — ${capital} inmovilizados",
        "motivo_reposicion": "Quedan {dias} días de stock y el proveedor demora "
                             "{lead} — riesgo de perder ${riesgo}/mes de venta",
        "motivo_precio": "Margen actual {actual}% vs {objetivo}% de su categoría "
                         "— subir {suba}% suma ${extra}/mes",
        "motivo_zona": "${por_cliente} por cliente vs ${mediana} de la mediana "
                       "— ${potencial} sin capturar",
        "motivo_recuperar": "Compraba cada {cada} días y hace {sin_comprar} que "
                            "no compra — ${perdida}/mes en juego",
    },
    "pt": {
        "titulo_ofertas": "O que ofertar",
        "titulo_reposicion": "O que repor",
        "titulo_precios": "O que reprecificar",
        "titulo_zonas": "Zonas",
        "titulo_recuperar": "Clientes a recuperar",
        "motivo_oferta": "{dias} dias de estoque ({unidades} un., venda diária "
                         "{diaria}) — ${capital} parados",
        "motivo_reposicion": "Restam {dias} dias de estoque e o fornecedor demora "
                             "{lead} — risco de perder ${riesgo}/mês de venda",
        "motivo_precio": "Margem atual {actual}% vs {objetivo}% da sua categoria "
                         "— subir {suba}% soma ${extra}/mês",
        "motivo_zona": "${por_cliente} por cliente vs ${mediana} da mediana "
                       "— ${potencial} sem capturar",
        "motivo_recuperar": "Comprava a cada {cada} dias e faz {sin_comprar} que "
                            "não compra — ${perdida}/mês em jogo",
    },
    "en": {
        "titulo_ofertas": "What to discount",
        "titulo_reposicion": "What to restock",
        "titulo_precios": "What to reprice",
        "titulo_zonas": "Zones",
        "titulo_recuperar": "Customers to win back",
        "motivo_oferta": "{dias} days of stock ({unidades} units, daily sales "
                         "{diaria}) — ${capital} tied up",
        "motivo_reposicion": "{dias} days of stock left and the supplier takes "
                             "{lead} — risk of losing ${riesgo}/month in sales",
        "motivo_precio": "Current margin {actual}% vs {objetivo}% for its category "
                         "— raising it {suba}% adds ${extra}/month",
        "motivo_zona": "${por_cliente} per customer vs ${mediana} median "
                       "— ${potencial} left on the table",
        "motivo_recuperar": "Used to buy every {cada} days and hasn't bought in "
                            "{sin_comprar} — ${perdida}/month at stake",
    },
}


def _idioma(idioma: str | None) -> str:
    """Normaliza el código de idioma: 'pt-BR' → 'pt', desconocido → 'es'."""
    corto = str(idioma or "").strip().lower().replace("_", "-").split("-")[0]
    return corto if corto in IDIOMAS else IDIOMA_DEFAULT


def titulos(idioma: str = IDIOMA_DEFAULT) -> dict:
    """Título de cada una de las cinco listas, por su clave en `todas`."""
    t = _TEXTOS[_idioma(idioma)]
    return {clave: t[f"titulo_{clave}"]
            for clave in ("ofertas", "reposicion", "precios", "zonas", "recuperar")}


class DatosIncompletos(ValueError):
    """Falta una columna necesaria. El mensaje nombra cuál y en qué tabla."""


def _exigir(df: pd.DataFrame, columnas, tabla: str) -> None:
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise DatosIncompletos(
            f"A la tabla de {tabla} le faltan columnas: {', '.join(faltan)}. "
            f"Se necesitan: {', '.join(columnas)}.")


# ---------------------------------------------------------------------------
# Analítica base
# ---------------------------------------------------------------------------
def enriquecer(ventas: pd.DataFrame, productos: pd.DataFrame,
               clientes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Ventas + producto + cliente en una sola tabla de trabajo.

    Idempotente a propósito: la pantalla la llama varias veces por sesión y
    volver a mezclar duplicaría las columnas de producto.
    """
    _exigir(ventas, COLUMNAS_VENTAS, "ventas")
    _exigir(productos, COLUMNAS_PRODUCTOS, "productos")
    if "venta" in ventas.columns and "margen" in ventas.columns:
        return ventas

    v = ventas.copy()
    # `format="mixed"` y no la inferencia por defecto: una tabla de ventas real
    # trae "2026-01-01" y "2026-01-01 09:32:00" en la MISMA columna (una carga
    # manual y una del ERP), y sin esto pandas infiere el formato de la primera
    # fila y manda a NaT todas las demás. Como acá abajo se hace dropna, esas
    # filas NO dan error: desaparecen. Medido con tres ventas de 1, 1 y 5
    # unidades, la última con otro formato: el módulo informaba 2 unidades de 7.
    v["fecha"] = pd.to_datetime(v["fecha"], format="mixed", errors="coerce")
    v = v.dropna(subset=["fecha"])

    if "precio_unit" not in v.columns or v["precio_unit"].isna().all():
        v = v.merge(productos[["sku", "precio"]], on="sku", how="left")
        v["precio_unit"] = v.pop("precio")
    if "costo_unit" not in v.columns or v["costo_unit"].isna().all():
        v = v.merge(productos[["sku", "costo"]], on="sku", how="left")
        v["costo_unit"] = v.pop("costo")

    v["venta"] = v["cantidad"] * v["precio_unit"].fillna(0)
    v["costo_total"] = v["cantidad"] * v["costo_unit"].fillna(0)
    v["margen"] = v["venta"] - v["costo_total"]

    extras = [c for c in ("nombre", "categoria", "proveedor") if c in productos.columns]
    v = v.merge(productos[["sku", *extras]], on="sku", how="left")
    if clientes is not None and len(clientes) and "cliente_id" in v.columns:
        cols = [c for c in ("tipo_negocio", "departamento", "zona")
                if c in clientes.columns]
        if cols:
            v = v.merge(clientes[["cliente_id", *cols]], on="cliente_id", how="left")
    return v


def rotacion(productos: pd.DataFrame, v: pd.DataFrame,
             ventana_dias: int = 90) -> pd.DataFrame:
    """Venta diaria y días de stock por SKU — la base de todo lo demás.

    `dias_stock` es infinito cuando algo no vendió nada en la ventana: no es
    un error sino el dato real, y ponerle 0 lo haría aparecer como urgente de
    reponer, que es exactamente al revés.
    """
    corte = v["fecha"].max() - pd.Timedelta(days=ventana_dias)
    vp = v[v["fecha"] > corte]
    diaria = (vp.groupby("sku")["cantidad"].sum() / ventana_dias).rename("venta_diaria")
    r = productos.merge(diaria, on="sku", how="left")
    r["venta_diaria"] = r["venta_diaria"].fillna(0.0)
    r["dias_stock"] = np.where(r["venta_diaria"] > 0,
                               r["stock"] / r["venta_diaria"], np.inf)
    return r


def margen_por_producto(v: pd.DataFrame) -> pd.DataFrame:
    llaves = [c for c in ("sku", "nombre", "categoria") if c in v.columns]
    g = (v.groupby(llaves, as_index=False)
           .agg(venta=("venta", "sum"), margen=("margen", "sum"),
                unidades=("cantidad", "sum")))
    g["margen_pct"] = np.where(g["venta"] > 0, g["margen"] / g["venta"] * 100, 0.0)
    return g.sort_values("margen", ascending=False).reset_index(drop=True)


def indicadores(productos: pd.DataFrame, v: pd.DataFrame, dias: int = 30) -> dict:
    """Las tarjetas del panel."""
    corte = v["fecha"].max() - pd.Timedelta(days=dias)
    vp = v[v["fecha"] > corte]
    venta = float(vp["venta"].sum())
    margen = float(vp["margen"].sum())
    rot = rotacion(productos, v)
    stock_min = (productos["stock_min"] if "stock_min" in productos.columns
                 else pd.Series(0, index=productos.index))
    return {
        "venta_periodo": venta,
        "margen_periodo": margen,
        "margen_pct": (margen / venta * 100) if venta else 0.0,
        "valor_stock": float((productos["stock"] * productos["costo"]).sum()),
        "quiebres": int((productos["stock"] <= 0).sum()),
        "bajo_minimo": int((productos["stock"] < stock_min).sum()),
        "sobrestock": int((rot["dias_stock"] > DIAS_SOBRESTOCK).sum()),
        "clientes_activos": (int(vp["cliente_id"].nunique())
                             if "cliente_id" in vp.columns else 0),
        "dias": dias,
    }


# ---------------------------------------------------------------------------
# Las cinco sugerencias
# ---------------------------------------------------------------------------
def ofertas(productos: pd.DataFrame, v: pd.DataFrame,
            idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Qué ofertar: lo parado, con un descuento que apure sin regalar margen."""
    motivo = _TEXTOS[_idioma(idioma)]["motivo_oferta"]
    r = rotacion(productos, v)
    sob = r[(r["dias_stock"] > DIAS_SOBRESTOCK) & (r["stock"] > 0)].copy()
    if not len(sob):
        return pd.DataFrame()

    # Descuento proporcional al exceso sobre el objetivo, tope 30%.
    exceso = (sob["dias_stock"].clip(upper=365) - DIAS_OBJETIVO) / 365
    desc = (exceso * 0.35).clip(0.05, 0.30)

    # El piso de margen manda: si el descuento calculado perfora costo+8%, se
    # recorta hasta el piso en vez de sugerir vender a pérdida.
    precio_con_desc = sob["precio"] * (1 - desc)
    piso = sob["costo"] * (1 + MARGEN_MINIMO)
    # Redondear DESPUÉS de multiplicar: `.round(3) * 100` deja el residuo
    # binario del float a la vista (16.900000000000002% en pantalla).
    sob["descuento_pct"] = (np.where(precio_con_desc < piso,
                                     (1 - piso / sob["precio"]).clip(lower=0),
                                     desc) * 100).round(1)
    sob["dias_stock"] = sob["dias_stock"].round(1)
    sob["precio_oferta"] = (sob["precio"] * (1 - sob["descuento_pct"] / 100)).round(2)
    sob["capital_inmovilizado"] = (sob["stock"] * sob["costo"]).round(2)
    sob["motivo"] = sob.apply(
        lambda x: motivo.format(dias=f"{x['dias_stock']:.0f}",
                                unidades=int(x["stock"]),
                                diaria=f"{x['venta_diaria']:.1f}",
                                capital=f"{x['capital_inmovilizado']:,.0f}"), axis=1)
    cols = [c for c in ("sku", "nombre", "categoria", "stock", "dias_stock",
                        "precio", "descuento_pct", "precio_oferta",
                        "capital_inmovilizado", "motivo") if c in sob.columns]
    return (sob[cols].sort_values("capital_inmovilizado", ascending=False)
            .reset_index(drop=True))


def reposicion(productos: pd.DataFrame, v: pd.DataFrame,
               idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Qué comprar ya: lo que se agota antes de que llegue el proveedor."""
    motivo = _TEXTOS[_idioma(idioma)]["motivo_reposicion"]
    r = rotacion(productos, v)
    if "lead_time_dias" not in r.columns:
        r["lead_time_dias"] = 7          # supuesto explícito, no un cero mudo
    riesgo = r[(r["venta_diaria"] > 0)
               & (r["dias_stock"] < r["lead_time_dias"] + COLCHON_REPOSICION)].copy()
    if not len(riesgo):
        return pd.DataFrame()

    riesgo["cantidad_sugerida"] = np.ceil(
        riesgo["venta_diaria"] * 30 - riesgo["stock"]).clip(lower=0).astype(int)
    riesgo = riesgo[riesgo["cantidad_sugerida"] > 0]
    if not len(riesgo):
        return pd.DataFrame()

    riesgo["dias_stock"] = riesgo["dias_stock"].round(1)
    riesgo["inversion"] = (riesgo["cantidad_sugerida"] * riesgo["costo"]).round(2)
    riesgo["venta_en_riesgo"] = (riesgo["venta_diaria"] * riesgo["precio"] * 30).round(2)
    riesgo["motivo"] = riesgo.apply(
        lambda x: motivo.format(dias=f"{x['dias_stock']:.0f}",
                                lead=int(x["lead_time_dias"]),
                                riesgo=f"{x['venta_en_riesgo']:,.0f}"), axis=1)
    cols = [c for c in ("sku", "nombre", "categoria", "proveedor", "stock",
                        "dias_stock", "lead_time_dias", "cantidad_sugerida",
                        "inversion", "venta_en_riesgo", "motivo")
            if c in riesgo.columns]
    return (riesgo[cols].sort_values("venta_en_riesgo", ascending=False)
            .reset_index(drop=True))


def precios(productos: pd.DataFrame, v: pd.DataFrame,
            margen_objetivo_pct: float = 25.0,
            idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Qué re-precificar: vende bien pero deja menos margen que su categoría.

    La suba se acota entre 0,5% y 25%: por debajo no mueve la aguja y no vale
    tocar la lista de precios; por arriba deja de ser creíble que el cliente
    la acepte sin resistencia, y una sugerencia que nadie va a aplicar es
    ruido que hace desconfiar del resto.
    """
    motivo = _TEXTOS[_idioma(idioma)]["motivo_precio"]
    mp = margen_por_producto(v)
    if "categoria" not in mp.columns or not len(mp):
        return pd.DataFrame()

    objetivo = (mp.groupby("categoria")["margen_pct"].median()
                .clip(lower=margen_objetivo_pct).rename("margen_obj"))
    mp = mp.merge(objetivo, on="categoria")
    bajo = mp[(mp["margen_pct"] < mp["margen_obj"] - 3) & (mp["venta"] > 0)].copy()
    if not len(bajo):
        return pd.DataFrame()

    bajo = bajo.merge(productos[["sku", "precio", "costo"]], on="sku")
    bajo["precio_sugerido"] = (bajo["costo"] / (1 - bajo["margen_obj"] / 100)).round(2)
    bajo["suba_pct"] = ((bajo["precio_sugerido"] / bajo["precio"] - 1) * 100).round(1)
    bajo = bajo[(bajo["suba_pct"] > 0.5) & (bajo["suba_pct"] < 25)]
    if not len(bajo):
        return pd.DataFrame()

    bajo["margen_extra_mensual"] = (
        (bajo["precio_sugerido"] - bajo["precio"]) * bajo["unidades"] / 12).round(2)
    bajo["motivo"] = bajo.apply(
        lambda x: motivo.format(actual=f"{x['margen_pct']:.1f}",
                                objetivo=f"{x['margen_obj']:.1f}",
                                suba=f"{x['suba_pct']:.1f}",
                                extra=f"{x['margen_extra_mensual']:,.0f}"), axis=1)
    cols = [c for c in ("sku", "nombre", "categoria", "precio", "precio_sugerido",
                        "suba_pct", "margen_pct", "margen_obj",
                        "margen_extra_mensual", "motivo") if c in bajo.columns]
    return (bajo[cols].sort_values("margen_extra_mensual", ascending=False)
            .reset_index(drop=True))


def zonas(v: pd.DataFrame, idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """Dónde hay venta sin explotar: zonas por debajo de su potencial."""
    motivo = _TEXTOS[_idioma(idioma)]["motivo_zona"]
    if "zona" not in v.columns or v["zona"].isna().all():
        return pd.DataFrame()
    g = (v.groupby("zona", as_index=False)
           .agg(venta=("venta", "sum"), margen=("margen", "sum"),
                clientes=("cliente_id", "nunique")))
    if len(g) < 2:
        return pd.DataFrame()
    g["venta_por_cliente"] = np.where(g["clientes"] > 0, g["venta"] / g["clientes"], 0.0)
    referencia = g["venta_por_cliente"].median()
    flojas = g[g["venta_por_cliente"] < referencia * 0.8].copy()
    if not len(flojas):
        return pd.DataFrame()
    flojas["potencial"] = ((referencia - flojas["venta_por_cliente"])
                           * flojas["clientes"]).round(2)
    flojas["motivo"] = flojas.apply(
        lambda x: motivo.format(por_cliente=f"{x['venta_por_cliente']:,.0f}",
                                mediana=f"{referencia:,.0f}",
                                potencial=f"{x['potencial']:,.0f}"), axis=1)
    return (flojas.sort_values("potencial", ascending=False)
            .reset_index(drop=True))


def recuperar_clientes(v: pd.DataFrame, dias_sin_comprar: int = 60,
                       idioma: str = IDIOMA_DEFAULT) -> pd.DataFrame:
    """A quién recuperar: compraba seguido y dejó de comprar.

    Se mide contra el ritmo propio de cada cliente, no contra un umbral fijo:
    uno que compra cada tres meses no está perdido a los 60 días, y uno que
    compraba semanal sí. Un umbral único llenaría la lista de falsos avisos.
    """
    motivo = _TEXTOS[_idioma(idioma)]["motivo_recuperar"]
    if "cliente_id" not in v.columns or not len(v):
        return pd.DataFrame()
    hoy = v["fecha"].max()
    g = (v.groupby("cliente_id", as_index=False)
           .agg(ultima=("fecha", "max"), primera=("fecha", "min"),
                compras=("fecha", "nunique"), venta=("venta", "sum")))
    g = g[g["compras"] >= 3]
    if not len(g):
        return pd.DataFrame()

    span = (g["ultima"] - g["primera"]).dt.days.clip(lower=1)
    g["cada_dias"] = (span / g["compras"]).round(1)
    g["dias_sin_comprar"] = (hoy - g["ultima"]).dt.days
    # Dormido = pasó más del doble de su propio intervalo, y al menos el piso.
    dormidos = g[(g["dias_sin_comprar"] > g["cada_dias"] * 2)
                 & (g["dias_sin_comprar"] >= dias_sin_comprar)].copy()
    if not len(dormidos):
        return pd.DataFrame()

    dormidos["venta_mensual_perdida"] = (
        dormidos["venta"] / span[dormidos.index] * 30).round(2)
    dormidos["motivo"] = dormidos.apply(
        lambda x: motivo.format(cada=f"{x['cada_dias']:.0f}",
                                sin_comprar=f"{x['dias_sin_comprar']:.0f}",
                                perdida=f"{x['venta_mensual_perdida']:,.0f}"), axis=1)
    return (dormidos.sort_values("venta_mensual_perdida", ascending=False)
            .reset_index(drop=True))


def todas(productos: pd.DataFrame, ventas: pd.DataFrame,
          clientes: pd.DataFrame | None = None,
          idioma: str = IDIOMA_DEFAULT) -> dict:
    """Las cinco listas y los indicadores, en una sola llamada.

    Devuelve solo las listas y los indicadores: los títulos salen de `titulos`,
    aparte, porque quien consume esto trata todas las claves menos
    `indicadores` como tablas y una clave de texto rompería ese recorrido.
    """
    idioma = _idioma(idioma)
    v = enriquecer(ventas, productos, clientes)
    return {
        "indicadores": indicadores(productos, v),
        "ofertas": ofertas(productos, v, idioma),
        "reposicion": reposicion(productos, v, idioma),
        "precios": precios(productos, v, idioma=idioma),
        "zonas": zonas(v, idioma),
        "recuperar": recuperar_clientes(v, idioma=idioma),
    }
