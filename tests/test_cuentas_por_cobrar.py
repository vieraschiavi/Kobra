"""Cuentas por cobrar: los cálculos que un analista de CxC hace todos los días.

Kobra cubría la GESTIÓN de cobranza (a quién llamar, con qué estrategia) pero
no el ANÁLISIS de cuentas por cobrar: antigüedad de saldos, DSO, efectividad,
conciliación de pagos, pagos mal aplicados. Este módulo lo cierra.

Lo que fijan estos tests, más allá de que las cuentas den bien: que ante una
AMBIGÜEDAD el módulo la reporte en vez de elegir. Un pago aplicado a la
factura "que más se parece" deja un saldo mal imputado que reaparece semanas
después como un descuadre que nadie sabe de dónde salió.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pd = pytest.importorskip("pandas")

from kobra import cuentas_por_cobrar as cxc  # noqa: E402


# --- Antigüedad de saldos ---------------------------------------------------
def _cartera():
    return pd.DataFrame([
        {"id_deudor": "A", "monto_deuda": 100000.0, "dias_mora": 15, "tramo_mora": "1-30"},
        {"id_deudor": "B", "monto_deuda": 50000.0, "dias_mora": 45, "tramo_mora": "31-60"},
        {"id_deudor": "C", "monto_deuda": 250000.0, "dias_mora": 200, "tramo_mora": "180+"},
        {"id_deudor": "D", "monto_deuda": 100000.0, "dias_mora": 20, "tramo_mora": "1-30"},
    ])


def test_la_antiguedad_de_saldos_suma_exactamente_la_cartera():
    r = cxc.antiguedad_saldos(_cartera())
    assert r["total_uyu"] == 500000.0
    assert r["deudores"] == 4
    assert round(sum(t["monto_uyu"] for t in r["tramos"]), 2) == 500000.0
    assert round(sum(t["pct_del_total"] for t in r["tramos"]), 4) == 1.0


def test_los_tramos_salen_en_el_orden_del_reporte_no_alfabetico():
    r = cxc.antiguedad_saldos(_cartera())
    orden = [t["tramo"] for t in r["tramos"]]
    assert orden == ["1-30", "31-60", "180+"], orden


def test_una_cartera_vacia_no_revienta():
    assert cxc.antiguedad_saldos(pd.DataFrame())["total_uyu"] == 0.0
    assert cxc.antiguedad_saldos(None)["tramos"] == []


def test_la_concentracion_dice_cuanto_pesan_los_mas_grandes():
    r = cxc.concentracion(_cartera(), top=2)
    assert [f["id_deudor"] for f in r["top"]] == ["C", "A"]
    # C (250k) + A (100k) = 350k de 500k = 70 %.
    assert r["pct_acumulado"] == 0.7


# --- DSO --------------------------------------------------------------------
def test_dso_da_el_numero_del_manual():
    # Ejemplo del propio manual: ventas 1.850.000, saldo 620.000, 31 días.
    r = cxc.dso(1_850_000, 620_000, 31)
    assert r["dso"] == round((620_000 / 1_850_000) * 31, 1)
    assert "saldo CxC / ventas a crédito" in r["formula"]


def test_dso_sin_el_plazo_de_credito_no_dice_si_esta_bien_o_mal():
    """Un DSO de 45 es excelente con plazo 60 y malo con plazo 30. El número
    solo no se puede interpretar, y el módulo no inventa una lectura."""
    r = cxc.dso(1_000_000, 100_000, 30)
    assert "lectura" not in r


def test_dso_con_plazo_dice_cuantos_dias_se_pasa():
    r = cxc.dso(1_000_000, 200_000, 30, plazo_estandar=30)
    assert r["dso"] == 6.0
    assert r["exceso_dias"] == -24.0
    assert "por debajo" in r["lectura"]

    r2 = cxc.dso(1_000_000, 2_000_000, 30, plazo_estandar=30)
    assert r2["exceso_dias"] == 30.0
    assert "POR ENCIMA" in r2["lectura"]


@pytest.mark.parametrize("ventas,dias", [(0, 30), (1000, 0), (-5, 30)])
def test_dso_con_datos_imposibles_avisa_en_vez_de_dividir_por_cero(ventas, dias):
    r = cxc.dso(ventas, 100, dias)
    assert r["dso"] is None and "error" in r


# --- Efectividad de cobranza ------------------------------------------------
def _gestiones():
    return pd.DataFrame([
        {"mes": "2026-07", "monto_gestionado": 1_000_000.0, "recupero": 800_000.0},
        {"mes": "2026-07", "monto_gestionado": 200_000.0, "recupero": 180_000.0},
        {"mes": "2026-06", "monto_gestionado": 1_100_000.0, "recupero": 850_000.0},
    ])


def test_efectividad_es_cobrado_sobre_gestionado():
    r = cxc.efectividad(_gestiones(), mes="2026-07")
    assert r["gestionado_uyu"] == 1_200_000.0
    assert r["cobrado_uyu"] == 980_000.0
    assert r["efectividad"] == round(980_000 / 1_200_000, 4)
    assert r["gestiones"] == 2


def test_la_comparacion_entre_meses_va_en_PUNTOS_no_en_porcentaje_relativo():
    """Comparar dos porcentajes en % relativo es la forma más común de
    exagerar una mejora: de 2 % a 3 % no es '+50 %', es +1 punto."""
    r = cxc.efectividad(_gestiones(), mes="2026-07", mes_comparar="2026-06")
    esperado = round((980_000 / 1_200_000 - 850_000 / 1_100_000) * 100, 1)
    assert r["comparacion"]["variacion_pp"] == esperado
    assert "variacion_pct" not in r["comparacion"]


def test_efectividad_de_un_mes_sin_gestiones_avisa():
    r = cxc.efectividad(_gestiones(), mes="2026-01")
    assert r["efectividad"] is None and "2026-01" in r["error"]


def test_efectividad_sin_las_columnas_necesarias_dice_cuales_faltan():
    r = cxc.efectividad(pd.DataFrame([{"mes": "2026-07"}]), mes="2026-07")
    assert r["efectividad"] is None
    assert "monto_gestionado" in r["error"] and "recupero" in r["error"]


def test_el_ultimo_mes_con_datos_saltea_un_mes_en_curso_sin_monto_gestionado():
    """Bug real encontrado corriendo esto contra la cartera de demo: el último
    mes del archivo tenía 3 gestiones con monto_gestionado en 0, así que el
    tablero mostraba 'sin datos' teniendo 7.000+ gestiones cargadas."""
    g = pd.DataFrame([
        {"mes": "2026-06", "monto_gestionado": 1_000_000.0, "recupero": 700_000.0},
        {"mes": "2026-07", "monto_gestionado": 0.0, "recupero": 9_500.0},
    ])
    assert cxc.ultimo_mes_con_datos(g) == "2026-06"


def test_sin_ningun_mes_calculable_devuelve_None_en_vez_de_elegir_uno_malo():
    g = pd.DataFrame([{"mes": "2026-07", "monto_gestionado": 0.0, "recupero": 100.0}])
    assert cxc.ultimo_mes_con_datos(g) is None
    assert cxc.ultimo_mes_con_datos(pd.DataFrame()) is None
    assert cxc.ultimo_mes_con_datos(None) is None


# --- Conciliación de pagos --------------------------------------------------
FACTURAS = [
    {"id": "F-4501", "monto": 30000.0},
    {"id": "F-4502", "monto": 28300.0},
    {"id": "F-4510", "monto": 15000.0},
]


def test_un_pago_que_calza_con_una_sola_factura():
    r = cxc.conciliar_pago(15000.0, FACTURAS)
    assert r["match"]["facturas"] == ["F-4510"]
    assert r["ambiguo"] is False


def test_un_pago_que_calza_con_la_suma_de_dos_facturas():
    # El ejemplo del manual: 58.300 = 30.000 + 28.300.
    r = cxc.conciliar_pago(58300.0, FACTURAS)
    assert r["match"] is not None
    assert sorted(r["match"]["facturas"]) == ["F-4501", "F-4502"]


def test_cuando_hay_DOS_combinaciones_posibles_no_elige_ninguna():
    """El test que importa: si el monto es ambiguo, aplicar 'la que parece'
    deja un saldo mal imputado que reaparece como un descuadre."""
    facturas = [
        {"id": "F-1", "monto": 10000.0},
        {"id": "F-2", "monto": 10000.0},
        {"id": "F-3", "monto": 7000.0},
    ]
    r = cxc.conciliar_pago(10000.0, facturas)
    assert r["ambiguo"] is True
    assert r["match"] is None, "no puede elegir por su cuenta entre dos opciones válidas"
    assert len(r["candidatos"]) == 2


def test_prefiere_la_explicacion_simple_una_factura_antes_que_tres():
    facturas = [
        {"id": "UNA", "monto": 100.0},
        {"id": "A", "monto": 50.0}, {"id": "B", "monto": 30.0}, {"id": "C", "monto": 20.0},
    ]
    r = cxc.conciliar_pago(100.0, facturas)
    assert r["match"]["facturas"] == ["UNA"]


def test_sin_match_lo_dice_y_muestra_las_mas_cercanas():
    r = cxc.conciliar_pago(99999.0, FACTURAS)
    assert r["sin_match"] is True
    assert r["match"] is None
    assert len(r["mas_cercanas"]) == 3
    assert all("diferencia" in c for c in r["mas_cercanas"])


def test_un_pago_con_centavos_de_diferencia_igual_concilia():
    r = cxc.conciliar_pago(30000.005, FACTURAS)
    assert r["match"]["facturas"] == ["F-4501"]


@pytest.mark.parametrize("monto,facturas", [(0, FACTURAS), (-100, FACTURAS), (100, [])])
def test_conciliar_con_datos_invalidos_avisa(monto, facturas):
    r = cxc.conciliar_pago(monto, facturas)
    assert r["match"] is None and "error" in r


def test_con_muchisimas_facturas_avisa_que_trunco_en_vez_de_decir_sin_match():
    """Un límite silencioso haría creer que no hay match cuando en realidad
    no se buscó — el peor resultado posible en una conciliación."""
    muchas = [{"id": f"F-{i}", "monto": float(1000 + i)} for i in range(200)]
    r = cxc.conciliar_pago(999_999.0, muchas)
    assert "aviso" in r and "no evaluadas" in r["aviso"]


def test_no_explota_con_una_lista_larga_de_facturas():
    """Buscar TODAS las combinaciones es 2^n. Con 200 facturas esto tiene que
    terminar igual, no colgarse."""
    import time
    muchas = [{"id": f"F-{i}", "monto": float(1000 + i)} for i in range(200)]
    t0 = time.time()
    cxc.conciliar_pago(3003.0, muchas)
    assert time.time() - t0 < 10, "la conciliación tarda demasiado"


# --- Pagos duplicados o mal aplicados ---------------------------------------
def test_detecta_el_mismo_pago_cargado_dos_veces():
    pagos = [
        {"referencia": "P-1", "id_deudor": "A", "monto": 5000.0,
         "fecha": "2026-08-01", "factura": "F-1", "monto_factura": 5000.0},
        {"referencia": "P-2", "id_deudor": "A", "monto": 5000.0,
         "fecha": "2026-08-02", "factura": "F-1", "monto_factura": 5000.0},
    ]
    r = cxc.anomalias_en_pagos(pagos)
    tipos = [h["tipo"] for h in r["hallazgos"]]
    assert "posible_duplicado" in tipos
    dup = next(h for h in r["hallazgos"] if h["tipo"] == "posible_duplicado")
    assert sorted(dup["referencias"]) == ["P-1", "P-2"]


def test_dos_pagos_iguales_pero_lejanos_en_el_tiempo_NO_son_duplicado():
    """Un cliente que paga la misma cuota todos los meses no es un error."""
    pagos = [
        {"referencia": "P-1", "id_deudor": "A", "monto": 5000.0,
         "fecha": "2026-06-01", "factura": "F-1", "monto_factura": 5000.0},
        {"referencia": "P-2", "id_deudor": "A", "monto": 5000.0,
         "fecha": "2026-07-01", "factura": "F-2", "monto_factura": 5000.0},
    ]
    r = cxc.anomalias_en_pagos(pagos)
    assert not any(h["tipo"] == "posible_duplicado" for h in r["hallazgos"])


def test_marca_un_pago_sin_factura_asociada():
    r = cxc.anomalias_en_pagos([{"referencia": "P-9", "id_deudor": "B",
                                 "monto": 100.0, "fecha": "2026-08-01"}])
    assert r["hallazgos"][0]["tipo"] == "sin_factura"


def test_marca_cuando_el_pago_no_coincide_con_la_factura():
    r = cxc.anomalias_en_pagos([
        {"referencia": "P-3", "id_deudor": "C", "monto": 112000.0,
         "fecha": "2026-08-01", "factura": "F-4600", "monto_factura": 116000.0},
    ])
    h = r["hallazgos"][0]
    assert h["tipo"] == "monto_no_calza"
    # La diferencia típica de una retención: hay que decir cuánto, no solo que no calza.
    assert "-4000.0" in h["detalle"] or "4000" in h["detalle"]
    assert "verificar" in h["detalle"].lower()


def test_una_conciliacion_limpia_no_inventa_hallazgos():
    pagos = [
        {"referencia": "P-1", "id_deudor": "A", "monto": 5000.0,
         "fecha": "2026-08-01", "factura": "F-1", "monto_factura": 5000.0},
        {"referencia": "P-2", "id_deudor": "B", "monto": 7000.0,
         "fecha": "2026-08-02", "factura": "F-2", "monto_factura": 7000.0},
    ]
    r = cxc.anomalias_en_pagos(pagos)
    assert r["total_hallazgos"] == 0
    assert r["revisados"] == 2


def test_pagos_vacios_o_corruptos_no_revientan():
    assert cxc.anomalias_en_pagos([])["total_hallazgos"] == 0
    assert cxc.anomalias_en_pagos(None)["revisados"] == 0
    # Una fila con basura se saltea, no tumba la revisión de las demás.
    r = cxc.anomalias_en_pagos([{"monto": "no-es-un-numero"},
                                {"referencia": "P-1", "id_deudor": "A",
                                 "monto": 1.0, "fecha": "2026-08-01"}])
    assert r["revisados"] == 1


# --- HTTP: los cálculos sobre la cartera REAL del cliente --------------------
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """La app real con una cartera y unas gestiones mínimas."""
    pytest.importorskip("fastapi")
    import importlib
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    os.makedirs(tmp_path / "outputs", exist_ok=True)
    os.makedirs(tmp_path / "data", exist_ok=True)
    with open(tmp_path / "outputs" / "kobra_scored.csv", "w", encoding="utf-8") as f:
        f.write("id_deudor,segmento,monto_deuda,dias_mora,tramo_mora,cuotas_atrasadas,"
                "probpago,segmento_propension,valor_esperado_recupero\n"
                "KB-1,Retail,100000.0,15,1-30,1,0.7,Alta,70000.0\n"
                "KB-2,Pyme,400000.0,200,180+,6,0.2,Baja,80000.0\n")
    with open(tmp_path / "data" / "kobra_gestiones.csv", "w", encoding="utf-8") as f:
        f.write("mes,monto_gestionado,recupero\n"
                "2026-07,1000000.0,800000.0\n"
                "2026-06,1000000.0,700000.0\n")

    from kobra import rutas as krutas
    importlib.reload(krutas)
    from kobra import autenticacion as kauth
    importlib.reload(kauth)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    c = TestClient(api.app)
    kauth.establecer_password("admin", "clave-segura-123")
    tok = c.post("/api/auth/login", json={"password": "clave-segura-123"}).json()["token"]
    yield c, {"Authorization": f"Bearer {tok}"}
    monkeypatch.undo()
    importlib.reload(krutas)
    importlib.reload(kauth)
    importlib.reload(api)


def test_http_antiguedad_sale_de_la_cartera_cargada(cliente):
    c, h = cliente
    r = c.get("/api/cxc/antiguedad", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["antiguedad"]["total_uyu"] == 500000.0
    assert d["concentracion"]["top"][0]["id_deudor"] == "KB-2"


def test_http_dso_usa_el_saldo_de_la_cartera_si_no_se_lo_pasan(cliente):
    c, h = cliente
    r = c.post("/api/cxc/dso", headers=h,
               json={"ventas_credito": 1000000.0, "dias_periodo": 30})
    assert r.status_code == 200
    # saldo = 500.000 de la cartera cargada, sin que el usuario lo escriba.
    assert r.json()["saldo_cxc"] == 500000.0
    assert r.json()["dso"] == 15.0


def test_http_efectividad_toma_el_ultimo_mes_por_default(cliente):
    c, h = cliente
    d = c.get("/api/cxc/efectividad", headers=h).json()
    assert d["mes"] == "2026-07"
    assert d["efectividad"] == 0.8


def test_http_efectividad_compara_contra_otro_mes(cliente):
    c, h = cliente
    d = c.get("/api/cxc/efectividad?mes=2026-07&comparar=2026-06", headers=h).json()
    assert d["comparacion"]["variacion_pp"] == 10.0


def test_http_conciliar_no_elige_cuando_hay_ambiguedad(cliente):
    c, h = cliente
    d = c.post("/api/cxc/conciliar", headers=h, json={
        "monto": 100.0,
        "facturas": [{"id": "A", "monto": 100.0}, {"id": "B", "monto": 100.0}],
    }).json()
    assert d["ambiguo"] is True and d["match"] is None


@pytest.mark.parametrize("metodo,ruta", [
    ("get", "/api/cxc/antiguedad"), ("post", "/api/cxc/dso"),
    ("get", "/api/cxc/efectividad"), ("post", "/api/cxc/conciliar"),
    ("get", "/api/cxc/anomalias"),
])
def test_todos_los_endpoints_de_cxc_exigen_sesion(cliente, metodo, ruta):
    """Son datos financieros del cliente: ninguno puede quedar público."""
    c, _ = cliente
    r = c.request(metodo, ruta, json={} if metodo == "post" else None)
    assert r.status_code == 401, f"{ruta} quedó accesible sin sesión"
