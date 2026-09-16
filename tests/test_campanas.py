# © 2026 Martín Viera. Todos los derechos reservados.

"""Campañas segmentadas, RFM y cohortes.

Los tests se apoyan en datos donde el resultado correcto se conoce de
antemano: si se inyecta un 20% de descuento, el módulo tiene que informar
20,0%; si la segunda edición vende la mitad que la primera, tiene que decir
-50%. Medir contra una expectativa calculada por el mismo código no probaría
nada.

La otra mitad de este archivo son las guardas. Un panel de campañas es un
lugar donde es facilísimo mostrar un número que parece una medición y es un
artefacto: «0% de descuento» cuando en realidad el archivo no traía precios,
o «+300%» contra un período previo que también estaba en promoción. Cada una
de esas tiene su test.
"""
import json
import math
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from kobra import campanas as kc  # noqa: E402
from kobra.logistica import DatosIncompletos, enriquecer  # noqa: E402

PRECIO = 1000.0


def _productos(n=6, stock=400):
    return pd.DataFrame({
        "sku": [f"S{i}" for i in range(n)],
        "nombre": [f"Prod {i}" for i in range(n)],
        "categoria": ["A"] * n,
        "precio": [PRECIO] * n,
        "costo": [PRECIO * 0.6] * n,
        "stock": [stock] * n,
    })


def _ventas(tramos, semilla=42, skus=5, clientes=35):
    """`tramos` = [(desde, hasta, lineas_por_dia, descuento, campania), …]."""
    rng = np.random.default_rng(semilla)
    filas = []
    for desde, hasta, lineas, desc, camp in tramos:
        for dia in pd.date_range(desde, hasta):
            for _ in range(lineas):
                filas.append({
                    "fecha": dia,
                    "sku": f"S{rng.integers(0, skus)}",
                    "cantidad": int(rng.integers(1, 4)),
                    "cliente_id": f"C{rng.integers(0, clientes):02d}",
                    "precio_unit": PRECIO * (1 - desc),
                    "campania": camp,
                })
    return pd.DataFrame(filas)


@pytest.fixture(scope="module")
def caso():
    """Dos ediciones de la misma campaña, la segunda con la MITAD de líneas.

    Es el caso que el módulo existe para contar: una campaña que le gana a un
    día normal y al mismo tiempo rinde la mitad que su edición anterior.
    """
    productos = _productos()
    ventas = _ventas([
        ("2025-01-01", "2025-04-24", 8, 0.0, None),
        ("2025-04-25", "2025-05-01", 24, 0.20, "Hot Sale"),   # edición 1
        ("2025-05-02", "2026-04-24", 8, 0.0, None),
        ("2026-04-25", "2026-05-01", 12, 0.20, "Hot Sale"),   # edición 2: mitad
    ])
    return productos, ventas, enriquecer(ventas, productos)


# ---------------------------------------------------------------------------
# Ediciones y comparaciones
# ---------------------------------------------------------------------------

def test_dos_corridas_de_la_misma_campania_son_dos_ediciones(caso):
    """Separadas por un año: el cliente no tiene que numerar nada a mano."""
    _, _, v = caso
    e = kc.ediciones(v)
    assert list(e["campania"]) == ["Hot Sale", "Hot Sale"]
    assert list(e["edicion"]) == [1, 2]
    assert str(e.iloc[0]["desde"].date()) == "2025-04-25"
    assert str(e.iloc[1]["desde"].date()) == "2026-04-25"


def test_dias_seguidos_de_la_misma_campania_son_UNA_edicion(caso):
    """El contrapeso: si cada día fuera una edición, «la anterior» sería ayer
    y la comparación no diría nada."""
    productos = _productos()
    v = enriquecer(_ventas([("2026-04-01", "2026-04-20", 5, 0.1, "Promo")]),
                   productos)
    assert len(kc.ediciones(v)) == 1


def test_el_descuento_informado_es_el_que_de_verdad_se_aplico(caso):
    productos, _, v = caso
    e = kc.ediciones(v)
    fila = e[e["edicion"] == 2].iloc[0]
    r = kc.contra_normal(v, fila["desde"], fila["hasta"], productos)
    assert r["campania"]["descuento_pct"] == pytest.approx(20.0, abs=0.01)
    assert r["variacion"]["precio_promedio"] == pytest.approx(-20.0, abs=0.01)


