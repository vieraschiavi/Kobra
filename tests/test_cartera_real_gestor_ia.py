# © 2026 Martín Viera. Todos los derechos reservados.

"""El Gestor IA telefónico tiene que negociar con la cartera DEL CLIENTE.

El agujero que cierra este archivo era el peor de todos comercialmente: el
cliente importaba su cartera en el dashboard, la pantalla mostraba sus
deudores, lanzaba la campaña de voz… y el bot llamaba con los datos de la
cartera sintética de demostración.

La causa era una sola línea: `kobra/registro.py` leía SIEMPRE
`outputs/kobra_scored.csv` —la salida del pipeline sintético—, mientras la
webapp guardaba la cartera importada en `outputs/kobra_cartera_real.csv` con
una marca `origen_cartera.json`. Las dos mitades existían y nadie las unía.

Lo que se rompía en concreto, con un `id_deudor` que existe en las dos
carteras (pasa siempre: los IDs los pone el cliente, o vienen del ERP):

  * `monto_deuda` de otra persona,
  * `probpago` de otra persona,
  * y sobre todo el **descuento autorizado** de otra persona — una quita
    ofrecida por teléfono, grabada, sobre una deuda que nadie miró.

El segundo bloque cubre el fallback de llamada entrante: alguien que NO está
en la cartera. Ese caso es legítimo y hay que atenderlo, pero antes se le
inventaba un perfil medio y de ahí salía un descuento. Ahora se le ofrece
plan de cuotas sin quita, que es lo único defendible sin dato.
"""
import importlib
import json
import os
import sys

import pytest
from conftest import CABECERA_REALTIME

from kobra import registro

# ---------------------------------------------------------------------------
# Carteras de prueba
# ---------------------------------------------------------------------------
CABECERA = ("id_deudor,segmento,producto,departamento,tramo_mora,dias_mora,"
            "monto_deuda,probpago,segmento_propension,estrategia,"
            "descuento_recomendado,plan_cuotas,canal_recomendado,"
            "valor_esperado_recupero,prioridad,guion,motivo_probpago\n")

# Mismo id_deudor en las dos, valores distintos a propósito: es la única forma
# de comprobar de cuál de las dos salió el brief.
DEMO = CABECERA + (
    "KB-100000,Pyme,Tarjeta,Montevideo,91-180,120,999999,0.20,Baja,"
    "Quita agresiva,0.35,12,Llamada,50000,1,Guion demo,motivo demo\n")

REAL = CABECERA + (
    "KB-100000,Retail,Microcrédito,Salto,1-30,10,12345,0.90,Alta,"
    "Recordatorio suave,0.0,1,Email,11000,7,Guion real,motivo real\n")


@pytest.fixture()
def carteras(tmp_path, monkeypatch):
    """Aísla las tres rutas que mira `registro` y limpia su caché.

    El caché es una global del módulo: sin resetearlo, el primer test que lea
    una cartera se la deja puesta a todos los demás.
    """
    demo = tmp_path / "kobra_scored.csv"
    real = tmp_path / "kobra_cartera_real.csv"
    marca = tmp_path / "origen_cartera.json"
    demo.write_text(DEMO, encoding="utf-8")

    monkeypatch.setattr(registro, "SCORED_CSV", str(demo))
    monkeypatch.setattr(registro, "CARTERA_REAL_CSV", str(real))
    monkeypatch.setattr(registro, "ORIGEN_JSON", str(marca))
    monkeypatch.setattr(registro, "_scored_cache", None)
    monkeypatch.setattr(registro, "_scored_firma", None)
    yield {"demo": demo, "real": real, "marca": marca}
    registro._scored_cache = None
    registro._scored_firma = None


def importar(carteras, contenido=REAL, modo="real"):
    """Simula lo que hace la webapp al importar: el CSV y la marca."""
    carteras["real"].write_text(contenido, encoding="utf-8")
    carteras["marca"].write_text(json.dumps({"modo": modo, "tipo": modo}),
                                 encoding="utf-8")


# ---------------------------------------------------------------------------
# 1) De qué archivo sale la cartera
# ---------------------------------------------------------------------------
def test_sin_cartera_importada_usa_la_de_demostracion(carteras):
    assert registro.ruta_cartera() == str(carteras["demo"])


def test_con_cartera_importada_usa_la_del_cliente(carteras):
    importar(carteras)
    assert registro.ruta_cartera() == str(carteras["real"])


def test_el_boton_demo_vuelve_a_la_sintetica(carteras):
    """La marca en 'demo' manda aunque el archivo real siga ahí — es el mismo
    criterio que el interruptor del dashboard, así las dos pantallas no
    pueden discrepar sobre qué cartera está viendo el cliente."""
    importar(carteras, modo="demo")
    assert registro.ruta_cartera() == str(carteras["demo"])


