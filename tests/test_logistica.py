# © 2026 Martín Viera. Todos los derechos reservados.

"""Logística: las cinco sugerencias y sus frenos.

Portado del motor de Plania. Lo que se prueba no es que la cuenta dé, sino que
la sugerencia **sea aplicable**: quien la lee es un encargado de compras
poniendo su plata, y una lista que sugiere comprar de más, vender a pérdida o
subir precios de forma inaceptable no se corrige — se deja de mirar entera, y
con ella las sugerencias que sí servían.

Datos sintéticos armados en el test (`CLAUDE.md`).
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import logistica as klog  # noqa: E402


@pytest.fixture()
def productos():
    return pd.DataFrame({
        "sku": ["A-1", "A-2", "A-3", "A-4"],
        "nombre": ["Filtro chico", "Filtro grande", "Aceite 5W", "Correa"],
        "categoria": ["Filtros", "Filtros", "Lubricantes", "Correas"],
        "proveedor": ["Prov1", "Prov1", "Prov2", "Prov2"],
        "precio": [100.0, 250.0, 400.0, 180.0],
        "costo": [70.0, 150.0, 300.0, 90.0],
        "stock": [900, 12, 500, 40],       # A-1 y A-3 parados, A-2 al límite
        "stock_min": [50, 20, 40, 15],
        "lead_time_dias": [7, 12, 10, 5],
    })


@pytest.fixture()
def ventas():
    """180 días de ventas: A-1 casi no rota, A-2 vuela, A-3 parado, A-4 normal."""
    filas = []
    base = pd.Timestamp("2026-01-01")
    for d in range(180):
        fecha = base + pd.Timedelta(days=d)
        if d % 30 == 0:
            filas.append({"fecha": fecha, "sku": "A-1", "cantidad": 1,
                          "cliente_id": "C1", "venta_id": f"V{d}a", "zona": "Norte"})
        filas.append({"fecha": fecha, "sku": "A-2", "cantidad": 3,
                      "cliente_id": "C2", "venta_id": f"V{d}b", "zona": "Sur"})
        if d % 45 == 0:
            filas.append({"fecha": fecha, "sku": "A-3", "cantidad": 1,
                          "cliente_id": "C3", "venta_id": f"V{d}c", "zona": "Norte"})
        if d % 3 == 0:
            filas.append({"fecha": fecha, "sku": "A-4", "cantidad": 2,
                          "cliente_id": "C1", "venta_id": f"V{d}d", "zona": "Sur"})
    return pd.DataFrame(filas)


@pytest.fixture()
def v(ventas, productos):
    return klog.enriquecer(ventas, productos)


# ---------------------------------------------------------------------------
# Validación de entrada
# ---------------------------------------------------------------------------
def test_una_tabla_incompleta_dice_que_columna_falta(productos):
    """Un KeyError de pandas a mitad del cálculo no le dice al cliente qué le
    falta a su archivo, y su archivo es lo único que puede arreglar."""
    with pytest.raises(klog.DatosIncompletos) as e:
        klog.enriquecer(pd.DataFrame({"fecha": [], "sku": []}), productos)
    assert "cantidad" in str(e.value)


def test_enriquecer_es_idempotente(ventas, productos):
    """La pantalla la llama varias veces por sesión; volver a mezclar
    duplicaría las columnas de producto y rompería los cálculos siguientes."""
    una = klog.enriquecer(ventas, productos)
    dos = klog.enriquecer(una, productos)
    assert list(una.columns) == list(dos.columns)
    assert len(una) == len(dos)


# ---------------------------------------------------------------------------
# Ofertas: el freno del margen
# ---------------------------------------------------------------------------
def test_lo_parado_aparece_en_ofertas(productos, v):
    o = klog.ofertas(productos, v)
    assert "A-1" in set(o["sku"]), "el producto con 900 unidades paradas no se sugiere ofertar"


def test_lo_que_rota_bien_no_se_oferta(productos, v):
    o = klog.ofertas(productos, v)
    assert "A-2" not in set(o["sku"]), "está ofertando algo que ya vende bien"


def test_ninguna_oferta_vende_por_debajo_del_piso(productos, v):
    """El freno que impide que la fórmula regale mercadería: cuanto más parado
    está algo más descuento pide, y el óptimo de 'sacártelo de encima' es
    tirarlo. Vender a pérdida puede ser válido, pero lo decide el dueño."""
    o = klog.ofertas(productos, v)
    con_costo = o.merge(productos[["sku", "costo"]], on="sku")
    piso = con_costo["costo"] * (1 + klog.MARGEN_MINIMO)
    assert (con_costo["precio_oferta"] >= piso - 0.01).all(), \
        con_costo[["sku", "precio_oferta", "costo"]].to_dict("records")


def test_cada_oferta_explica_por_que(productos, v):
    """Sin el porqué, el encargado de compras no le cree — y con razón."""
    o = klog.ofertas(productos, v)
    assert (o["motivo"].str.len() > 20).all()
    assert o["motivo"].str.contains("inmovilizados").all()


# ---------------------------------------------------------------------------
# Reposición
# ---------------------------------------------------------------------------
def test_lo_que_se_agota_antes_de_que_llegue_el_proveedor_se_repone(productos, v):
    r = klog.reposicion(productos, v)
    assert "A-2" in set(r["sku"]), \
        "no avisó del que se agota antes del lead time del proveedor"


def test_no_se_repone_lo_que_sobra(productos, v):
    r = klog.reposicion(productos, v)
    assert "A-1" not in set(r["sku"]), "sugiere comprar más de algo que ya está parado"


def test_la_cantidad_sugerida_nunca_es_negativa(productos, v):
    r = klog.reposicion(productos, v)
    if len(r):
        assert (r["cantidad_sugerida"] > 0).all()


def test_sin_lead_time_se_usa_un_supuesto_explicito(productos, v):
    """Una cartera sin esa columna no puede quedar sin reposición; el supuesto
    se documenta en el código en vez de dejar un cero mudo que haría parecer
    que todo llega instantáneo."""
    sin = productos.drop(columns=["lead_time_dias"])
    r = klog.reposicion(sin, v)
    assert isinstance(r, pd.DataFrame)


# ---------------------------------------------------------------------------
# Precios
# ---------------------------------------------------------------------------
def test_las_subas_sugeridas_son_creibles(productos, v):
    """Por debajo de 0,5% no vale tocar la lista de precios; por arriba de 25%
    el cliente no la acepta. Una sugerencia que nadie va a aplicar es ruido
    que hace desconfiar del resto de la lista."""
    p = klog.precios(productos, v)
    if len(p):
        assert (p["suba_pct"] > 0.5).all() and (p["suba_pct"] < 25).all()


def test_el_precio_sugerido_siempre_supera_el_costo(productos, v):
    p = klog.precios(productos, v)
    if len(p):
        con_costo = p.merge(productos[["sku", "costo"]], on="sku")
        assert (con_costo["precio_sugerido"] > con_costo["costo"]).all()


# ---------------------------------------------------------------------------
# Zonas y recupero
# ---------------------------------------------------------------------------
def test_sin_columna_de_zona_no_explota(productos, v):
    """Muchas carteras no tienen zona: devolver vacío es correcto, romper no."""
    sin_zona = v.drop(columns=["zona"])
    assert klog.zonas(sin_zona).empty


def test_el_cliente_dormido_se_mide_contra_su_propio_ritmo(productos):
    """Uno que compra cada tres meses no está perdido a los 60 días y uno que
    compraba semanal sí. Un umbral fijo llenaría la lista de falsos avisos."""
    base = pd.Timestamp("2026-01-01")
    filas = []
    # Semanal, dejó de comprar hace 90 días -> dormido
    for s in range(20):
        filas.append({"fecha": base + pd.Timedelta(weeks=s), "sku": "A-1",
                      "cantidad": 1, "cliente_id": "SEMANAL", "venta": 100.0,
                      "margen": 30.0})
    # Trimestral, última compra hace 90 días -> al día para su ritmo
    for q in range(4):
        filas.append({"fecha": base + pd.Timedelta(days=90 * q), "sku": "A-1",
                      "cantidad": 1, "cliente_id": "TRIMESTRAL", "venta": 100.0,
                      "margen": 30.0})
    v = pd.DataFrame(filas)
    v["fecha"] = pd.to_datetime(v["fecha"])

    r = klog.recuperar_clientes(v)
    dormidos = set(r["cliente_id"]) if len(r) else set()
    assert "SEMANAL" in dormidos, "no detectó al que compraba todas las semanas"
    assert "TRIMESTRAL" not in dormidos, \
        "marcó como dormido a uno que compra cada tres meses y está en fecha"


# ---------------------------------------------------------------------------
# Integración
# ---------------------------------------------------------------------------
def test_todas_devuelve_las_cinco_listas(productos, ventas):
    d = klog.todas(productos, ventas)
    for clave in ("indicadores", "ofertas", "reposicion", "precios", "zonas",
                  "recuperar"):
        assert clave in d
    assert d["indicadores"]["valor_stock"] > 0


def test_los_indicadores_cuadran_con_los_datos(productos, ventas):
    d = klog.todas(productos, ventas)
    i = d["indicadores"]
    esperado = float((productos["stock"] * productos["costo"]).sum())
    assert abs(i["valor_stock"] - esperado) < 0.01
    assert 0 <= i["margen_pct"] <= 100