def test_contra_lo_normal_toma_el_mismo_largo_y_el_tramo_pegado_antes(caso):
    productos, _, v = caso
    r = kc.contra_normal(v, "2026-04-25", "2026-05-01", productos)
    assert r["hay_base"] is True
    assert r["dias"] == 7
    assert r["desde"] == "2026-04-18" and r["hasta"] == "2026-04-24"
    # 12 líneas/día contra 8: más unidades, aunque las cantidades sean al azar.
    assert r["variacion"]["unidades"] > 0


def test_contra_la_edicion_anterior_ve_la_caida_que_lo_normal_esconde(caso):
    """El punto entero del módulo.

    Contra un día normal la campaña se ve bien; contra su propia edición
    anterior vendió la mitad. Las dos cosas son ciertas y hay que ver las dos.
    """
    productos, _, v = caso
    normal = kc.contra_normal(v, "2026-04-25", "2026-05-01", productos)
    anterior = kc.contra_anterior(v, "Hot Sale", productos=productos)

    assert normal["variacion"]["unidades"] > 0, "contra un día normal, vendió más"
    assert anterior["hay_anterior"] is True
    assert anterior["edicion"] == 2 and anterior["edicion_anterior"] == 1
    assert anterior["variacion"]["unidades"] == pytest.approx(-50, abs=8), (
        "se inyectó la mitad de líneas que en la edición 1")


def test_el_stock_se_mide_al_ritmo_de_la_campania_no_al_historico(caso):
    """En el medio de una promoción la pregunta es «¿me alcanza a ESTE ritmo?»,
    no «¿cuánto me duraba antes?»."""
    productos, _, v = caso
    st = kc.stock_de_campania(v, productos, "2026-04-25", "2026-05-01")
    assert not st.empty
    assert {"sku", "unidades", "stock", "cobertura_dias"} <= set(st.columns)
    fila = st.iloc[0]
    esperado = fila["stock"] / (fila["unidades"] / 7)
    assert fila["cobertura_dias"] == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# RFM y cohortes
# ---------------------------------------------------------------------------

def test_el_rfm_reparte_a_todos_los_clientes_en_un_segmento(caso):
    _, _, v = caso
    t = kc.rfm(v)
    assert len(t) == t["cliente_id"].nunique()
    assert set(t["segmento"]) <= set(kc.SEGMENTOS)
    assert t["segmento_nombre"].notna().all()


def test_el_rfm_no_depende_del_dia_en_que_se_corre(caso):
    """Si tomara la fecha del sistema, el mismo archivo daría segmentos
    distintos cada día y ningún test podría fijarlo."""
    _, _, v = caso
    a = kc.rfm(v, hoy="2026-05-01")
    b = kc.rfm(v, hoy="2026-05-01")
    assert a.equals(b)
    c = kc.rfm(v, hoy="2027-05-01")
    assert not c.equals(a), "con un año más de recencia, los segmentos cambian"


def test_el_que_compro_mucho_pero_hace_un_anio_esta_dormido_no_leal(caso):
    """La recencia manda sobre el puntaje pasado cierto punto."""
    productos = _productos()
    v = enriquecer(_ventas([("2024-01-01", "2024-03-31", 6, 0.0, None)]), productos)
    t = kc.rfm(v, hoy="2026-01-01")
    assert (t["segmento"] == "hibernando").any() or (t["segmento"] == "perdidos").any()
    assert not (t["segmento"].isin(("campeones", "leales"))).any()


def test_la_frecuencia_cuenta_dias_con_compra_y_no_lineas(caso):
    """Tres líneas del mismo ticket son una compra, no tres. Contarlas como
    tres convierte a quien compra carritos grandes en «frecuente»."""
    productos = _productos()
    ventas = pd.DataFrame([
        {"fecha": "2026-01-01", "sku": "S0", "cantidad": 1, "cliente_id": "C1",
         "precio_unit": PRECIO, "campania": None},
        {"fecha": "2026-01-01", "sku": "S1", "cantidad": 1, "cliente_id": "C1",
         "precio_unit": PRECIO, "campania": None},
        {"fecha": "2026-01-01", "sku": "S2", "cantidad": 1, "cliente_id": "C1",
         "precio_unit": PRECIO, "campania": None},
    ])
    t = kc.rfm(enriquecer(ventas, productos))
    assert int(t.iloc[0]["frecuencia"]) == 1