def test_marca_real_sin_archivo_no_deja_sin_cartera(carteras):
    """Marca vieja apuntando a un archivo que ya no está: se cae a la de
    demostración en vez de quedarse sin nada. Quedarse sin cartera rompe la
    llamada; la pantalla ya avisa cuál está activa."""
    carteras["marca"].write_text('{"modo": "real"}', encoding="utf-8")
    assert registro.ruta_cartera() == str(carteras["demo"])


def test_marca_corrupta_no_tumba_el_brief(carteras):
    carteras["real"].write_text(REAL, encoding="utf-8")
    carteras["marca"].write_text("{ esto no es json", encoding="utf-8")
    assert registro.ruta_cartera() == str(carteras["demo"])
    assert registro.brief("KB-100000") is not None


# ---------------------------------------------------------------------------
# 2) El brief que recibe el bot
# ---------------------------------------------------------------------------
def test_el_brief_trae_los_datos_del_cliente_no_los_de_la_demo(carteras):
    """El corazón del asunto: mismo id en las dos carteras, valores opuestos."""
    importar(carteras)
    b = registro.brief("KB-100000")
    assert b is not None
    assert b["monto_deuda"] == 12345, "el bot negocia sobre el monto de la demo"
    assert b["probpago"] == 0.90
    # El más caro de equivocar: 35% de quita autorizada sobre una deuda ajena.
    assert b["descuento_recomendado"] == 0.0, (
        "el bot ofrece por teléfono el descuento calculado para OTRO deudor")
    assert b["departamento"] == "Salto"


def test_importar_la_cartera_tiene_efecto_sin_reiniciar(carteras):
    """El caché era una global que se llenaba una vez y no se soltaba nunca:
    el cliente importaba y el bot seguía con la cartera anterior hasta que
    alguien reiniciara el servicio."""
    primero = registro.brief("KB-100000")
    assert primero["monto_deuda"] == 999999          # todavía la de demo

    importar(carteras)
    segundo = registro.brief("KB-100000")
    assert segundo["monto_deuda"] == 12345, (
        "importar la cartera no tuvo ningún efecto: el caché nunca se soltó")


def test_reimportar_encima_tambien_se_nota(carteras):
    """Segunda importación sobre el mismo archivo: cambia el contenido pero
    no la ruta, así que un caché por nombre de archivo no lo vería."""
    importar(carteras)
    assert registro.brief("KB-100000")["monto_deuda"] == 12345

    corregida = REAL.replace("12345", "67890")
    importar(carteras, contenido=corregida)
    assert registro.brief("KB-100000")["monto_deuda"] == 67890


def test_un_deudor_que_no_esta_en_la_cartera_del_cliente_no_aparece(carteras):
    """Sin esto, un id que solo existe en la demo devolvía brief igual."""
    solo_demo = REAL.replace("KB-100000", "KB-777777")
    importar(carteras, contenido=solo_demo)
    assert registro.brief("KB-100000") is None
    assert registro.brief("KB-777777") is not None


# ---------------------------------------------------------------------------
# 3) Llamada entrante de alguien que no está en la cartera
# ---------------------------------------------------------------------------
def test_desconocido_no_recibe_descuento_inventado():
    from realtime import server
    b = server._brief_para_voz("", 50000)
    assert b["descuento_recomendado"] == 0.0, (
        "se autoriza una quita sobre una deuda de la que no sabemos nada")
    assert b["origen"] == "sin_cartera"
    # Sí se le sigue ofreciendo un camino: cuotas.
    assert b["plan_cuotas"] >= 1


def test_el_brief_dice_de_donde_salio(carteras):
    """Quien llama tiene que poder distinguir un brief real de uno mínimo —
    una campaña saliente no debería marcar nunca con el segundo."""
    from realtime import server
    importar(carteras)
    assert server._brief_para_voz("KB-100000", 0)["origen"] == "cartera"
    assert server._brief_para_voz("KB-NOEXISTE", 0)["origen"] == "sin_cartera"


def test_monto_basura_no_rompe_la_llamada():
    from realtime import server
    for malo in (None, "", "cincuenta mil", {}):
        b = server._brief_para_voz("KB-NOEXISTE", malo)
        assert b["monto_deuda"] == 0.0
        assert b["descuento_recomendado"] == 0.0


