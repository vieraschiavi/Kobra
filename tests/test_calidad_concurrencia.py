# © 2026 Martín Viera. Todos los derechos reservados.

"""`_guardar_calidad` (webapp/backend/api.py) hace un read-modify-write sobre
un CSV: lee el archivo entero, le suma una fila, reescribe. Dos evaluaciones
subidas casi juntas (dos supervisores cargando llamadas al mismo tiempo)
podían leer el mismo CSV de N filas antes de que ninguna escribiera; las dos
calculaban N+1 y la segunda pisaba a la primera — una evaluación desaparecía
sin ningún error visible. Mismo patrón que ya resolvía `kobra/registro.py`
para el guardado de gestiones, acá sin lock.
"""
import importlib
import os
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """Recarga SOLO lo que captura `DIR_DATOS` al importarse (`kobra.rutas` y
    `webapp.backend.api`, que hace `DIR_DATOS = krutas.DIR_DATOS` a nivel de
    módulo) — no todo `kobra.*`/`webapp.*`. Borrar en bloque de `sys.modules`
    (patrón usado en otros tests de este repo) ensucia módulos no relacionados
    que otros archivos de test cargan más tarde en la misma corrida: ver
    `tests/test_seguridad.py::_olvidar_modulos`, que ya había causado este
    mismo tipo de contaminación una vez. Confirmado acá con evidencia: con el
    borrado en bloque, `tests/test_kobra.py` y `tests/test_doble_modo.py`
    fallaban SOLO cuando corrían después de este archivo en la suite
    completa, nunca en aislamiento — la firma típica de contaminación entre
    tests, no un bug real en esos módulos."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import rutas as krutas
    importlib.reload(krutas)
    from webapp.backend import api as mod
    importlib.reload(mod)
    yield mod
    monkeypatch.undo()
    importlib.reload(krutas)
    importlib.reload(mod)


def _evaluacion():
    from kobra import calidad_gestion as kcalidad
    return kcalidad.evaluar(
        "Gestor: Buenos días, lo llamo por su cuenta atrasada. "
        "Cliente: Sí, ¿en cuánto está? "
        "Gestor: Le puedo ofrecer pagarlo en 3 cuotas, ¿le sirve? "
        "Cliente: Sí, dale, gracias.",
        canal="Llamada", usar_ia=False)


def test_evaluaciones_concurrentes_no_se_pisan(api):
    """N hilos guardando evaluaciones al mismo tiempo: el CSV final tiene que
    tener exactamente N filas, no menos."""
    N = 25
    errores = []

    def _guardar(i):
        try:
            api._guardar_calidad("principal", f"Gestor-{i}", "2026-01",
                                 "Llamada", f"audio-{i}.wav", _evaluacion())
        except Exception as e:                          # pragma: no cover
            errores.append(e)

    hilos = [threading.Thread(target=_guardar, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=15)

    assert not errores, f"guardar tiró excepciones: {errores}"
    df = api._leer_calidad("principal")
    assert df is not None
    assert len(df) == N, (
        f"se guardaron {N} evaluaciones concurrentes pero el CSV quedó con "
        f"{len(df)} filas — se perdieron escrituras")
    # Ninguna fila duplicada ni faltante: los N gestores están todos.
    assert set(df["gestor"]) == {f"Gestor-{i}" for i in range(N)}


def test_el_lock_no_impide_el_uso_normal_secuencial(api):
    """El lock no puede convertir el flujo normal (una evaluación por vez) en
    algo más lento o roto — sigue funcionando exactamente igual."""
    for i in range(3):
        out = api._guardar_calidad("principal", "Gestor Único", "2026-01",
                                   "Llamada", f"a{i}.wav", _evaluacion())
        assert out["acumuladas"] == i + 1
