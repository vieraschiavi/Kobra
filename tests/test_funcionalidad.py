# © 2026 Martín Viera. Todos los derechos reservados.
"""Eje FUNCIONALIDAD: que un error le diga al usuario qué hacer.

El hallazgo concreto salió probando la API con archivos inválidos, no leyendo
el código. Subir algo que no era audio devolvía:

    Error opening '/home/user/Kobra/.uploads/voz_c298d20c1004….wav':
    Format not recognised.

Tres problemas en una sola línea: le filtra al cliente la ruta interna del
servidor, le habla en inglés y en jerga de librería, y no le dice qué hacer.
Ahora dice qué archivo se espera y conserva la causa técnica sin rutas.

El resto del eje se audita acá también: que el núcleo no dependa de servicios
de pago para funcionar.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def api():
    pytest.importorskip("fastapi")
    from webapp.backend import api as mod
    return mod


# --- Los mensajes de error no filtran rutas del servidor -------------------
@pytest.mark.parametrize("crudo,esperado_fuera", [
    ("Error opening '/home/user/Kobra/.uploads/voz_c298d.wav': Format not recognised.",
     "/home/user"),
    (r"No such file: C:\Users\juan\cartera.xlsx", "C:\\Users"),
    ("falla en /var/data/kobra/outputs/x.csv linea 12", "/var/data"),
])
def test_el_detalle_del_error_no_expone_la_ruta_del_servidor(api, crudo, esperado_fuera):
    salida = api._detalle_sin_rutas(Exception(crudo))
    assert esperado_fuera not in salida, f"filtró la ruta: {salida}"
    assert "el archivo" in salida


def test_el_detalle_conserva_la_causa_tecnica(api):
    """Borrar el detalle entero sería peor: nadie podría diagnosticar. Lo que
    se saca es la ruta, no la explicación."""
    salida = api._detalle_sin_rutas(
        Exception("Error opening '/tmp/x.wav': Format not recognised."))
    assert "Format not recognised" in salida


@pytest.mark.parametrize("texto", [
    "columna faltante: monto",
    "la relacion 2/3 no es una ruta",
    "el valor 12/2026 tiene formato invalido",
])
def test_no_confunde_una_fraccion_ni_una_fecha_con_una_ruta(api, texto):
    """Un saneador demasiado entusiasta rompería mensajes que estaban bien."""
    assert api._detalle_sin_rutas(Exception(texto)) == texto


def test_el_detalle_se_acota(api):
    """Un traceback de pandas de 4.000 caracteres dentro de un cartel no es un
    mensaje: es ruido que tapa la parte accionable."""
    salida = api._detalle_sin_rutas(Exception("x" * 5000))
    assert len(salida) <= 200


# --- Cada error dice QUÉ HACER ---------------------------------------------
@pytest.fixture
def cliente():
    """La app tal como está importada, sin recargar módulos.

    A propósito NO se purga `sys.modules`: estos tests mandan archivos
    inválidos, que fallan antes de tocar ningún dato, así que no hace falta un
    directorio de datos propio. Y purgar tiene un costo que ya mordió:
    `test_kobra.py` liga `ProbPagoModel` al importarse, y si otro módulo de
    test borra `kobra.probpago` del caché, el `monkeypatch` de ese test toca un
    módulo nuevo mientras la clase sigue apuntando al viejo — el test empieza a
    fallar por una razón que no tiene nada que ver con lo que prueba.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from webapp.backend import api as mod
    token = mod._emitir_token("admin", mod.EMPRESA_DEFAULT)
    return TestClient(mod.app), {"Authorization": f"Bearer {token}"}


def test_subir_algo_que_no_es_audio_explica_que_se_espera(cliente):
    cli, h = cliente
    r = cli.post("/api/voz/analizar", headers=h,
                 files={"archivo": ("x.wav", b"esto no es audio", "audio/wav")})
    assert r.status_code == 400
    detalle = r.json()["detail"]
    assert ".wav" in detalle and ".mp3" in detalle, f"no dice qué subir: {detalle}"
    assert "/home" not in detalle and "/tmp" not in detalle, \
        f"filtra una ruta del servidor: {detalle}"


