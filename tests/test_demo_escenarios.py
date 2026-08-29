# © 2026 Martín Viera. Todos los derechos reservados.

"""Los dos escenarios de demo: completos, deterministas y verificables.

Lo que se fija acá es la promesa de la pantalla: "dos empresas sintéticas
completas, con datos para todos los módulos". Si un escenario deja un módulo
sin datos, la demo muestra una pantalla vacía justo delante de un prospecto;
si la verificación no ejecuta de verdad, el checklist es un "debería andar"
con tildes.
"""
import os

import pandas as pd
import pytest

from kobra import demo_escenarios as de


@pytest.fixture(scope="module")
def activados(tmp_path_factory):
    """Los dos escenarios activados una sola vez para todo el archivo: la
    generación scorea con el modelo real y no es gratis."""
    out = {}
    for esc in de.ESCENARIOS:
        d = tmp_path_factory.mktemp(esc)
        out[esc] = (str(d), de.activar(esc, str(d)))
    return out


def test_hay_al_menos_dos_escenarios():
    assert len(de.ESCENARIOS) >= 2


@pytest.mark.parametrize("esc", sorted(de.ESCENARIOS))
def test_cada_escenario_trae_datos_para_todos_los_modulos(activados, esc):
    """La promesa central: ningún módulo queda con la pantalla vacía."""
    dir_datos, _ = activados[esc]
    for tabla in ("kobra_scored", "kobra_gestiones", "calidad_evaluaciones",
                  "logistica_productos", "logistica_ventas",
                  "proyectos_proyectos", "proyectos_tareas",
                  "proyectos_equipo"):
        ruta = os.path.join(dir_datos, f"{tabla}.csv")
        assert os.path.exists(ruta), f"{esc} no generó {tabla}"
        assert len(pd.read_csv(ruta)) > 0, f"{esc}: {tabla} quedó vacía"


@pytest.mark.parametrize("esc", sorted(de.ESCENARIOS))
def test_la_cartera_pasa_por_el_scoring_real(activados, esc):
    """La cartera del escenario recorre el MISMO camino que una real subida:
    tiene que salir con probpago, decil, estrategia y guion — no un CSV
    manual con columnas de adorno."""
    dir_datos, _ = activados[esc]
    df = pd.read_csv(os.path.join(dir_datos, "kobra_scored.csv"))
    for col in ("probpago", "decil", "estrategia", "descuento_recomendado",
                "guion", "motivo_probpago"):
        assert col in df.columns, f"{esc}: falta {col} en la cartera scoreada"
    assert df["probpago"].between(0, 1).all()


def test_los_escenarios_son_empresas_distintas(activados):
    """Si las dos demos se parecen, el selector no demuestra nada. El ticket
    promedio de la distribuidora (crédito comercial) tiene que ser varias
    veces el de la financiera (consumo)."""
    fin = pd.read_csv(os.path.join(activados["financiera"][0], "kobra_scored.csv"))
    dis = pd.read_csv(os.path.join(activados["distribuidora"][0], "kobra_scored.csv"))
    assert dis["monto_deuda"].mean() > fin["monto_deuda"].mean() * 2, (
        "la distribuidora no se distingue de la financiera: mismo ticket")


def test_activar_es_determinista(tmp_path):
    """Semilla fija: dos activaciones dan la misma cartera. Sin esto, cada
    demo muestra números distintos y el guion del vendedor no cierra."""
    a = de.activar("financiera", str(tmp_path / "a"))
    b = de.activar("financiera", str(tmp_path / "b"))
    assert a["deuda_total"] == b["deuda_total"]
    ca = pd.read_csv(tmp_path / "a" / "kobra_scored.csv")
    cb = pd.read_csv(tmp_path / "b" / "kobra_scored.csv")
    pd.testing.assert_frame_equal(ca, cb)


def test_un_escenario_inventado_se_rechaza():
    with pytest.raises(ValueError, match="desconocido"):
        de.generar("panaderia")


