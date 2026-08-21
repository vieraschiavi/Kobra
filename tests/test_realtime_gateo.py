# © 2026 Martín Viera. Todos los derechos reservados.

"""`realtime/` cobra como el resto del producto, y no se ofrece a la red.

Este servicio hace las tres acciones que `kobra/plan.py` define como gestión
facturable —transcribir, copilotar y llamar por teléfono— y hasta estos tests
no miraba el plan ni descontaba cupo. Un cliente con la demo vencida, o con un
plan sin `voz`, levantaba `python -m realtime.server` desde su propia carpeta
(el código viaja en todas las ediciones) y tenía el producto completo gratis.

Encima ataba `0.0.0.0` sin pedir credenciales: en una red corporativa
cualquiera con la IP de la máquina llegaba al copiloto, a la transcripción y a
`/voz/llamar`, que dispara una llamada telefónica real.
"""
import importlib
import inspect
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECRETO = "secreto-de-prueba-del-gateo-realtime"


@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    """El servidor realtime con una licencia concreta aplicada."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)

    def montar(plan="basico", features=None):
        for k in list(sys.modules):
            if k.startswith(("kobra", "realtime")):
                del sys.modules[k]
        from kobra import config as kconfig
        importlib.reload(kconfig)
        from backend_venta import licencias as klic
        from kobra.edicion import CLAVE_TOKEN
        token = klic.emitir_licencia("cliente-rt", plan, features=features,
                                     secreto=SECRETO)
        kconfig.guardar_extra(CLAVE_TOKEN, token)
        from fastapi.testclient import TestClient

        from realtime import server
        return server, TestClient(server.app)

    yield montar
    for k in list(sys.modules):
        if k.startswith(("kobra", "realtime")):
            del sys.modules[k]


def _audio():
    return {"audio": ("x.wav", b"RIFF0000WAVEfmt ", "audio/wav")}


# ---------------------------------------------------------------------------
# Gateo por plan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ruta", ["/transcribe", "/analizar_audio"])
def test_sin_voz_en_el_plan_no_se_transcribe(servidor, ruta):
    """`voz` se vende aparte. Antes alcanzaba con levantar este servicio."""
    _s, cli = servidor(plan="basico", features=["copiloto"])
    r = cli.post(ruta, files=_audio())
    assert r.status_code == 403, f"{ruta} no gatea por plan"
    assert r.json()["motivo"] == "feature_no_incluida"


def test_sin_copiloto_en_el_plan_no_se_copilotea(servidor):
    _s, cli = servidor(plan="basico", features=["voz"])
    r = cli.post("/copiloto_audio", files=_audio())
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"


def test_una_llamada_telefonica_real_exige_el_plan(servidor):
    """`/voz/llamar` gasta plata de verdad en cada intento."""
    _s, cli = servidor(plan="basico", features=["copiloto"])
    r = cli.post("/voz/llamar", json={"telefono": "+59899000000"})
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"


def test_con_el_plan_correcto_pasa_el_candado(servidor):
    """El gateo no puede volverse un muro para quien sí pagó: con la feature
    incluida, el pedido llega al handler (falle después por lo que sea, pero
    no por plan)."""
    _s, cli = servidor(plan="basico", features=["voz", "copiloto"])
    r = cli.post("/analizar_audio", files=_audio())
    assert r.status_code != 403, "gatea a alguien que sí tiene la feature"


def test_el_cupo_agotado_corta_con_402(servidor):
    """Mismo código que la webapp, para que el frontend los trate igual."""
    s, cli = servidor(plan="basico", features=["voz"])
    from kobra import plan as kplan
    for _ in range(kplan.cupo() or 0):
        kplan.registrar_gestion()
    r = cli.post("/transcribe", files=_audio())
    assert r.status_code == 402
    assert r.json()["motivo"] == "cupo_agotado"


# ---------------------------------------------------------------------------
# Exposición de red
# ---------------------------------------------------------------------------
def test_no_escucha_en_toda_la_red_por_defecto():
    """Ataba 0.0.0.0 siempre. Sin autenticación, eso es ofrecerle el copiloto
    y el disparador de llamadas a cualquiera en la LAN."""
    fuente = open(os.path.join(ROOT, "realtime", "server.py"),
                  encoding="utf-8").read()
    principal = fuente.split('if __name__ == "__main__":')[1]
    assert 'host="0.0.0.0"' not in principal, \
        "sigue atando 0.0.0.0 sin que nadie lo pida"
    assert "KOBRA_REALTIME_HOST" in principal, \
        "no hay forma explícita de exponerlo cuando de verdad se necesita"
    assert '"127.0.0.1"' in principal, "el default no es loopback"


def test_exponerlo_a_la_red_avisa_de_que_no_pide_credenciales():
    fuente = open(os.path.join(ROOT, "realtime", "server.py"),
                  encoding="utf-8").read()
    principal = fuente.split('if __name__ == "__main__":')[1]
    assert "pide credenciales" in principal, \
        "se puede exponer a la red sin que nada advierta que no hay auth"
    assert "ATENCION" in principal


def test_los_endpoints_que_facturan_estan_todos_gateados():
    """Que no se agregue uno nuevo sin candado."""
    from realtime import server
    for nombre, feature in (("transcribe", "voz"), ("analizar_audio", "voz"),
                            ("copiloto_audio", "copiloto"),
                            ("voz_llamar", "voz")):
        fuente = inspect.getsource(getattr(server, nombre))
        assert "kplan.exigir(" in fuente, f"{nombre} no exige feature"
        assert f'"{feature}"' in fuente, f"{nombre} no exige {feature!r}"
        assert "kplan.verificar_cupo()" in fuente, f"{nombre} no mira el cupo"
