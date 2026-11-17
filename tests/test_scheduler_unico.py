# © 2026 Martín Viera. Todos los derechos reservados.

"""El scheduler de campañas corre UNA vez por instalación, sobre los datos del cliente.

Revisión de producción:

  * Arrancaba en cada importación de `realtime/server.py`. Con
    `KOBRA_WORKERS=3` eran 7 schedulers, y el mismo deudor recibía hasta 7
    llamadas o WhatsApp por corrida; el informe del lunes llegaba 7 veces.
  * Los jobs leían `ROOT/data` y `ROOT/outputs` (el repo) en vez de la carpeta
    de datos del cliente (`KOBRA_DATA_DIR`, que la release fija): instalado,
    la campaña no encontraba gestiones y el informe no salía, y con la cartera
    real activa el informe mandaba la demo.
"""
import os
import subprocess
import sys
import textwrap
import time

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_con_varios_procesos_hay_un_solo_scheduler(tmp_path):
    pytest.importorskip("apscheduler")
    pytest.importorskip("fastapi")
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {ROOT!r})
        from realtime import server
        print("SCHEDULER" if server._scheduler is not None else "ESPERA", flush=True)
        time.sleep(4)
    """)
    entorno = {**os.environ, "KOBRA_DATA_DIR": str(tmp_path / "datos"),
               "KOBRA_CONFIG_DIR": str(tmp_path / "config")}
    procesos = []
    for _ in range(3):
        procesos.append(subprocess.Popen([sys.executable, "-c", script], env=entorno,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True))
        time.sleep(0.2)
    salidas = [p.communicate(timeout=120) for p in procesos]
    roles = [out.strip().splitlines()[-1] if out.strip() else f"ERROR: {err[-300:]}"
             for out, err in salidas]
    assert sorted(roles) == ["ESPERA", "ESPERA", "SCHEDULER"], roles


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    previos = dict(sys.modules)
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    from realtime import server
    yield server
    for k in list(sys.modules):
        if k.startswith(("realtime", "kobra")):
            del sys.modules[k]
    sys.modules.update(previos)


def test_el_informe_semanal_usa_la_cartera_real_de_la_carpeta_de_datos(servidor, monkeypatch):
    import json

    from kobra import config as kconfig
    from kobra import informe_ejecutivo as kinforme
    from kobra import registro
    os.makedirs(os.path.dirname(registro.CARTERA_REAL_CSV), exist_ok=True)
    pd.DataFrame({"id_deudor": ["REAL-1"], "monto_deuda": [100.0]}).to_csv(
        registro.CARTERA_REAL_CSV, index=False)
    with open(registro.ORIGEN_JSON, "w", encoding="utf-8") as f:
        json.dump({"modo": "real"}, f)
    kconfig.guardar_extra("INFORME_EMAIL_ACTIVO", True)
    kconfig.guardar_extra("INFORME_EMAIL_DESTINO", "gerencia@cliente.com")

    enviados = []
    monkeypatch.setattr(kinforme, "enviar_por_email",
                        lambda destino, scored, gestiones, **k: enviados.append(
                            (destino, list(scored["id_deudor"]), k)) or {"ok": True,
                                                                         "detalle": None})
    servidor._job_informe_semanal()
    assert enviados, "no mandó el informe: no encontró la cartera en la carpeta de datos"
    destino, ids, kwargs = enviados[0]
    assert destino == "gerencia@cliente.com" and ids == ["REAL-1"]
    assert kwargs["datos_demo"] is False


def test_la_campana_lee_las_gestiones_de_la_carpeta_de_datos(servidor, monkeypatch):
    from kobra import campana, registro
    from kobra import config as kconfig
    os.makedirs(os.path.dirname(registro.GESTIONES_CSV), exist_ok=True)
    pd.DataFrame({"id_deudor": ["KB-1"], "canal": ["Llamada"]}).to_csv(
        registro.GESTIONES_CSV, index=False)
    kconfig.guardar_extra("CAMPANA_ACTIVA", True)
    kconfig.guardar_extra("CAMPANA_CONTACTOS_CSV", "contactos.csv")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://kobra.example.com")

    leidas = []
    monkeypatch.setattr(campana, "contactados_hoy_por_campana", lambda: set())
    monkeypatch.setattr(campana, "plan_contacto_hoy",
                        lambda gestiones, **k: leidas.append(list(gestiones["id_deudor"]))
                        or pd.DataFrame())
    servidor._job_campana()
    assert leidas == [["KB-1"]]