@pytest.mark.parametrize("esc", sorted(de.ESCENARIOS))
def test_la_verificacion_pasa_entera_con_cada_escenario(activados, esc):
    """El gate del pedido: todos los módulos en verde, punta a punta, con
    evidencia. Un solo paso rojo hace fallar este test con su detalle."""
    dir_datos, _ = activados[esc]
    pasos = de.verificar(dir_datos)
    modulos = {p["modulo"] for p in pasos}
    # Los módulos comprometidos tienen que estar TODOS en el checklist.
    for esperado in ("ProbPago", "Gestor IA", "Chatbot", "Gobernanza", "KPIs",
                     "AutoML", "Logística", "Proyectos", "Ingeniería",
                     "Cumplimiento", "Agenda", "Gestores", "Calidad",
                     "Cuentas por cobrar", "Campaña"):
        assert any(esperado in m for m in modulos), (
            f"la verificación no cubre {esperado}")
    fallas = [p for p in pasos if not p["ok"]]
    assert not fallas, "módulos en falla: " + "; ".join(
        f"{p['modulo']} → {p['detalle']}" for p in fallas)


@pytest.mark.parametrize("esc", sorted(de.ESCENARIOS))
def test_las_gestiones_tienen_el_esquema_del_producto(activados, esc):
    """El defecto que motivó estos tests: la primera versión generaba
    gestiones con un esquema propio de 6 columnas y Agenda y Gestores
    devolvían 500 apenas se activaba el escenario. Las gestiones tienen que
    salir del generador canónico, con las columnas que las pantallas leen."""
    dir_datos, _ = activados[esc]
    g = pd.read_csv(os.path.join(dir_datos, "kobra_gestiones.csv"))
    for col in ("fecha_gestion", "gestor_id", "gestor", "canal", "resultado",
                "fecha_compromiso", "fecha_pago", "monto_acordado",
                "calidad_gestion", "recupero", "mes", "usa_kobra"):
        assert col in g.columns, f"{esc}: a las gestiones les falta {col!r}"
    # Y con contenido para las pantallas: promesas (Agenda) y varios gestores.
    assert (g["resultado"] == "Promesa").any(), f"{esc}: sin promesas"
    assert g["gestor_id"].nunique() >= 5, f"{esc}: muy pocos gestores"


@pytest.mark.parametrize("esc", sorted(de.ESCENARIOS))
def test_las_llamadas_evaluadas_salen_del_evaluador_real(activados, esc):
    """El panel de calidad no puede decir "todavía no hay llamadas
    evaluadas" en una demo recién activada. Y los puntajes tienen que venir
    del evaluador real con dispersión — un panel donde todos tienen 95 no
    distingue a quién entrenar."""
    dir_datos, _ = activados[esc]
    ev = pd.read_csv(os.path.join(dir_datos, "calidad_evaluaciones.csv"))
    assert len(ev) >= 30, f"{esc}: pocas llamadas evaluadas ({len(ev)})"
    assert ev["puntaje_total"].between(0, 100).all()
    assert ev["puntaje_total"].std() > 4, (
        f"{esc}: todos los puntajes casi iguales "
        f"(sd={ev['puntaje_total'].std():.1f}): el panel no distingue nada")
    # Columnas por criterio de la rúbrica (c1..c14), como las guarda el store.
    assert {"c1", "c14", "gestor", "mes"} <= set(ev.columns)


def test_la_verificacion_no_es_de_tildes(activados, monkeypatch):
    """Control del control: si un módulo se rompe de verdad, el checklist lo
    tiene que mostrar en rojo — no seguir verde por mirar solo archivos."""
    from kobra import medidas
    dir_datos, _ = activados["financiera"]

    def rota(*a, **k):
        raise RuntimeError("motor de fórmulas roto a propósito")
    monkeypatch.setattr(medidas, "evaluar", rota)
    pasos = de.verificar(dir_datos)
    kpi = next(p for p in pasos if "KPIs" in p["modulo"])
    assert not kpi["ok"], "el checklist quedó verde con el módulo roto"
    assert "roto a propósito" in kpi["detalle"]


def test_la_evidencia_trae_numeros_medidos(activados):
    """El detalle de cada paso verde tiene que traer una cifra (deudores,
    columnas, métricas) — es lo que separa evidencia de un tilde."""
    import re
    dir_datos, _ = activados["financiera"]
    for p in de.verificar(dir_datos):
        assert re.search(r"\d", p["detalle"]) or "permite" in p["detalle"], (
            f"{p['modulo']} pasó sin evidencia medida: {p['detalle']!r}")
