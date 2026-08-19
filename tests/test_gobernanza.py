# © 2026 Martín Viera. Todos los derechos reservados.

"""Gobernanza de datos: clasificación, enmascarado, calidad y linaje.

Lo que se prueba acá es que el módulo cumpla las dos promesas que se le hacen
a una empresa antes de dejarlo entrar a su cartera:

  * **que proteja de verdad** — que un rol que no debe ver un dato personal no
    lo vea, y que el seudónimo no se pueda deshacer;
  * **que el producto siga sirviendo** — un enmascarado que rompe la operación
    se desactiva el primer día, y entonces no protege nada. Por eso hay tantos
    tests de "el gestor sigue pudiendo trabajar" como de "el gestor no ve".

Todos los datos son sintéticos y armados en el test (`CLAUDE.md`: nunca datos
reales de clientes, ni siquiera para probar el enmascarado de datos reales).
"""
import importlib
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def kgob(tmp_path, monkeypatch):
    """El módulo con una instalación limpia: sal y log propios del test."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    os.makedirs(tmp_path / "datos" / "data", exist_ok=True)
    monkeypatch.setenv("KOBRA_AUDIT_LOG", str(tmp_path / "datos" / "auditoria.log"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import auditoria as kaud
    importlib.reload(kaud)
    from kobra import gobernanza as g
    importlib.reload(g)
    return g


@pytest.fixture()
def cartera():
    """Cartera sintética con la forma real del dataset de Kobra."""
    return pd.DataFrame({
        "id_deudor": [f"KB-{100000 + i}" for i in range(6)],
        "segmento": ["Pyme", "Individuo", "Pyme", "Corp", "Individuo", "Pyme"],
        "departamento": ["Cerro Largo", "Montevideo", "Salto", "Canelones",
                         "Rivera", "Maldonado"],
        "monto_deuda": [231530.0, 45000.0, 120000.0, 890000.0, 15000.0, 60000.0],
        "dias_mora": [13, 45, 0, 120, 7, 200],
        "cuotas_atrasadas": [1, 2, 0, 4, 1, 6],
        "score_buro": [576, 620, 780, 410, 690, 350],
        "ingreso_estimado": [37300.0, 52000.0, 91000.0, 28000.0, 64000.0, 41000.0],
        "contactabilidad": [0.749, 0.5, 0.9, 0.2, 0.66, 0.31],
        "canal_preferido": ["Llamada", "WhatsApp", "Llamada", "Email",
                            "WhatsApp", "Llamada"],
        "tramo_mora": ["1-30", "31-60", "0", "91-180", "1-30", "180+"],
    })


# ---------------------------------------------------------------------------
# Clasificación
# ---------------------------------------------------------------------------
def test_el_score_de_buro_es_sensible_aunque_el_nombre_no_lo_diga(kgob):
    """El caso que justifica declarar el catálogo a mano en vez de adivinar:
    `score_buro` no dice 'personal' por ningún lado y es dato crediticio."""
    assert kgob.clasificar("score_buro") == kgob.SENSIBLE
    assert kgob.clasificar("ingreso_estimado") == kgob.SENSIBLE


def test_el_departamento_es_personal_por_cuasi_identificador(kgob):
    """Sola no identifica; cruzada con monto y mora, sí. Es el error clásico
    de anonimización: proteger el nombre y dejar pasar la geografía."""
    assert kgob.clasificar("departamento") == kgob.PERSONAL


def test_una_columna_desconocida_no_se_asume_publica(kgob):
    """El default de una herramienta de gobernanza tiene que fallar hacia
    proteger de más. Si lo desconocido fuera público, cada cartera que sube un
    cliente con nombres propios se filtraría entera."""
    assert kgob.clasificar("una_columna_que_nadie_declaro") == kgob.INTERNO


@pytest.mark.parametrize("columna", [
    "nombre_titular", "cedula", "email_contacto", "telefono_celular",
    "direccion", "fecha_nacimiento",
])
def test_la_heuristica_agarra_los_campos_personales_tipicos(kgob, columna):
    """Para la cartera que sube un cliente, con columnas que no conocemos."""
    assert kgob.clasificar(columna) in (kgob.PERSONAL, kgob.SENSIBLE)


# ---------------------------------------------------------------------------
# Enmascarado: que proteja
# ---------------------------------------------------------------------------
def test_el_gestor_no_ve_el_identificador_ni_el_ingreso(kgob, cartera):
    visto = kgob.enmascarar(cartera, "gestor")
    assert not set(visto["id_deudor"]) & set(cartera["id_deudor"]), \
        "el gestor está viendo identificadores en claro"
    assert not set(visto["ingreso_estimado"]) & set(cartera["ingreso_estimado"]), \
        "el gestor está viendo ingresos exactos"


def test_el_admin_ve_todo_sin_tocar(kgob, cartera):
    """El admin responde legalmente por la cartera: enmascararle los datos lo
    dejaría sin poder auditar su propia operación."""
    pd.testing.assert_frame_equal(kgob.enmascarar(cartera, "admin"), cartera)


def test_un_rol_desconocido_no_hereda_permisos_de_admin(kgob, cartera):
    """Si un rol nuevo cayera en el default permisivo, agregar un rol sería
    abrir la cartera sin querer."""
    visto = kgob.enmascarar(cartera, "pasante")
    assert not set(visto["id_deudor"]) & set(cartera["id_deudor"])


def test_el_seudonimo_es_estable_pero_no_reversible(kgob, cartera):
    """Estable: sirve para agrupar y contar por deudor. No reversible: no se
    puede volver al identificador sin la sal."""
    a = kgob.enmascarar(cartera, "gestor")
    b = kgob.enmascarar(cartera, "gestor")
    assert list(a["id_deudor"]) == list(b["id_deudor"]), \
        "el seudónimo cambia entre llamadas: no se puede agrupar por deudor"
    assert a["id_deudor"].nunique() == cartera["id_deudor"].nunique(), \
        "el seudónimo colisiona: dos deudores distintos quedan como uno"
    for original, anon in zip(cartera["id_deudor"], a["id_deudor"]):
        assert original not in anon


def test_dos_instalaciones_no_comparten_seudonimos(kgob, cartera, tmp_path,
                                                   monkeypatch):
    """Si la sal fuera global, dos empresas podrían cruzar sus carteras
    seudonimizadas y reconstruir a la persona entre las dos."""
    primero = list(kgob.enmascarar(cartera, "gestor")["id_deudor"])

    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "otra_empresa"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    otro = importlib.reload(kgob)
    segundo = list(otro.enmascarar(cartera, "gestor")["id_deudor"])

    assert primero != segundo, \
        "dos instalaciones dan el mismo seudónimo: son cruzables entre sí"


# ---------------------------------------------------------------------------
# Enmascarado: que el producto siga sirviendo
# ---------------------------------------------------------------------------
def test_el_gestor_conserva_lo_que_necesita_para_cobrar(kgob, cartera):
    """Un enmascarado que le saca la deuda al gestor lo deja sin trabajo, se
    desactiva el primer día, y entonces no protegió nada."""
    visto = kgob.enmascarar(cartera, "gestor")
    for col in ("monto_deuda", "dias_mora", "canal_preferido",
                "contactabilidad", "segmento"):
        assert list(visto[col]) == list(cartera[col]), \
            f"al gestor le enmascararon {col}, que necesita para gestionar"


def test_no_se_pierden_columnas_ni_filas(kgob, cartera):
    """Enmascarar transforma, no borra: una tabla con menos columnas rompe
    todo lo que la consume río abajo."""
    visto = kgob.enmascarar(cartera, "gestor")
    assert list(visto.columns) == list(cartera.columns)
    assert len(visto) == len(cartera)


def test_el_dato_sensible_numerico_queda_en_tramos_utiles(kgob, cartera):
    """Un ingreso se vuelve un rango: se puede seguir analizando la
    distribución sin poder señalar a nadie."""
    visto = kgob.enmascarar(cartera, "gestor")
    tramos = visto["ingreso_estimado"]
    assert all("–" in t for t in tramos), "no quedaron como rango"
    assert tramos.nunique() > 1, \
        "todos los ingresos cayeron en un solo tramo: el dato quedó inservible"


def test_la_interfaz_sabe_que_columnas_estan_enmascaradas(kgob, cartera):
    """Sin esto, el gestor ve `anon:7f3a…` sin explicación y cree que el
    programa está roto."""
    vis = kgob.columnas_visibles("gestor", cartera.columns)
    assert vis["monto_deuda"] is True
    assert vis["id_deudor"] is False
    assert vis["score_buro"] is False


# ---------------------------------------------------------------------------
# Calidad
# ---------------------------------------------------------------------------
def test_una_cartera_sana_pasa_las_reglas(kgob, cartera):
    informe = kgob.evaluar_calidad(cartera)
    assert informe["apto"] is True, [r for r in informe["resultados"]
                                     if r["estado"] == "falla"]
    assert informe["fallas"] == 0


def test_un_identificador_repetido_se_detecta(kgob, cartera):
    """Gestionar dos veces al mismo deudor es una llamada de más a una persona
    real, y con eso se pierde el cliente."""
    rota = cartera.copy()
    rota.loc[1, "id_deudor"] = rota.loc[0, "id_deudor"]
    informe = kgob.evaluar_calidad(rota)
    assert informe["apto"] is False
    fallas = [r["regla"] for r in informe["resultados"] if r["estado"] == "falla"]
    assert any("duplicados" in f for f in fallas), fallas


def test_un_score_fuera_de_rango_se_detecta(kgob, cartera):
    """El score de buró va de 300 a 950: un 9999 es un error de carga que el
    modelo tomaría como un cliente excelente."""
    rota = cartera.copy()
    rota.loc[0, "score_buro"] = 9999
    informe = kgob.evaluar_calidad(rota)
    assert informe["apto"] is False


def test_una_incoherencia_entre_columnas_se_detecta(kgob, cartera):
    """Cada columna por separado es válida; juntas se contradicen. Es lo que
    una validación columna a columna no ve."""
    rota = cartera.copy()
    rota.loc[0, "cuotas_atrasadas"] = 3
    rota.loc[0, "dias_mora"] = 0
    informe = kgob.evaluar_calidad(rota)
    assert informe["apto"] is False
    fallas = [r["regla"] for r in informe["resultados"] if r["estado"] == "falla"]
    assert any("coherente" in f for f in fallas), fallas


def test_un_dato_malo_no_tumba_el_proceso(kgob):
    """Evaluar calidad tiene que poder correr sobre datos rotos — es su razón
    de existir. Si lanzara, no se podría ni mostrar el problema."""
    basura = pd.DataFrame({"id_deudor": [None, None],
                           "monto_deuda": ["no es un número", -5]})
    informe = kgob.evaluar_calidad(basura)
    assert informe["apto"] is False
    assert informe["filas"] == 2


def test_una_columna_ausente_no_cuenta_como_falla(kgob):
    """Una cartera sin `score_buro` no está mal cargada: no tiene esa columna.
    Reportarlo como falla llenaría el informe de ruido."""
    minima = pd.DataFrame({"id_deudor": ["A", "B"], "monto_deuda": [10.0, 20.0]})
    informe = kgob.evaluar_calidad(minima)
    estados = {r["regla"]: r["estado"] for r in informe["resultados"]}
    assert any(e == "no_aplica" for e in estados.values())
    assert informe["apto"] is True


def test_el_informe_puntua_las_seis_dimensiones(kgob, cartera):
    """Las seis dimensiones DAMA son el lenguaje que ya habla un área de datos
    de una empresa; reportar en otro vocabulario obliga a traducir."""
    informe = kgob.evaluar_calidad(cartera)
    assert set(informe["por_dimension"]) <= set(kgob.DIMENSIONES)
    assert informe["por_dimension"], "no se puntuó ninguna dimensión"


# ---------------------------------------------------------------------------
# Linaje
# ---------------------------------------------------------------------------
def test_el_linaje_responde_de_donde_salio_un_numero(kgob):
    """La pregunta que se hace cuando un KPI del dashboard está mal."""
    kgob.registrar_linaje("cartera_limpia", ["cartera_cruda"], "validación", 1000)
    kgob.registrar_linaje("scoring", ["cartera_limpia"], "ProbPago", 1000)
    kgob.registrar_linaje("dashboard_kpis", ["scoring"], "agregación", 12)

    arriba = kgob.aguas_arriba("dashboard_kpis")
    assert "scoring" in arriba
    assert "cartera_limpia" in arriba
    assert "cartera_cruda" in arriba, \
        "el linaje no llega hasta el origen: solo ve un salto"


def test_el_linaje_responde_que_se_rompe_si_cambio_esto(kgob):
    """La pregunta al revés, la que se hace antes de tocar una fuente."""
    kgob.registrar_linaje("cartera_limpia", ["cartera_cruda"], "validación")
    kgob.registrar_linaje("scoring", ["cartera_limpia"], "ProbPago")
    assert kgob.aguas_abajo("cartera_cruda") == ["cartera_limpia"]


def test_un_linaje_circular_no_cuelga_el_programa(kgob):
    """Un linaje mal cargado puede tener ciclos. Recorrerlo sin cortar sería
    recursión infinita, o sea la app colgada en la pantalla de gobernanza."""
    kgob.registrar_linaje("a", ["b"], "x")
    kgob.registrar_linaje("b", ["a"], "y")
    assert isinstance(kgob.aguas_arriba("a"), list)


def test_el_linaje_hereda_la_cadena_de_hashes_del_log(kgob):
    """Se escribe en el log append-only que ya existe, así que editar un
    asiento de linaje a mano rompe la integridad y se nota."""
    from kobra import auditoria as kaud
    kgob.registrar_linaje("salida", ["entrada"], "prueba")
    assert kaud.verificar_integridad()["ok"] is True


# ---------------------------------------------------------------------------
# Resumen para la pantalla
# ---------------------------------------------------------------------------
def test_el_resumen_trae_todo_lo_que_muestra_la_pantalla(kgob, cartera):
    r = kgob.resumen(cartera, rol="gestor")
    assert r["filas"] == len(cartera)
    assert r["columnas"] == len(cartera.columns)
    assert sum(r["por_nivel"].values()) == len(cartera.columns)
    assert r["calidad"]["apto"] is True
    assert r["integridad_log"]["ok"] is True
    assert r["visibles"]["id_deudor"] is False