# ---------------------------------------------------------------------------
# 4) Campaña saliente: no se llama a quien no está en la cartera
# ---------------------------------------------------------------------------
@pytest.fixture()
def servidor_voz(tmp_path, monkeypatch):
    """El servidor realtime con plan de voz, Twilio "configurado" y una
    cartera propia — sin salir a la red en ningún caso.

    Los módulos de `kobra`/`realtime` se sacan de `sys.modules` para que el
    plan se lea de esta licencia y no de la del test anterior, y se REPONEN al
    terminar: borrarlos sin reponerlos deja a los tests siguientes con medio
    paquete recargado y fallando por el motivo equivocado.
    """
    pytest.importorskip("fastapi")
    previos = dict(sys.modules)
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", "secreto-de-prueba-cartera-voz")
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        monkeypatch.setenv(k, "de-prueba")

    for k in list(sys.modules):
        if k.startswith(("kobra", "realtime")):
            del sys.modules[k]

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from backend_venta import licencias as klic
    from kobra.edicion import CLAVE_TOKEN
    kconfig.guardar_extra(CLAVE_TOKEN, klic.emitir_licencia(
        "cliente-cartera", "pro", features=["voz", "copiloto"],
        secreto="secreto-de-prueba-cartera-voz"))

    from fastapi.testclient import TestClient

    from kobra import registro as reg
    from realtime import server

    cartera = tmp_path / "kobra_scored.csv"
    cartera.write_text(REAL, encoding="utf-8")
    monkeypatch.setattr(reg, "SCORED_CSV", str(cartera))
    monkeypatch.setattr(reg, "CARTERA_REAL_CSV", str(tmp_path / "no_hay.csv"))
    monkeypatch.setattr(reg, "ORIGEN_JSON", str(tmp_path / "no_hay.json"))
    reg._scored_cache = reg._scored_firma = None

    # Ninguna llamada de verdad: si el guardrail falla, se ve acá.
    disparadas = []
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: (
        disparadas.append(k.get("data")) or _RespuestaTwilio()))

    # Con token: acá se prueba el guardrail de cartera, no el candado de
    # acceso (ése vive en test_acceso_realtime.py).
    yield TestClient(server.app, headers=CABECERA_REALTIME), disparadas

    for k in list(sys.modules):
        if k.startswith(("kobra", "realtime")):
            del sys.modules[k]
    sys.modules.update(previos)


class _RespuestaTwilio:
    status_code = 201

    def json(self):
        return {"sid": "CA-de-prueba"}


def test_no_se_llama_a_un_deudor_que_no_esta_en_la_cartera(servidor_voz):
    """Un id con un typo, o de una lista vieja, salía a marcar igual: gastaba
    plata y del otro lado alguien escuchaba un reclamo sin verificar."""
    cli, disparadas = servidor_voz
    r = cli.post("/voz/llamar", data={"telefono": "+59899000000",
                                      "id_deudor": "KB-999999", "monto": "5000"})
    assert r.status_code == 404, r.text
    assert "no está en la cartera" in r.json()["error"]
    assert disparadas == [], "se disparó la llamada igual"


def test_un_deudor_de_la_cartera_sí_se_llama(servidor_voz):
    """El guardrail no puede volverse un muro: el caso normal sigue pasando."""
    cli, disparadas = servidor_voz
    r = cli.post("/voz/llamar", data={"telefono": "+59899000000",
                                      "id_deudor": "KB-100000"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert len(disparadas) == 1


def test_la_prueba_manual_sin_id_sigue_andando(servidor_voz):
    """Marcar el propio número para escuchar al agente (sin id_deudor) es el
    camino con el que se demuestra el producto. Ese ya no ofrece descuento,
    así que no hace falta bloquearlo."""
    cli, disparadas = servidor_voz
    r = cli.post("/voz/llamar", data={"telefono": "+59899000000"})
    assert r.status_code == 200, r.text
    assert len(disparadas) == 1


# ---------------------------------------------------------------------------
# 5) Que no vuelva a desconectarse
# ---------------------------------------------------------------------------
def test_registro_y_la_webapp_nombran_igual_los_archivos():
    """Las dos mitades tienen que seguir hablando del mismo archivo. Si
    alguien renombra uno de los dos lados, este test lo dice acá y no en la
    primera campaña de voz de un cliente."""
    api = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "webapp", "backend", "api.py"),
        encoding="utf-8").read()
    for nombre in ("kobra_cartera_real.csv", "origen_cartera.json"):
        assert nombre in api, f"la webapp ya no escribe {nombre}"
        assert nombre in (os.path.basename(registro.CARTERA_REAL_CSV) + " " +
                          os.path.basename(registro.ORIGEN_JSON)), (
            f"registro.py ya no lee {nombre}")