def test_las_cohortes_miden_la_retencion_que_de_verdad_hubo():
    """Datos armados para que la respuesta se sepa: de cada cohorte de 10, la
    mitad vuelve al mes siguiente y 3 al subsiguiente."""
    productos = _productos()
    filas = []
    for mes in range(6):
        ini = pd.Timestamp("2026-01-01") + pd.DateOffset(months=mes)
        for c in range(10):
            cid = f"M{mes}C{c}"
            filas.append({"fecha": ini, "sku": "S0", "cantidad": 1,
                          "cliente_id": cid, "precio_unit": PRECIO})
            if c < 5:
                filas.append({"fecha": ini + pd.DateOffset(months=1), "sku": "S0",
                              "cantidad": 1, "cliente_id": cid, "precio_unit": PRECIO})
            if c < 3:
                filas.append({"fecha": ini + pd.DateOffset(months=2), "sku": "S0",
                              "cantidad": 1, "cliente_id": cid, "precio_unit": PRECIO})
    coh = kc.cohortes(enriquecer(pd.DataFrame(filas), productos))
    primera = coh.iloc[0]
    assert primera["clientes"] == 10
    assert primera["mes_0"] == 100.0
    assert primera["mes_1"] == 50.0
    assert primera["mes_2"] == 30.0


# ---------------------------------------------------------------------------
# Las guardas: no informar un número que no se midió
# ---------------------------------------------------------------------------

def test_sin_precio_de_venta_el_descuento_es_None_y_no_cero():
    """El defecto más fácil de cometer acá.

    `logistica.enriquecer` completa el precio faltante con el de lista, así
    que el descuento da 0 POR CONSTRUCCIÓN. Informar «0% de descuento» no es
    un redondeo: es afirmar que no hubo promoción cuando lo que pasa es que no
    se puede saber.
    """
    productos = _productos()
    ventas = _ventas([("2026-01-01", "2026-03-31", 4, 0.0, None),
                      ("2026-04-01", "2026-04-07", 10, 0.0, "Promo")])
    ventas = ventas.drop(columns=["precio_unit"])      # el ERP no lo exporta
    d = kc.todas(productos, ventas)

    assert d["descuento_medible"] is False
    assert d["aviso_descuento"], "tiene que explicar por qué no está el número"
    assert d["detalle"]["contra_normal"]["campania"]["descuento_pct"] is None


def test_con_precio_de_venta_propio_el_descuento_si_se_mide():
    """El contrapeso: la guarda no puede tapar el caso bueno."""
    productos = _productos()
    ventas = _ventas([("2026-01-01", "2026-03-31", 4, 0.0, None),
                      ("2026-04-01", "2026-04-07", 10, 0.30, "Promo")])
    d = kc.todas(productos, ventas)
    assert d["descuento_medible"] is True
    assert d["aviso_descuento"] is None
    assert d["detalle"]["contra_normal"]["campania"]["descuento_pct"] == pytest.approx(
        30.0, abs=0.01)


def test_si_el_periodo_previo_tambien_estaba_en_promo_no_se_compara():
    """Compararse contra otra promoción hace ver a la campaña peor de lo que
    fue, y nadie se entera de que la base estaba contaminada."""
    productos = _productos()
    ventas = _ventas([("2026-03-25", "2026-03-31", 6, 0.15, "Otra"),
                      ("2026-04-01", "2026-04-07", 6, 0.20, "Promo")])
    r = kc.contra_normal(enriquecer(ventas, productos), "2026-04-01", "2026-04-07",
                         productos)
    assert r["hay_base"] is False
    assert "normal" in r["motivo"].lower() or "comparar" in r["motivo"].lower()


def test_la_primera_edicion_lo_dice_en_vez_de_comparar_contra_nada():
    productos = _productos()
    ventas = _ventas([("2026-04-01", "2026-04-07", 6, 0.2, "Promo")])
    r = kc.contra_anterior(enriquecer(ventas, productos), "Promo", productos=productos)
    assert r["hay_anterior"] is False
    assert r["motivo"]
    assert r["actual"]["unidades"] > 0, "igual informa cómo le fue a esta"


def test_con_pocos_clientes_avisa_que_los_quintiles_son_ruido():
    productos = _productos()
    ventas = _ventas([("2026-01-01", "2026-02-01", 2, 0.0, None)], clientes=4)
    d = kc.todas(productos, ventas)
    assert d["aviso_rfm"] and "4" in d["aviso_rfm"]


