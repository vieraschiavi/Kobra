# © 2026 Martín Viera. Todos los derechos reservados.

"""Proyectos: salud de portafolio y backlog priorizado.

Portado de MV Project Management. Lo que se prueba:

  * que el índice **se mueva con el tiempo** — el motor original tenía la
    fecha de hoy fija en el código, y portado tal cual el cronograma quedaría
    congelado: al día siguiente ninguna tarea vencería;
  * que un tablero en verde signifique algo. Un índice que da 80 con el 20% de
    las tareas vencidas tranquiliza mientras el proyecto se cae, y eso es peor
    que no tener tablero;
  * que la prioridad sea defendible frente a quien pregunte por qué su tarea
    quedó abajo.
"""
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import proyectos as kpro  # noqa: E402

HOY = datetime(2026, 6, 1)


@pytest.fixture()
def proyectos():
    return pd.DataFrame({
        "proyecto_id": ["P1", "P2"],
        "nombre": ["Migración ERP", "Portal clientes"],
        "dueno": ["Ana", "Beto"],
        "criticidad": ["Alta", "Media"],
        "presupuesto": [100000.0, 50000.0],
        "ejecutado": [60000.0, 62000.0],      # P2 pasado de presupuesto
    })


@pytest.fixture()
def tareas():
    def f(dias):
        return HOY + timedelta(days=dias)
    return pd.DataFrame({
        "tarea_id": ["T1", "T2", "T3", "T4", "T5", "T6"],
        "proyecto_id": ["P1", "P1", "P1", "P2", "P2", "P2"],
        "estado": ["done", "in_progress", "todo", "blocked", "todo", "todo"],
        "responsable": ["Ana", "Ana", None, "Beto", "Beto", "Beto"],
        "prioridad": ["Media", "Alta", "Baja", "Alta", "Media", "Media"],
        "vencimiento": [f(-30), f(-5), f(20), f(-2), f(10), f(60)],
        "depende_de": [None, "T1", "T2", None, "T4", "T5"],
    })


@pytest.fixture()
def equipo():
    return pd.DataFrame({
        "nombre": ["Ana", "Beto"],
        "capacidad_semanal_hs": [40, 40],
        "carga_actual_hs": [38, 70],          # Beto sobrecargado
    })


# ---------------------------------------------------------------------------
# La fecha: el bug del motor original
# ---------------------------------------------------------------------------
def test_el_indice_cambia_si_pasa_el_tiempo(proyectos, tareas, equipo):
    """El motor de origen tenía `_TODAY = datetime(2026, 7, 12)` fijo. Portado
    tal cual, el cronograma quedaría congelado en esa fecha para siempre."""
    ahora = kpro.indice_general(proyectos, tareas, equipo, hoy=HOY)
    dentro_de_un_ano = kpro.indice_general(proyectos, tareas, equipo,
                                           hoy=HOY + timedelta(days=365))
    assert dentro_de_un_ano < ahora, (
        "el índice no empeoró al pasar un año con las mismas tareas sin "
        "terminar: la fecha está congelada")


def test_sin_fecha_explicita_usa_el_reloj(proyectos, tareas, equipo):
    """En producción nadie le pasa la fecha: la tiene que tomar sola."""
    df = kpro.salud(proyectos, tareas, equipo)
    assert len(df) == 2


# ---------------------------------------------------------------------------
# Que el verde signifique algo
# ---------------------------------------------------------------------------
def test_un_proyecto_con_tareas_vencidas_no_da_verde(proyectos, tareas, equipo):
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    p1 = s[s["proyecto_id"] == "P1"].iloc[0]
    assert p1["dim_cronograma"] < 100, "una tarea vencida no movió el cronograma"


def test_el_proyecto_pasado_de_presupuesto_lo_refleja(proyectos, tareas, equipo):
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    p2 = s[s["proyecto_id"] == "P2"].iloc[0]
    assert p2["dim_presupuesto"] < 100


def test_la_alerta_de_presupuesto_suena_antes_del_100(proyectos, tareas, equipo):
    """Cuando un proyecto llega al 100% ya es tarde para reaccionar."""
    casi = proyectos.copy()
    casi.loc[0, "ejecutado"] = 95000.0        # 95% del presupuesto
    s = kpro.salud(casi, tareas, equipo, hoy=HOY)
    assert s[s["proyecto_id"] == "P1"].iloc[0]["dim_presupuesto"] < 100


def test_una_tarea_bloqueada_baja_el_riesgo(proyectos, tareas, equipo):
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    assert s[s["proyecto_id"] == "P2"].iloc[0]["dim_riesgo"] < 100


def test_una_tarea_sin_responsable_baja_el_alcance(proyectos, tareas, equipo):
    """Nadie las va a hacer, y nadie va a avisar que no se hicieron."""
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    assert s[s["proyecto_id"] == "P1"].iloc[0]["dim_alcance"] < 100


def test_el_dueno_sobrecargado_baja_la_dimension_equipo(proyectos, tareas, equipo):
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    p1 = s[s["proyecto_id"] == "P1"].iloc[0]   # Ana, 38 de 40 hs
    p2 = s[s["proyecto_id"] == "P2"].iloc[0]   # Beto, 70 de 40 hs
    assert p2["dim_equipo"] < p1["dim_equipo"]


