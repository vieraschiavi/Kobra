# © 2026 Martín Viera. Todos los derechos reservados.
"""Tests del tablero de calidad de llamadas.

Pedido: una pestaña que analice la calidad por **gestor, mes, año y aspecto de
la negociación**, comparando contra la media de gestores, con KPIs.

Lo que hace útil al tablero no es la nota sino la comparación: saber que un
gestor tiene 58 de calidad no dice qué entrenarle; saber que está 40 puntos por
debajo de la media del equipo en "Negociación deuda total" y en línea en el
resto, sí.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import calidad_gestion as cg  # noqa: E402


def _dataset():
    """Tres gestores, tres meses. Al 'Gestor 05' se le inyecta una debilidad
    concreta en el criterio 3 para poder verificar que el tablero la encuentre."""
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    rng = np.random.default_rng(42)
    filas = []
    for gestor, sesgo in (("Gestor 04", +8), ("Gestor 05", -12), ("Gestor 12", 0)):
        for mes in ("2026-01", "2026-02", "2026-03"):
            for _ in range(6):
                ev, total = {"criterios": []}, 0.0
                for c in cg.RUBRICA:
                    flojo = -0.45 * c["max"] if (gestor == "Gestor 05" and c["id"] == 3) else 0
                    p = float(np.clip(c["max"] * (0.72 + sesgo / 100) + flojo
                                      + rng.normal(0, c["max"] * 0.08), 0, c["max"]))
                    ev["criterios"].append({"id": c["id"], "puntaje": round(p, 2)})
                    total += p
                ev["puntaje_total"] = round(total, 1)
                filas.append(cg.fila_evaluacion(gestor, f"{mes}-15", "Llamada",
                                                "a.mp3", ev, "x"))
    return pd.DataFrame(filas)


def test_sin_datos_no_rompe():
    for vacio in (None, []):
        p = cg.panel_calidad(vacio)
        assert p["total"] == 0 and p["por_criterio"] == [] and p["kpis"] == {}


def test_encuentra_el_aspecto_flojo_comparando_contra_el_equipo():
    """El caso que justifica el tablero: detecta *qué* aspecto entrenar."""
    p = cg.panel_calidad(_dataset(), gestor="Gestor 05")
    peor = p["oportunidades"][0]
    assert peor["criterio"] == "Negociación deuda total"
    assert peor["brecha"] < -25, "no detectó la debilidad inyectada"
    assert p["kpis"]["peor_aspecto"] == "Negociación deuda total"
    assert p["kpis"]["vs_media"] < 0


def test_la_media_es_del_equipo_no_del_gestor_filtrado():
    """Regresión conceptual: si la media se calculara sobre el mismo gestor
    filtrado, la brecha daría cero en todos los aspectos y el tablero no
    serviría para nada."""
    df = _dataset()
    p = cg.panel_calidad(df, gestor="Gestor 05")
    brechas = [c["brecha"] for c in p["por_criterio"] if c["brecha"] is not None]
    assert brechas and any(abs(b) > 1 for b in brechas), "la media se calculó sobre sí mismo"
    # Y la media del equipo coincide con la del panel sin filtrar.
    assert p["kpis"]["media_equipo"] == cg.panel_calidad(df)["kpis"]["calidad_prom"]


def test_los_criterios_se_comparan_normalizados():
    """Sin normalizar no se pueden comparar entre sí: 'Escucha activa' vale 15
    puntos y 'Apertura y saludo' 5, así que un 4 en el primero (26% del máximo,
    malo) parecería mejor que un 4 en el segundo (80%, bueno)."""
    assert cg._pct(4, 15) == pytest.approx(26.7, abs=0.1)
    assert cg._pct(4, 5) == pytest.approx(80.0)
    assert cg._pct(None, 5) is None and cg._pct(3, 0) is None
    p = cg.panel_calidad(_dataset(), gestor="Gestor 04")
    for c in p["por_criterio"]:
        if c["pct"] is not None:
            assert 0 <= c["pct"] <= 100


def test_filtra_por_gestor_mes_y_anio():
    df = _dataset()
    assert cg.panel_calidad(df, mes="2026-02")["total"] == 18
    assert cg.panel_calidad(df, gestor="Gestor 04", mes="2026-02")["total"] == 6
    assert cg.panel_calidad(df, anio="2026")["total"] == 54
    assert cg.panel_calidad(df, anio="2025")["total"] == 0


def test_las_opciones_de_filtro_no_se_vacian_al_filtrar():
    """Regresión de usabilidad: si el universo de filtros se calcula DESPUÉS de
    filtrar, al elegir un gestor la pantalla se queda sin los demás y no se
    puede volver."""
    p = cg.panel_calidad(_dataset(), gestor="Gestor 05", mes="2026-01")
    assert len(p["gestores"]) == 3
    assert len(p["meses"]) == 3


def test_la_evolucion_trae_gestor_y_equipo_por_mes():
    p = cg.panel_calidad(_dataset(), gestor="Gestor 05")
    assert [e["mes"] for e in p["evolucion"]] == ["2026-01", "2026-02", "2026-03"]
    for e in p["evolucion"]:
        assert e["gestor"] is not None and e["equipo"] is not None
        assert e["gestor"] < e["equipo"], "el gestor flojo debería estar por debajo"


def test_el_ranking_ordena_y_marca_la_distancia_a_la_media():
    p = cg.panel_calidad(_dataset())
    notas = [r["calidad_prom"] for r in p["ranking"]]
    assert notas == sorted(notas, reverse=True)
    assert p["ranking"][0]["gestor"] == "Gestor 04"
    assert p["ranking"][0]["vs_media"] > 0 > p["ranking"][-1]["vs_media"]


def test_la_distribucion_cubre_todos_los_audios():
    p = cg.panel_calidad(_dataset())
    assert sum(t["audios"] for t in p["distribucion"]) == p["total"]