def test_una_variacion_sin_base_es_None_y_no_un_cero_tranquilizador():
    """`_variacion` contra cero: devolver 0 convierte «no tengo con qué
    comparar» en «no cambió nada», que es otra afirmación."""
    assert kc._variacion(100, 0) is None
    assert kc._variacion(100, None) is None
    assert kc._variacion(150, 100) == pytest.approx(50.0)


def test_una_campania_que_no_existe_lo_dice_con_su_nombre():
    productos = _productos()
    ventas = _ventas([("2026-04-01", "2026-04-07", 4, 0.1, "Promo")])
    with pytest.raises(DatosIncompletos, match="Inventada"):
        kc.contra_anterior(enriquecer(ventas, productos), "Inventada")


def test_un_sku_vendido_que_no_esta_en_el_maestro_no_rompe_el_json():
    """Pasa siempre: un alta nueva, un catálogo desactualizado. El merge deja
    NaN, y `NaN` no es JSON válido — el fetch del navegador falla entero y la
    pantalla queda vacía sin ningún error visible."""
    productos = _productos(n=1)
    ventas = pd.DataFrame([
        {"fecha": "2026-04-01", "sku": "S0", "cantidad": 5, "cliente_id": "C1",
         "precio_unit": 900.0, "campania": "P"},
        {"fecha": "2026-04-01", "sku": "S9", "cantidad": 5, "cliente_id": "C1",
         "precio_unit": 900.0, "campania": "P"},
    ])
    st = kc.stock_de_campania(enriquecer(ventas, productos), productos,
                              "2026-04-01", "2026-04-07")
    crudo = st.to_dict("records")
    with pytest.raises(ValueError):
        json.dumps(crudo, allow_nan=False)

    from webapp.backend.api import _sin_infinitos
    limpio = _sin_infinitos(crudo)
    json.dumps(limpio, allow_nan=False)          # no levanta
    assert any(f["cobertura_dias"] is None for f in limpio)


def test_sin_columna_de_cliente_el_rfm_lo_dice_en_vez_de_reventar():
    productos = _productos()
    ventas = _ventas([("2026-01-01", "2026-02-01", 3, 0.0, None)])
    ventas = ventas.drop(columns=["cliente_id"])
    with pytest.raises(DatosIncompletos, match="cliente_id"):
        kc.rfm(enriquecer(ventas, productos))


# ---------------------------------------------------------------------------
# Idiomas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("idioma", ["es", "pt", "en", "pt-BR", "zz", None])
def test_los_textos_salen_completos_en_cualquier_idioma(idioma):
    """Incluye los que no existen: un idioma desconocido cae en español y no
    deja la pantalla con claves crudas."""
    t = kc.titulos(idioma)
    assert set(t) == {"rfm", "cohortes", "campanias"}
    assert all(isinstance(x, str) and x for x in t.values())
    segs = kc.nombres_segmentos(idioma)
    assert set(segs) == set(kc.SEGMENTOS)
    assert all(isinstance(x, str) and x for x in segs.values())


def test_los_tres_idiomas_traducen_de_verdad():
    """Un diccionario copiado y pegado sin traducir pasa cualquier test que
    solo mire que la clave exista."""
    es, en = kc.nombres_segmentos("es"), kc.nombres_segmentos("en")
    assert es["campeones"] != en["campeones"]
    assert es["en_riesgo"] != en["en_riesgo"]
    for idi in kc.IDIOMAS:
        faltan = [c for c in _TEXTO_ESPERADO if c not in kc._TEXTOS[idi]]
        assert not faltan, f"a «{idi}» le faltan textos: {faltan}"


_TEXTO_ESPERADO = tuple(kc._TEXTOS["es"])


def test_no_quedaron_infinitos_sueltos_en_el_resumen(caso):
    """Barrido final sobre el payload entero, por si alguna cuenta futura
    vuelve a meter un inf donde la pantalla espera un número."""
    productos, ventas, _ = caso
    d = kc.todas(productos, ventas, campania="Hot Sale")
    for clave in ("rfm", "segmentos", "cohortes"):
        for fila in d[clave].to_dict("records"):
            for k, val in fila.items():
                assert not (isinstance(val, float) and math.isinf(val)), (
                    f"{clave}.{k} es infinito")