def test_una_dependencia_huerfana_se_detecta(proyectos, tareas, equipo):
    """El síntoma de un plan viejo: alguien borró una tarea y las que dependían
    de ella quedaron colgando, pero el cronograma sigue calculando como si la
    cadena estuviera entera."""
    rotas = tareas.copy()
    rotas.loc[rotas["tarea_id"] == "T2", "depende_de"] = "T-BORRADA"
    s = kpro.salud(proyectos, rotas, equipo, hoy=HOY)
    assert s[s["proyecto_id"] == "P1"].iloc[0]["dim_dependencias"] < 100


def test_un_proyecto_sin_dueno_no_da_100_en_equipo(proyectos, tareas, equipo):
    """Dar 100 diría que está sano justo por no tener a nadie a cargo."""
    huerfano = proyectos.copy()
    huerfano.loc[0, "dueno"] = None
    s = kpro.salud(huerfano, tareas, equipo, hoy=HOY)
    assert s[s["proyecto_id"] == "P1"].iloc[0]["dim_equipo"] < 100


def test_el_semaforo_usa_los_umbrales_declarados(proyectos, tareas, equipo):
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    for _, f in s.iterrows():
        if f["indice"] < kpro.UMBRAL_RIESGO:
            assert f["estado"] == "riesgo"
        elif f["indice"] < kpro.UMBRAL_OBSERVACION:
            assert f["estado"] == "observacion"
        else:
            assert f["estado"] == "saludable"


def test_el_desglose_viene_con_el_indice(proyectos, tareas, equipo):
    """Un número solo se discute; un desglose se acciona — dice qué arreglar."""
    s = kpro.salud(proyectos, tareas, equipo, hoy=HOY)
    for d in kpro.DIMENSIONES:
        assert f"dim_{d}" in s.columns


# ---------------------------------------------------------------------------
# Backlog priorizado
# ---------------------------------------------------------------------------
def test_lo_vencido_va_primero(proyectos, tareas, equipo):
    """El costo del atraso ya se está pagando: no compite, va antes."""
    b = kpro.backlog(proyectos, tareas, hoy=HOY)
    primera = b.iloc[0]
    assert primera["dias_restantes"] < 0, \
        f"arriba de todo quedó algo que todavía tiene plazo: {primera.to_dict()}"


def test_lo_terminado_no_entra_al_backlog(proyectos, tareas, equipo):
    b = kpro.backlog(proyectos, tareas, hoy=HOY)
    assert "T1" not in set(b["tarea_id"]), "una tarea terminada está en el backlog"


def test_una_tarea_que_frena_a_otras_sube(proyectos, tareas, equipo):
    """Lo que decide la prioridad real es el tamaño de la cola que quedó
    esperando, no solo la urgencia propia."""
    b = kpro.backlog(proyectos, tareas, hoy=HOY)
    t2 = b[b["tarea_id"] == "T2"].iloc[0]
    assert t2["tareas_impactadas"] >= 1


def test_la_cadena_de_dependencias_se_sigue_entera(proyectos, tareas, equipo):
    """T4 -> T5 -> T6: si se cuenta un solo salto, T4 parece frenar a una sola
    tarea cuando en realidad frena a dos."""
    b = kpro.backlog(proyectos, tareas, hoy=HOY)
    t4 = b[b["tarea_id"] == "T4"].iloc[0]
    assert t4["tareas_impactadas"] == 2, \
        f"contó {t4['tareas_impactadas']} en vez de 2: no siguió la cadena"


def test_un_ciclo_en_el_plan_no_cuelga_el_calculo(proyectos, tareas, equipo):
    """Un plan mal cargado puede tener ciclos; recorrerlos sin cortar sería la
    app colgada en la pantalla de proyectos."""
    ciclo = tareas.copy()
    ciclo.loc[ciclo["tarea_id"] == "T4", "depende_de"] = "T6"
    b = kpro.backlog(proyectos, ciclo, hoy=HOY)
    assert len(b) > 0


def test_sin_tareas_pendientes_devuelve_vacio_sin_romper(proyectos, tareas):
    todas_hechas = tareas.copy()
    todas_hechas["estado"] = "done"
    b = kpro.backlog(proyectos, todas_hechas, hoy=HOY)
    assert b.empty
    assert "valor_esperado" in b.columns, \
        "sin la columna, la pantalla rompe al ordenar una tabla vacía"


# ---------------------------------------------------------------------------
# Entrada incompleta e integración
# ---------------------------------------------------------------------------
def test_una_tabla_incompleta_dice_que_falta(proyectos):
    with pytest.raises(kpro.DatosIncompletos) as e:
        kpro.salud(proyectos, pd.DataFrame({"tarea_id": []}), None)
    assert "proyecto_id" in str(e.value) or "estado" in str(e.value)


def test_funciona_sin_tabla_de_equipo(proyectos, tareas):
    """No todo cliente carga el equipo: la salud tiene que salir igual."""
    s = kpro.salud(proyectos, tareas, None, hoy=HOY)
    assert len(s) == 2
    assert (s["dim_equipo"] > 0).all()


def test_el_resumen_trae_lo_que_muestra_la_pantalla(proyectos, tareas, equipo):
    r = kpro.resumen(proyectos, tareas, equipo, hoy=HOY)
    assert r["proyectos"] == 2
    assert r["en_riesgo"] + r["en_observacion"] + r["saludables"] == 2
    assert 0 <= r["indice_general"] <= 100
    assert len(r["backlog"]) <= 10
