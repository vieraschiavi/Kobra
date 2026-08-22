# © 2026 Martín Viera. Todos los derechos reservados.

"""Tests de /api/cartera/importar: subir la cartera real (CSV/Excel) debe
reemplazar los datos de demo en TODO el dashboard, no solo simular una
negociación aparte. Bug real reportado: el cliente subía un CSV/Excel y
seguía viendo datos de demo — nunca existía este camino completo.

Usa un tenant aislado (como test_api_tenant_alta_y_aislamiento) para la
subida destructiva, así nunca toca outputs/kobra_scored.csv del repo."""
import importlib
import io
import os
import shutil
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import cartera_manual as kcartera
    importlib.reload(kcartera)  # limpia _MODELO_PRIOR cacheado de otro test
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    return api, TestClient(api.app)


def _h_admin(cliente, empresa=None):
    # La contraseña es POR EMPRESA desde que se cerró la fuga cross-tenant
    # (ver tests/test_aislamiento_tenant.py). Estos tests no prueban el login,
    # así que se le crea a la empresa la credencial que le corresponde.
    from kobra import autenticacion as kauth
    cuerpo = {"password": "AdminTest123!"}
    if empresa:
        cuerpo["empresa"] = empresa
        kauth.establecer_password("admin", "AdminTest123!", empresa=empresa)
    r = cliente.post("/api/auth/login", json=cuerpo)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _csv_cartera_real():
    df = pd.DataFrame({
        "nombre": ["Juan Pérez", "María Silva", "Carlos Notario"],
        "telefono": ["099111222", "098333444", "097555666"],
        "deuda": [50000, 120000, 8000],
        "dias_mora": [45, 10, 200],
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _xlsx_columnas_raras():
    """Excel estilo export de ProbPago/ERP: nombres de columna que NO son los
    nuestros (camelCase, otro idioma, moneda formateada). Debe adaptarse solo."""
    df = pd.DataFrame({
        "IdCliente": ["C1", "C2", "C3"],
        "Nombre Cliente": ["Ana", "Beto", "Caro"],
        "Celular": ["099111", "098222", "097333"],
        "MontoDeuda": ["$ 1.234.567", "50.000", "8.900,50"],
        "DiasAtraso": [45, 10, 200],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_origen_default_es_demo(cliente):
    api, c = cliente
    h = _h_admin(c)
    origen = c.get("/api/cartera/origen", headers=h).json()
    assert origen["tipo"] == "demo" and origen["modo"] == "demo"
    assert origen["hay_real"] is False  # sin cartera real subida, el botón está deshabilitado


def test_mapea_columnas_parecidas():
    """El corazón del pedido: adaptarse a nombres de columna similares."""
    from kobra import cartera_manual as kc
    m = kc.mapear_columnas(["IdCliente", "Nombre Cliente", "Celular",
                            "MontoDeuda", "DiasAtraso"])
    assert m["MontoDeuda"] == "monto_deuda"
    assert m["Nombre Cliente"] == "nombre"
    assert m["Celular"] == "telefono"
    assert m["DiasAtraso"] == "dias_mora"
    # Otros idiomas + sinónimos de deuda
    for col in ["Saldo Vencido", "Dívida Total", "Total Debt", "Importe", "saldo"]:
        assert kc.mapear_columnas([col]).get(col) == "monto_deuda", col


def test_elige_columna_de_deuda_entre_varias_de_plata():
    """Desambiguación por dataset: con varias columnas de plata, elegir la de
    DEUDA — 'deuda/adeudo/vencido/saldo' le ganan a 'monto/importe' genérico, y
    'pago/cobro' (lo ya cobrado) es la última opción."""
    from kobra import cartera_manual as kc

    def deuda(cols):
        m = kc.mapear_columnas(cols)
        return next((c for c, f in m.items() if f == "monto_deuda"), None)

    assert deuda(["Cliente", "Último Pago", "Deuda Total", "Capital"]) == "Deuda Total"
    assert deuda(["Cliente", "Importe", "Cobro Mensual"]) == "Importe"
    assert deuda(["Nombre", "Saldo Vencido", "Monto Pagado"]) == "Saldo Vencido"
    assert deuda(["nombre", "Capital"]) == "Capital"           # capital como deuda
    assert deuda(["cliente", "Monto Cobrado"]) == "Monto Cobrado"  # única plata → se usa
    assert deuda(["nombre", "telefono", "dias_mora"]) is None  # sin plata → None


def test_parseo_moneda_formateada():
    from kobra import cartera_manual as kc
    assert kc._a_numero("$ 1.234.567,89") == 1234567.89   # es: miles '.', dec ','
    assert kc._a_numero("1,234,567.89") == 1234567.89     # en: miles ',', dec '.'
    assert kc._a_numero("R$ 5.000") == 5000.0
    assert kc._a_numero("45%") == 0.45
    assert pd.isna(kc._a_numero(""))


def test_importar_xlsx_con_columnas_raras(cliente):
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        r = c.post("/api/tenant/alta", json={"empresa": "test-cols-raras"}, headers=h_principal)
        assert r.status_code == 200, r.text
        h = _h_admin(c, empresa="test-cols-raras")
        r = c.post("/api/cartera/importar", headers=h, files={"archivo": (
            "ProbPago_export.xlsx", _xlsx_columnas_raras(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deudores"] == 3
        # El monto formateado '$ 1.234.567' se parseó bien.
        assert abs(d["cartera_total_uyu"] - (1234567 + 50000 + 8900.5)) < 1
        assert d["columnas_detectadas"]["MontoDeuda"] == "monto_deuda"
        kpis = c.get("/api/kpis", headers=h).json()
        assert kpis["deudores"] == 3
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-cols-raras"),
                      ignore_errors=True)


def test_importar_csv_reemplaza_dashboard_completo(cliente):
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        r = c.post("/api/tenant/alta", json={"empresa": "test-importar-cartera"},
                  headers=h_principal)
        assert r.status_code == 200, r.text
        h = _h_admin(c, empresa="test-importar-cartera")

        kpis_antes = c.get("/api/kpis", headers=h).json()
        assert kpis_antes["deudores"] == 2000  # la demo del tenant (muestra)

        r = c.post("/api/cartera/importar", headers=h,
                  files={"archivo": ("mi_cartera.csv", _csv_cartera_real(), "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deudores"] == 3

        # El dashboard entero (KPIs) ahora refleja la cartera real, no la demo.
        kpis_despues = c.get("/api/kpis", headers=h).json()
        assert kpis_despues["deudores"] == 3
        assert abs(kpis_despues["cartera_uyu"] - 178_000) < 1

        # Y la cartera priorizada trae los 3 deudores reales, con estrategia.
        cartera = c.get("/api/cartera", headers=h).json()
        assert len(cartera["filas"]) == 3
        fila = cartera["filas"][0]
        assert "estrategia" in fila and "probpago" in fila

        # Origen ahora marca "real", con fecha y nombre de archivo — nunca se
        # disfraza de demo. Y el tenant "principal" no se tocó.
        origen = c.get("/api/cartera/origen", headers=h).json()
        assert origen["tipo"] == "real" and origen["modo"] == "real"
        assert origen["hay_real"] is True
        assert origen["archivo"] == "mi_cartera.csv"
        assert origen["deudores"] == 3
        assert "cargado_en" in origen
        assert c.get("/api/cartera/origen", headers=h_principal).json()["tipo"] == "demo"

        # Botón demo ON: volver a la demo NO pierde la cartera real (se puede
        # re-activar), y el dashboard entero vuelve a los datos sintéticos.
        c.post("/api/cartera/modo", json={"modo": "demo"}, headers=h)
        assert c.get("/api/kpis", headers=h).json()["deudores"] == 2000
        origen_demo = c.get("/api/cartera/origen", headers=h).json()
        assert origen_demo["modo"] == "demo" and origen_demo["hay_real"] is True

        # Botón demo OFF: re-activar la cartera real que ya estaba subida.
        c.post("/api/cartera/modo", json={"modo": "real"}, headers=h)
        assert c.get("/api/kpis", headers=h).json()["deudores"] == 3
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-importar-cartera"),
                      ignore_errors=True)


def test_activar_modo_real_sin_cartera_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    # No se puede activar 'real' si nunca se subió una cartera real.
    r = c.post("/api/cartera/modo", json={"modo": "real"}, headers=h)
    assert r.status_code == 400


def test_modo_invalido_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/cartera/modo", json={"modo": "otro"}, headers=h)
    assert r.status_code == 400


def test_importar_csv_vacio_de_deuda_da_422(cliente):
    api, c = cliente
    h = _h_admin(c)
    buf = io.StringIO()
    pd.DataFrame({"nombre": ["Sin Deuda"]}).to_csv(buf, index=False)
    r = c.post("/api/cartera/importar", headers=h,
              files={"archivo": ("vacio.csv", buf.getvalue().encode(), "text/csv")})
    assert r.status_code == 422


def test_importar_extension_no_soportada_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/cartera/importar", headers=h,
              files={"archivo": ("cartera.txt", b"algo", "text/plain")})
    assert r.status_code == 400


def test_importar_requiere_admin(cliente):
    api, c = cliente
    from kobra import autenticacion as kauth
    kauth.establecer_password("gestor", "GestorTest123!")
    r = c.post("/api/auth/login", json={"password": "GestorTest123!"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = c.post("/api/cartera/importar", headers=h,
               files={"archivo": ("x.csv", _csv_cartera_real(), "text/csv")})
    assert r2.status_code == 403


def test_importar_sql_desde_base_reemplaza_dashboard(cliente, tmp_path):
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        r = c.post("/api/tenant/alta", json={"empresa": "test-importar-sql"},
                  headers=h_principal)
        assert r.status_code == 200, r.text
        h = _h_admin(c, empresa="test-importar-sql")

        # Base SQLite del "cliente" con su cartera real.
        import sqlalchemy as sa
        db = tmp_path / "cartera_cliente.db"
        eng = sa.create_engine(f"sqlite:///{db}")
        pd.DataFrame({
            "nombre": ["Ana", "Beto", "Caro", "Dani"],
            "telefono": ["0991", "0992", "0993", "0994"],
            "monto_deuda": [10000, 25000, 5000, 40000],
            "dias_mora": [30, 90, 15, 200],
        }).to_sql("cartera", eng, index=False)
        eng.dispose()

        r = c.post("/api/cartera/importar-sql", headers=h, json={
            "conn_url": f"sqlite:///{db}",
            "consulta": "SELECT nombre, telefono, monto_deuda, dias_mora FROM cartera"})
        assert r.status_code == 200, r.text
        assert r.json()["deudores"] == 4

        kpis = c.get("/api/kpis", headers=h).json()
        assert kpis["deudores"] == 4
        origen = c.get("/api/cartera/origen", headers=h).json()
        assert origen["modo"] == "real" and origen["archivo"] == "Base de datos (SQL)"
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-importar-sql"),
                      ignore_errors=True)


def test_importar_sql_rechaza_consulta_de_escritura(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/cartera/importar-sql", headers=h, json={
        "conn_url": "sqlite:///x.db",
        "consulta": "DELETE FROM cartera"})
    assert r.status_code == 422  # solo lectura (SELECT/WITH)


def test_importar_sql_requiere_admin(cliente):
    api, c = cliente
    from kobra import autenticacion as kauth
    kauth.establecer_password("gestor", "GestorTest123!")
    r = c.post("/api/auth/login", json={"password": "GestorTest123!"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = c.post("/api/cartera/importar-sql", headers=h,
               json={"conn_url": "sqlite:///x.db", "consulta": "SELECT 1"})
    assert r2.status_code == 403


def test_filtros_dinamicos_del_dataset(cliente):
    """Los filtros del dashboard salen del DATASET activo (no hardcodeados):
    valores categóricos presentes + rangos de monto/días de mora + modo."""
    api, c = cliente
    h = _h_admin(c)
    f = c.get("/api/cartera/filtros", headers=h).json()
    assert f["modo"] == "demo"
    assert f["segmentos"] and isinstance(f["segmentos"], list)
    assert f["monto"]["min"] <= f["monto"]["max"]
    assert f["dias_mora"]["min"] <= f["dias_mora"]["max"]
    # Filtro por rango de monto y de días de mora achica el total, sin romper.
    total = c.get("/api/cartera", headers=h).json()["total"]
    lo, hi = f["monto"]["min"], f["monto"]["max"]
    medio = (lo + hi) // 2
    parcial = c.get(f"/api/cartera?monto_min={medio}", headers=h).json()["total"]
    assert 0 <= parcial <= total
    d = f["dias_mora"]
    r = c.get(f"/api/cartera?dias_min={d['min']}&dias_max={d['max']}", headers=h)
    assert r.status_code == 200


def test_cartera_no_rompe_con_esquema_sin_prioridad(cliente):
    """Regresión del 'Error 500': una cartera real cuyo scoring no trae
    'prioridad' NO debe tirar 500 — ordena por otro criterio."""
    api, c = cliente

    from webapp.backend import api as apimod
    df = apimod._scored("principal").drop(columns=["prioridad"])
    assert not apimod._ordenar_cartera(df).empty  # no lanza KeyError


def test_originacion_usa_el_mismo_dataset_del_dashboard(cliente):
    """Una sola carga: la originación se deriva del MISMO dataset activo (el que
    se sube en Configuración), no de una carga aparte. Demo → sintético; real →
    derivado de la cartera real cargada."""
    api, c = cliente
    h_principal = _h_admin(c)
    try:
        c.post("/api/tenant/alta", json={"empresa": "test-orig"}, headers=h_principal)
        h = _h_admin(c, empresa="test-orig")

        # Demo por default → cola sintética.
        cola = c.get("/api/originacion/cola", headers=h).json()
        assert cola["es_real"] is False and cola["solicitudes"]
        assert "sin_datos_reales" not in cola  # ya no existe ese estado

        # Al cargar la cartera real (única carga), la originación pasa a real
        # SIN una importación adicional para esta pestaña.
        c.post("/api/cartera/importar", headers=h,
               files={"archivo": ("c.csv", _csv_cartera_real(), "text/csv")})
        cola = c.get("/api/originacion/cola", headers=h).json()
        assert cola["es_real"] is True and cola["solicitudes"]
        # Ya no hay endpoint de importación propio de originación (404/405).
        assert c.post("/api/originacion/importar", headers=h,
                      files={"archivo": ("x.csv", b"a,b\n1,2", "text/csv")}).status_code in (404, 405)
    finally:
        shutil.rmtree(os.path.join(ROOT, "data", "tenants", "test-orig"),
                      ignore_errors=True)


# ---------------------------------------------------------------------------
# Un ProbPago hecho de supuestos tiene que decir que lo es
# ---------------------------------------------------------------------------
# `cargar_manual` exige UNA sola columna: el monto. Todo lo demás sale de
# `DEFAULTS` — score de buró 600, ingreso 45.000, contactabilidad 0,7… catorce
# supuestos. El modelo los toma como si fueran datos y devuelve un número con
# dos decimales, que se muestra en la misma pantalla y con la misma cara de
# certeza que uno calculado sobre la cartera completa de un ERP.
#
# No se puede resolver inventando mejores defaults: si el dato no está, no
# está. Lo que sí se puede es decirlo, y que llegue hasta el brief que mira el
# gestor antes de levantar el teléfono.
def test_una_cartera_de_una_sola_columna_se_marca_como_estimada():
    from kobra import cartera_manual as cm
    df = cm.cargar_manual([{"monto_deuda": 50000}])
    assert df["features_provistas"][0] == 0
    assert len(df["supuestos"][0]) == len(cm.DEFAULTS), (
        "no queda registro de cuántas features se inventaron")


def test_una_cartera_completa_se_marca_como_completa():
    """La contracara: el cliente que sí carga sus datos no puede quedar
    marcado como si hubiera subido tres columnas."""
    from kobra import cartera_manual as cm
    completo = {"monto_deuda": 50000, **cm.DEFAULTS}
    df = cm.cargar_manual([completo])
    assert df["features_provistas"][0] == len(cm.DEFAULTS)
    assert df["supuestos"][0] == []


def test_la_etiqueta_de_calidad_escala_con_los_datos():
    from kobra import cartera_manual as cm
    total = len(cm.DEFAULTS)
    assert cm._calidad_datos(0) == "estimada"
    assert cm._calidad_datos(total) == "completa"
    assert cm._calidad_datos(total // 2) == "parcial"


def test_la_calidad_llega_al_brief_que_mira_el_gestor():
    """Es el punto de todo esto: el que decide a quién llamar tiene que ver
    sobre qué está decidiendo, no solo el número."""
    from kobra import cartera_manual as cm
    df = cm.puntuar(cm.modelo_prior(),
                    cm.cargar_manual([{"monto_deuda": 50000,
                                       "nombre": "Ana", "telefono": "099"}]))
    from kobra import negociador
    fila = negociador.recomendar(df).iloc[0]
    brief = cm.brief_desde_fila(fila)
    assert brief["calidad_datos"] == "estimada"
    assert brief["features_provistas"] == 0
    # Y el resto del brief sigue completo: la etiqueta se suma, no reemplaza.
    for campo in ("id_deudor", "monto_deuda", "probpago", "estrategia",
                  "descuento_recomendado", "plan_cuotas"):
        assert campo in brief
