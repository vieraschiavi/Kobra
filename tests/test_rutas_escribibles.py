# © 2026 Martín Viera. Todos los derechos reservados.
"""Tests de kobra/rutas.py: DIR_DATOS nunca apunta a la carpeta de
instalación (Program Files) cuando el programa corre empaquetado —
bug real reportado: PermissionError al subir un audio para analizar,
porque app/app.py escribía relativo a ROOT (la instalación, de solo
lectura para un usuario sin admin)."""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def rutas_dev(monkeypatch):
    """Sin empaquetar (dev/tests): DIR_DATOS == la raíz del repo, sin cambios."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("KOBRA_DATA_DIR", raising=False)
    from kobra import rutas
    importlib.reload(rutas)
    return rutas


@pytest.fixture()
def rutas_empaquetado(tmp_path, monkeypatch):
    """Empaquetado (PyInstaller simulado): DIR_DATOS es una carpeta propia
    del usuario, nunca el bundle (que simula ser de solo lectura)."""
    bundle = tmp_path / "bundle_instalado"
    (bundle / "data").mkdir(parents=True)
    (bundle / "outputs").mkdir(parents=True)
    (bundle / "data" / "kobra_gestiones.csv").write_text("id_deudor\nKB-1\n")
    (bundle / "outputs" / "kobra_scored.csv").write_text("id_deudor\nKB-1\n")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.delenv("KOBRA_DATA_DIR", raising=False)
    userdata = tmp_path / "userdata"
    monkeypatch.setenv("LOCALAPPDATA", str(userdata))
    monkeypatch.setattr(sys, "platform", "win32")

    from kobra import rutas
    importlib.reload(rutas)
    yield rutas, bundle, userdata
    # kobra.rutas es un módulo compartido por todo el proceso de tests: si no
    # se restaura a modo dev acá, el resto de la suite (que corra después de
    # este archivo, en el mismo proceso) heredaría un DIR_DATOS de este
    # tmp_path ya descartado — rompiendo tests de otros archivos sin relación
    # aparente (bug real que apareció así: test_webapp.py fallaba con
    # KeyError porque _scored() ya no encontraba outputs/kobra_scored.csv).
    monkeypatch.undo()
    importlib.reload(rutas)


def test_dev_dir_datos_es_el_repo(rutas_dev):
    assert rutas_dev.DIR_DATOS == rutas_dev.ROOT_REPO


def test_empaquetado_dir_datos_no_es_el_bundle(rutas_empaquetado):
    rutas, bundle, userdata = rutas_empaquetado
    assert rutas.DIR_DATOS != str(bundle)
    assert rutas.DIR_DATOS.startswith(str(userdata))
    assert rutas.DIR_BUNDLE == str(bundle)


def test_empaquetado_siembra_demo_y_es_escribible(rutas_empaquetado):
    rutas, bundle, userdata = rutas_empaquetado
    rutas.sembrar_si_hace_falta()
    assert os.path.isfile(os.path.join(rutas.DIR_DATOS, "data", "kobra_gestiones.csv"))
    assert os.path.isfile(os.path.join(rutas.DIR_DATOS, "outputs", "kobra_scored.csv"))
    # Y es realmente escribible (a diferencia del bundle, que simula Program Files)
    prueba = os.path.join(rutas.DIR_DATOS, "prueba_escritura.txt")
    with open(prueba, "w") as f:
        f.write("ok")
    assert os.path.exists(prueba)


def test_empaquetado_no_pisa_datos_reales_ya_sembrados(rutas_empaquetado):
    rutas, bundle, userdata = rutas_empaquetado
    rutas.sembrar_si_hace_falta()
    ruta_real = os.path.join(rutas.DIR_DATOS, "data", "kobra_gestiones.csv")
    with open(ruta_real, "w") as f:
        f.write("id_deudor\nKB-REAL-DEL-CLIENTE\n")
    rutas.sembrar_si_hace_falta()  # 2do arranque: no debe volver a copiar encima
    with open(ruta_real) as f:
        assert "KB-REAL-DEL-CLIENTE" in f.read()


def test_kobra_env_data_dir_fuerza_ubicacion(tmp_path, monkeypatch):
    forzado = tmp_path / "donde-yo-diga"
    monkeypatch.setenv("KOBRA_DATA_DIR", str(forzado))
    from kobra import rutas
    importlib.reload(rutas)
    assert rutas.DIR_DATOS == str(forzado)
    monkeypatch.undo()
    importlib.reload(rutas)


def test_modulos_dependientes_usan_dir_datos(rutas_empaquetado, monkeypatch):
    """registro.py y auditoria.py (los que realmente fallaban) deben resolver
    sus rutas contra DIR_DATOS, nunca contra el bundle de instalación."""
    rutas, bundle, userdata = rutas_empaquetado
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(userdata / "config"))

    from kobra import registro as kreg
    importlib.reload(kreg)
    assert kreg.SCORED_CSV.startswith(rutas.DIR_DATOS)
    assert kreg.GESTIONES_CSV.startswith(rutas.DIR_DATOS)

    from kobra import auditoria as kaud
    importlib.reload(kaud)
    assert kaud.LOG_FILE.startswith(rutas.DIR_DATOS)