def test_subir_algo_que_no_es_planilla_explica_que_se_espera(cliente):
    cli, h = cliente
    r = cli.post("/api/cartera/importar", headers=h,
                 files={"archivo": ("c.xlsx", b"\x00\x01binario", "application/vnd.ms-excel")})
    assert r.status_code in (400, 422)
    detalle = r.json()["detail"]
    assert ".csv" in detalle or ".xlsx" in detalle, f"no dice qué subir: {detalle}"


def test_ningun_error_de_usuario_devuelve_un_stack_trace(cliente):
    """Un `Traceback (most recent call last)` en pantalla no es un mensaje de
    error: es una falla que además delata la estructura del servidor."""
    cli, h = cliente
    pruebas = [
        ("POST", "/api/voz/analizar", {"files": {"archivo": ("x.wav", b"no", "audio/wav")}}),
        ("POST", "/api/cartera/importar", {"files": {"archivo": ("c.csv", b"\x00", "text/csv")}}),
        ("GET", "/api/deudor/NO-EXISTE", {}),
        ("GET", "/api/cartera?pagina=999999", {}),
        ("POST", "/api/licencia/activar", {"json": {"token": "no-es-un-token"}}),
    ]
    for metodo, ruta, kw in pruebas:
        r = cli.request(metodo, ruta, headers=h, **kw)
        cuerpo = r.text
        assert "Traceback" not in cuerpo, f"{ruta} devolvió un traceback"
        assert "File \"/" not in cuerpo, f"{ruta} devolvió rutas de código"


def test_el_token_vencido_dice_que_hacer(cliente):
    cli, _ = cliente
    r = cli.get("/api/kpis", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401
    assert "sesión" in r.json()["detail"].lower(), r.json()["detail"]


# --- El flujo principal no depende de servicios de pago --------------------
def test_el_nucleo_no_importa_ninguna_pasarela_de_pago():
    """El dashboard, el scoring y el negociador tienen que funcionar aunque no
    haya checkout configurado: si el motor dependiera de la pasarela, una
    instalación sin pagos no serviría para nada.

    Nota (portal de cobros): el portal MENCIONA MercadoPago porque arma el
    link de pago preconfigurado de la empresa — pero no importa ningún SDK ni
    lo necesita para funcionar (viene deshabilitado por default, ver el test
    de abajo). Por eso este chequeo mira los IMPORT, que es lo que crearía la
    dependencia, y no la palabra."""
    import re
    sospechosos = ("mercadopago", "stripe", "paypal", "dlocal")
    patron = re.compile(
        rf"^\s*(import\s+({'|'.join(sospechosos)})\b"
        rf"|from\s+({'|'.join(sospechosos)})\b)", re.I)
    hallazgos = []
    for base in ("kobra", "webapp/backend", "realtime"):
        for root, _, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                ruta = os.path.join(root, f)
                with open(ruta, encoding="utf-8", errors="replace") as fh:
                    for n, linea in enumerate(fh, 1):
                        if patron.search(linea):
                            hallazgos.append(f"{ruta}:{n}")
    assert not hallazgos, f"el núcleo importa una pasarela de pago: {hallazgos}"


def test_mercadopago_del_portal_es_opcional_y_arranca_apagado():
    """La garantía positiva que acompaña al test de arriba: sin configurar
    nada, MercadoPago está deshabilitado y el portal funciona igual (solo
    transferencia). Habilitarlo es una decisión de la empresa, no un
    requisito del producto."""
    import tempfile

    from kobra import portal_pagos as kportal
    with tempfile.TemporaryDirectory() as d:
        cfg = kportal.cargar_config(d)
        assert cfg["mercadopago"]["habilitado"] is False
        assert cfg["transferencia"]["habilitado"] is True


def test_el_pipeline_completo_corre_sin_ninguna_api_key(monkeypatch):
    """Primer valor sin configurar nada: sin key de LLM, sin Whisper, sin
    telefonía. Si alguna de esas fuera obligatoria, un usuario nuevo no podría
    ver nada hasta conseguirlas."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                "TWILIO_ACCOUNT_SID", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from kobra import copiloto
    r = copiloto.analizar_conversacion(
        "Gestor: Buenos días, le hablo por su cuenta.\n"
        "Cliente: No puedo pagar todo junto, ¿hay cuotas?\n"
        "Gestor: Sí, puedo ofrecerle tres cuotas.\n"
        "Cliente: Dale, acepto.", canal="llamada")
    assert r["calidad"]["score_total"] is not None
    assert r["copiloto"]["clima_emocional"] is not None
    assert isinstance(r["tecnicas"], dict)
