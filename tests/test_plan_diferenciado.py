"""Lo que el cliente pagó tiene que ser lo que el cliente recibe.

El agujero que cierran estos tests: la licencia viajaba firmada con `plan`,
`cupo_mensual` y `features`, pero la app instalada leía UNA sola cosa — la
fecha de vencimiento. O sea que un cliente de Básico (US$99, "300 gestiones"
en la landing) y uno de Pro (US$349, "1.000 gestiones") recibían exactamente
el mismo producto; lo único distinto entre los dos era cuándo se les vencía.
Se estaba cobrando 3,5× por una diferencia que no existía en el software.

Dos reglas que estos tests fijan y que son tan importantes como el límite:

  1. **Un cupo agotado nunca deja a una empresa afuera de sus propios datos.**
     Se corta la gestión nueva, no la cartera, ni los informes, ni el export.
  2. **Correr sin licencia no inventa un límite.** El repo, los tests y el
     modo hosted (multi-tenant) siguen sin tope, como siempre.
"""
import importlib
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-para-firmar-licencias"


def _entorno(tmp_path, monkeypatch, plan=None, owner=False, sub="cliente-1",
             cupo=None, features=None, dias=None):
    """Deja el proceso como si fuera una copia instalada con esa licencia."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)
    if owner:
        monkeypatch.setenv("KOBRA_OWNER", "1")
    else:
        monkeypatch.delenv("KOBRA_OWNER", raising=False)

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import rutas as krutas
    importlib.reload(krutas)
    from kobra import edicion as kedicion
    importlib.reload(kedicion)
    from kobra import plan as kplan
    importlib.reload(kplan)

    if plan:
        from backend_venta import licencias as klicencias
        token = klicencias.emitir_licencia(sub, plan, cupo_mensual=cupo,
                                           features=features, dias=dias,
                                           secreto=SECRETO)
        kconfig.guardar_extra("LICENCIA_TOKEN", token)
    return kplan


def _api(tmp_path, monkeypatch):
    """La API como la ve un cliente con el programa instalado.

    A diferencia de `_entorno`, acá NO se muda `DIR_DATOS`: los endpoints
    tienen que encontrar la cartera de demo del repo para poder comprobar que
    el cliente sigue llegando a sus datos con el cupo agotado. Lo único que se
    desvía a tmp es el contador de uso, que sí escribe.
    """
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("KOBRA_DATA_DIR", raising=False)
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.delenv("KOBRA_OWNER", raising=False)

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import rutas as krutas
    importlib.reload(krutas)
    from kobra import plan as kplan
    importlib.reload(kplan)
    monkeypatch.setattr(kplan, "_ruta_uso", lambda: str(tmp_path / "uso_plan.json"))

    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    return kplan, TestClient(api.app)


# --- Sin licencia y owner: nadie inventa un tope ----------------------------
def test_sin_licencia_no_hay_tope(tmp_path, monkeypatch):
    """Correr desde el repo, los tests y el modo hosted no tienen licencia:
    aplicarles un cupo rompería el desarrollo y el multi-tenant."""
    kplan = _entorno(tmp_path, monkeypatch)
    st = kplan.estado()
    assert st["ilimitado"] is True
    assert st["cupo"] is None
    assert kplan.permite("cualquier_cosa") is True
    kplan.exigir("white_label")            # no levanta
    for _ in range(50):
        kplan.registrar_gestion()
    assert kplan.estado()["bloqueado"] is False


def test_el_dueno_no_tiene_cupo(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="basico", owner=True)
    assert kplan.estado()["ilimitado"] is True
    assert kplan.permite("white_label") is True
    for _ in range(400):                    # muy por encima de las 300 de Básico
        kplan.registrar_gestion()
    assert kplan.estado()["bloqueado"] is False


# --- Básico ≠ Pro: la diferencia que se vende existe en el software ---------
def test_basico_y_pro_no_son_el_mismo_producto(tmp_path, monkeypatch):
    """El test que resume todo el archivo.

    (Las lecturas se toman ANTES de armar el otro entorno: `kobra.plan` es un
    módulo, y recargarlo devuelve el mismo objeto — comparar dos "instancias"
    al final leería las dos veces la última licencia activada.)"""
    kplan = _entorno(tmp_path / "b", monkeypatch, plan="basico")
    basico = {**kplan.estado(), "excedente_ok": kplan.admite_excedente()}

    kplan = _entorno(tmp_path / "p", monkeypatch, plan="pro", sub="cliente-2")
    pro = {**kplan.estado(), "excedente_ok": kplan.admite_excedente()}

    assert basico["cupo"] == 300
    assert pro["cupo"] == 1000
    assert basico["cupo"] != pro["cupo"]
    # Y no es solo el número: Pro no se corta al llegar al tope, Básico sí.
    assert pro["excedente_ok"] is True
    assert basico["excedente_ok"] is False


def test_ningun_plan_caro_da_menos_que_uno_barato():
    """Regla de coherencia comercial que el cupo, mientras no se aplicaba,
    podía romper sin que nadie se enterara: si un plan cuesta más, no puede
    incluir menos gestiones que uno más barato. Con el cupo ya aplicado eso
    sería un cliente pagando 7× por un producto peor."""
    from backend_venta import licencias as klicencias
    cobrables = [(p, c) for p, c in klicencias.PLANES.items()
                 if c["precio"]]                      # trial y enterprise aparte
    infinito = float("inf")
    for plan_a, cfg_a in cobrables:
        for plan_b, cfg_b in cobrables:
            if cfg_a["precio"] <= cfg_b["precio"]:
                continue
            cupo_a = cfg_a["cupo_mensual"] if cfg_a["cupo_mensual"] is not None else infinito
            cupo_b = cfg_b["cupo_mensual"] if cfg_b["cupo_mensual"] is not None else infinito
            assert cupo_a >= cupo_b, (
                f"{plan_a} (US${cfg_a['precio']}) incluye {cupo_a} gestiones y "
                f"{plan_b} (US${cfg_b['precio']}) incluye {cupo_b}")


def test_enterprise_no_tiene_tope(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="enterprise")
    assert kplan.estado()["ilimitado"] is True
    assert kplan.permite("sso") is True
    assert kplan.permite("white_label") is True


def test_los_planes_de_abajo_no_traen_los_extras_de_enterprise(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="basico")
    assert kplan.permite("sso") is False
    assert kplan.permite("white_label") is False
    assert kplan.permite("copiloto") is True        # esto sí lo pagó


# --- El cupo se cuenta, avisa y corta ---------------------------------------
def test_cuenta_las_gestiones_del_mes(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="basico")
    assert kplan.consumo() == 0
    for _ in range(5):
        kplan.registrar_gestion()
    st = kplan.estado()
    assert st["usado"] == 5
    assert st["restante"] == 295


def test_avisa_al_80_por_ciento_sin_bloquear(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="trial", cupo=10)
    for _ in range(7):
        kplan.registrar_gestion()
    assert kplan.estado()["avisar"] is False
    kplan.registrar_gestion()                       # 8 de 10 = 80 %
    st = kplan.estado()
    assert st["avisar"] is True
    assert st["bloqueado"] is False


def test_al_agotarse_corta_la_gestion_siguiente(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="basico", cupo=3)
    for _ in range(3):
        kplan.registrar_gestion()
    with pytest.raises(kplan.CupoAgotado) as e:
        kplan.registrar_gestion()
    assert "3 gestiones" in str(e.value)
    assert "mvkobranzaia.com" in str(e.value)
    # Y no le sumó una gestión que además le negó.
    assert kplan.consumo() == 3


def test_verificar_cupo_no_consume(tmp_path, monkeypatch):
    """Se chequea antes de trabajar y se cobra después: un análisis que
    termina en error no le puede comer el cupo al cliente."""
    kplan = _entorno(tmp_path, monkeypatch, plan="basico", cupo=2)
    kplan.verificar_cupo()
    kplan.verificar_cupo()
    assert kplan.consumo() == 0
    kplan.registrar_gestion()
    kplan.registrar_gestion()
    with pytest.raises(kplan.CupoAgotado):
        kplan.verificar_cupo()


def test_pro_se_pasa_del_cupo_y_no_se_le_corta(tmp_path, monkeypatch):
    """Pro incluye "excedente": paga lo que se pase, no se le apaga el
    producto en la mitad del mes."""
    kplan = _entorno(tmp_path, monkeypatch, plan="pro", cupo=2)
    for _ in range(5):
        kplan.registrar_gestion()               # ninguna levanta
    st = kplan.estado()
    assert st["usado"] == 5
    assert st["excedente"] == 3
    assert st["bloqueado"] is False


# --- Contabilidad honesta ---------------------------------------------------
def test_el_mes_siguiente_arranca_limpio(tmp_path, monkeypatch):
    kplan = _entorno(tmp_path, monkeypatch, plan="basico", cupo=2)
    kplan.registrar_gestion()
    kplan.registrar_gestion()
    with pytest.raises(kplan.CupoAgotado):
        kplan.registrar_gestion()

    otro_mes = time.strftime("%Y-%m", time.localtime(time.time() + 40 * 86400))
    monkeypatch.setattr(kplan, "mes_actual", lambda: otro_mes)
    assert kplan.consumo() == 0
    kplan.registrar_gestion()                    # no levanta


def test_una_licencia_nueva_no_hereda_lo_gastado(tmp_path, monkeypatch):
    """Renovar o mejorar el plan a mitad de mes tiene que dar el cupo nuevo
    entero, no el resto del anterior."""
    kplan = _entorno(tmp_path, monkeypatch, plan="basico", cupo=2, sub="empresa-A")
    kplan.registrar_gestion()
    kplan.registrar_gestion()

    from backend_venta import licencias as klicencias
    from kobra import config as kconfig
    kconfig.guardar_extra("LICENCIA_TOKEN",
                          klicencias.emitir_licencia("empresa-B", "pro", secreto=SECRETO))
    assert kplan.consumo() == 0
    assert kplan.estado()["cupo"] == 1000


def test_el_contador_queda_en_un_json_valido(tmp_path, monkeypatch):
    """Escritura atómica: un corte a mitad no puede dejar el archivo roto —
    se leería como cero y regalaría el cupo del mes."""
    kplan = _entorno(tmp_path, monkeypatch, plan="basico")
    kplan.registrar_gestion()
    with open(kplan._ruta_uso(), encoding="utf-8") as f:
        datos = json.load(f)
    assert datos["cliente-1"][kplan.mes_actual()] == 1
    assert not os.path.exists(kplan._ruta_uso() + ".tmp")


def test_una_licencia_vencida_no_deja_el_cupo_abierto(tmp_path, monkeypatch):
    """Con la licencia vencida no hay claims: el estado no puede pasar a
    'ilimitado' por la puerta de atrás. El vencimiento lo aplica la pantalla
    de activación (kobra/edicion.py), pero acá no se puede blanquear el cupo."""
    kplan = _entorno(tmp_path, monkeypatch, plan="basico", dias=-1)
    assert kplan.claims() is None


# --- Las dos vías de arranque aplican el mismo plan -------------------------
def test_el_dashboard_streamlit_tambien_aplica_el_cupo():
    """Este paquete se abre por DOS caminos (app React y dashboard Streamlit).
    Si el cupo se controlara solo en uno, el cliente elige el otro y tiene
    gestiones infinitas — es exactamente el agujero que ya había pasado con el
    vencimiento de la Demo (ver kobra/edicion.py). Se comprueba en el fuente
    porque arrancar Streamlit dentro de un test no es viable."""
    with open(os.path.join(ROOT, "app", "app.py"), encoding="utf-8") as f:
        dash = f.read()
    assert "from kobra import plan as kplan" in dash
    assert "kplan.verificar_cupo()" in dash, "el dashboard no chequea el cupo"
    assert "kplan.registrar_gestion()" in dash, "el dashboard no descuenta la gestión"
    assert "kplan.exigir(" in dash, "el dashboard no mira las features del plan"

    with open(os.path.join(ROOT, "webapp", "backend", "api.py"), encoding="utf-8") as f:
        web = f.read()
    for pieza in ("kplan.exigir(", "kplan.verificar_cupo()", "kplan.registrar_gestion()"):
        assert pieza in web, f"la app React no usa {pieza}"


# --- Nadie se queda sin sus propios datos -----------------------------------
def test_un_cupo_agotado_no_es_un_secuestro_de_datos(tmp_path, monkeypatch):
    """La regla que hace que esto sea un límite comercial y no una extorsión:
    con el cupo en cero el cliente sigue entrando a su cartera, sus KPIs, sus
    informes y sus exportaciones. Solo se le corta GENERAR gestiones nuevas."""
    kplan, cliente = _api(tmp_path, monkeypatch)
    from backend_venta import licencias as klicencias
    token = klicencias.emitir_licencia("empresa-X", "basico", cupo_mensual=1,
                                       secreto=SECRETO)
    r = cliente.post("/api/licencia/activar", json={"token": token})
    assert r.status_code == 200
    cab = {"Authorization": f"Bearer {r.json()['token']}"}

    kplan.registrar_gestion()                   # consume el único cupo
    assert cliente.get("/api/plan", headers=cab).json()["bloqueado"] is True

    # Sus datos siguen ahí, todos.
    for ruta in ("/api/kpis", "/api/cartera", "/api/agenda",
                 "/api/cartera/export.csv", "/api/graficos/resumen"):
        assert cliente.get(ruta, headers=cab).status_code == 200, ruta

    # Lo único que se corta: generar una gestión nueva. Y con 402, que es
    # "pagá para seguir", no 403 "no tenés permiso".
    r = cliente.post("/api/gestor-ia/demo", json={"canal": "WhatsApp"}, headers=cab)
    assert r.status_code == 402
    d = r.json()
    assert d["motivo"] == "cupo_agotado"
    assert d["plan"]["cupo"] == 1


def test_la_api_niega_lo_que_el_plan_no_incluye(tmp_path, monkeypatch):
    _, cliente = _api(tmp_path, monkeypatch)
    from backend_venta import licencias as klicencias

    # Un plan sin ERP (se emite explícito: hoy todos los planes lo traen, y
    # el día que se venda uno sin integración el gateo ya está puesto).
    token = klicencias.emitir_licencia("empresa-Y", "basico",
                                       features=["voz", "whatsapp", "copiloto"],
                                       secreto=SECRETO)
    r = cliente.post("/api/licencia/activar", json={"token": token})
    cab = {"Authorization": f"Bearer {r.json()['token']}"}

    r = cliente.post("/api/integracion/cartera",
                     json={"contactos": [{"nombre": "X", "deuda": 100}]}, headers=cab)
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"
    assert "ERP" in r.json()["detail"]

    # Y lo que sí incluye, sigue funcionando.
    assert cliente.post("/api/gestor-ia/demo", json={"canal": "WhatsApp"},
                        headers=cab).status_code == 200
