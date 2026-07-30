"""Capacidad de llamadas simultáneas del chatvoice / chatbot.

La pregunta del negocio era «¿cuántas llamadas atiende a la vez sin errores,
entrantes y salientes?». Antes no tenía respuesta: no había tope, no había
vencimiento de sesiones y el trabajo pesado corría en el event loop. Estos
tests fijan las cuatro conductas que se corrigieron, cada una con el defecto
real que la motivó.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import concurrencia as kconc   # noqa: E402


class Reloj:
    """Reloj falso: el vencimiento por inactividad se prueba sin esperar."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, seg):
        self.t += seg


# --- 1) Tope de conversaciones simultáneas ---------------------------------
def test_el_tope_por_default_es_50_gestores():
    """El plan comercial es «máximo 50 gestores»: el default del código tiene
    que ser ese número, no un valor cualquiera."""
    assert kconc.MAX_SIMULTANEAS == 50


def test_la_conversacion_51_se_rechaza_en_vez_de_degradar_a_las_50():
    """Sin tope, la llamada 51 entraba igual y hacía esperar a las 50 que ya
    estaban hablando. Una llamada rechazada se reintenta; una llamada
    degradada se pierde con el cliente adentro."""
    reg = kconc.RegistroSesiones("voz", maximo=50)
    for i in range(50):
        reg.abrir(f"call-{i}", lambda: object())
    assert reg.vivas() == 50
    with pytest.raises(kconc.LimiteAlcanzado):
        reg.abrir("call-50", lambda: object())
    assert reg.metricas()["rechazadas"] == 1
    # Se libera una y entra la siguiente: el cupo vuelve al pool.
    reg.cerrar("call-0")
    reg.abrir("call-50", lambda: object())
    assert reg.vivas() == 50


def test_reabrir_una_conversacion_en_curso_no_consume_otro_cupo():
    """Twilio reintenta el webhook con el mismo CallSid: eso no es una llamada
    nueva y no puede comerse un cupo cada vez."""
    reg = kconc.RegistroSesiones("voz", maximo=2)
    reg.abrir("A", lambda: 1)
    reg.abrir("B", lambda: 2)
    reg.abrir("A", lambda: 3)          # mismo CallSid, no debe explotar
    assert reg.vivas() == 2


def test_la_fabrica_no_se_ejecuta_cuando_no_hay_cupo():
    """Construir la sesión lee la cartera: sin cupo, no se gasta ese trabajo."""
    reg = kconc.RegistroSesiones("voz", maximo=1)
    reg.abrir("A", lambda: 1)
    llamadas = []
    with pytest.raises(kconc.LimiteAlcanzado):
        reg.abrir("B", lambda: llamadas.append(1))
    assert llamadas == []


# --- 2) Vencimiento por inactividad ----------------------------------------
def test_la_llamada_abandonada_libera_su_cupo():
    """El caso medido: 500 llamadas abandonadas tras el saludo dejaban 500
    sesiones vivas para siempre. En telefonía el abandono es la norma — el
    deudor corta apenas escucha «cobranzas» — así que sin vencimiento el
    servidor se llena solo con llamadas que ya no existen."""
    reloj = Reloj()
    reg = kconc.RegistroSesiones("voz", maximo=50, ttl_seg=900, reloj=reloj)
    for i in range(50):
        reg.abrir(f"aband-{i}", lambda: object())
    assert reg.vivas() == 50

    reloj.avanzar(901)                 # 15 minutos sin un solo turno
    assert reg.vivas() == 0
    assert reg.metricas()["vencidas_por_inactividad"] == 50
    reg.abrir("nueva", lambda: object())   # el cupo volvió


def test_una_llamada_larga_pero_activa_no_se_corta():
    """El vencimiento mide INACTIVIDAD, no duración: una negociación de media
    hora con turnos cada dos minutos no se puede cortar sola."""
    reloj = Reloj()
    reg = kconc.RegistroSesiones("voz", ttl_seg=900, reloj=reloj)
    reg.abrir("larga", lambda: "sesion")
    for _ in range(15):                # 30 minutos, un turno cada 2
        reloj.avanzar(120)
        assert reg.obtener("larga") == "sesion"
    assert reg.vivas() == 1


# --- 3) El trabajo pesado no corre en el event loop ------------------------
@pytest.mark.parametrize("ruta,payload", [
    ("/whatsapp/webhook", {"json": {"sesion": "s", "id_deudor": "KB-1"}}),
    ("/voz/entrante", {"data": {"CallSid": "CA1"}}),
])
def test_las_conversaciones_simultaneas_no_se_atienden_de_a_una(ruta, payload):
    """El defecto de fondo, medido de punta a punta.

    Redactar un turno con LLM es una espera de red bloqueante dentro de un
    handler `async def`: corre EN el event loop, así que mientras una llamada
    espera al modelo, ninguna otra avanza. Con un LLM de 300 ms y 50
    conversaciones simultáneas eso daba 15,10 s (50 × 0,3 — serialización
    perfecta) contra 0,66 s mandando el turno a un hilo. Con ANTHROPIC_API_KEY
    puesta, que es como se vende el producto, el techo real no eran 50
    llamadas: eran 2 o 3.

    Acá se simula el LLM con 200 ms y 10 conversaciones a la vez: en serie
    serían ≥2 s; concurrentes, apenas más de 200 ms.
    """
    import asyncio
    import time

    httpx = pytest.importorskip("httpx")
    from kobra import gestor_ia
    from realtime import server

    LAT, N = 0.2, 10
    original = gestor_ia.SesionGestorIA.responder

    def lento(self, mensaje=None):
        time.sleep(LAT)                      # exactamente lo que hace requests.post
        return {"texto": "hola", "estado": "saludo", "fin": False, "campos_erp": None}

    gestor_ia.SesionGestorIA.responder = lento
    try:
        async def _correr():
            await server._preparar_capacidad()
            transporte = httpx.ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transporte,
                                         base_url="http://t", timeout=60) as c:
                t0 = time.perf_counter()
                r = await asyncio.gather(*[
                    c.post(f"{ruta}?call=CA{i}",
                           **{k: (dict(v, sesion=f"s{i}") if k == "json"
                                  else dict(v, CallSid=f"CA{i}"))
                              for k, v in payload.items()})
                    for i in range(N)])
                return time.perf_counter() - t0, r

        dt, respuestas = asyncio.run(_correr())
    finally:
        gestor_ia.SesionGestorIA.responder = original
        server._SESIONES_VOZ = kconc.RegistroSesiones("voz")
        server._SESIONES_WA = kconc.RegistroSesiones("whatsapp")

    assert all(x.status_code == 200 for x in respuestas)
    assert dt < LAT * N / 2, (
        f"{ruta}: {N} conversaciones tardaron {dt:.2f}s con turnos de {LAT}s — "
        f"se están atendiendo de a una en el event loop")


def test_el_threadpool_alcanza_para_el_tope_de_llamadas():
    """anyio trae 40 hilos por default: con 50 llamadas simultáneas, 10
    quedarían encoladas sin que nada lo diga."""
    import anyio.to_thread

    async def _correr():
        from realtime import server
        await server._preparar_capacidad()
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    import anyio
    assert anyio.run(_correr) >= kconc.MAX_SIMULTANEAS


# --- 4) Archivos temporales que no se pisan --------------------------------
def test_dos_subidas_con_el_mismo_nombre_van_a_archivos_distintos():
    """Se guardaba en /tmp/<el nombre que manda el cliente>. Medido con 30
    subidas simultáneas de «grabacion.wav»: 7 respuestas salieron mal — unas
    con HTTP 400 por WAV truncado y otras devolviendo el análisis de OTRA
    llamada (se subió 1,5 s de audio y contestó 1,3 s). En un producto de
    calidad de llamadas eso es lo peor que puede pasar: sale mal en silencio.
    Con nombres únicos, 30/30 correctas."""
    from realtime.server import _borrar, _guardar_temporal
    rutas = [_guardar_temporal(b"audio-" + str(i).encode(), "grabacion.wav", "call.wav")
             for i in range(30)]
    try:
        assert len(set(rutas)) == 30, "dos subidas fueron al mismo archivo"
        for i, r in enumerate(rutas):
            assert r.endswith(".wav")
            with open(r, "rb") as f:
                assert f.read() == b"audio-" + str(i).encode()
    finally:
        for r in rutas:
            _borrar(r)


def test_el_nombre_del_cliente_no_decide_donde_se_escribe():
    """El nombre del archivo llega de afuera: solo se conserva la extensión."""
    from realtime.server import _borrar, _guardar_temporal
    for nombre in ("../../etc/passwd.wav", "/etc/algo.wav", "raro.wav\x00.txt", None):
        ruta = _guardar_temporal(b"x", nombre, "call.wav")
        try:
            assert os.path.dirname(ruta) == os.path.realpath(
                os.path.dirname(ruta)), "la ruta salió del directorio temporal"
            assert os.path.basename(ruta).startswith("kobra_")
        finally:
            _borrar(ruta)


# --- 5) El tope también vale para las campañas salientes -------------------
def test_la_campania_saliente_no_puede_pedir_mas_lineas_que_el_tope():
    """`--lineas` se recortaba a 50 solo en el CLI. Llamando a la función
    —que es lo que hace el dashboard— entraban 200 líneas simultáneas
    (medido: pico 200)."""
    import asyncio

    from realtime import voicebot
    m = asyncio.run(voicebot.correr_campania(
        [], lineas=200, respetar_no_contactar=False))
    assert m["lineas"] == kconc.MAX_SIMULTANEAS
    m = asyncio.run(voicebot.correr_campania(
        [], lineas=0, respetar_no_contactar=False))
    assert m["lineas"] == 1, "0 líneas dejaría la campaña colgada para siempre"


# --- 6) Lo que se le informa al que opera ----------------------------------
def test_capacidad_total_no_promete_de_mas_con_varios_workers():
    """El tope es POR PROCESO. Con 4 workers la capacidad se multiplica, y eso
    tiene que decirse explícito para no vender 4× de más sin la RAM detrás."""
    c = kconc.capacidad_total(workers=4)
    assert c["por_worker"] == kconc.MAX_SIMULTANEAS
    assert c["simultaneas"] == kconc.MAX_SIMULTANEAS * 4
    assert kconc.capacidad_total()["simultaneas"] == kconc.MAX_SIMULTANEAS


def test_el_endpoint_capacidad_dice_cuanto_queda_libre():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from realtime import server
    c = fastapi_testclient.TestClient(server.app)
    r = c.get("/capacidad")
    assert r.status_code == 200
    d = r.json()
    assert d["limite_por_worker"] == kconc.MAX_SIMULTANEAS
    for canal in ("voz", "whatsapp", "copiloto_en_vivo"):
        assert d[canal]["libres"] + d[canal]["en_curso"] == kconc.MAX_SIMULTANEAS


def test_el_servidor_sube_el_keepalive_de_uvicorn():
    """Con el default de 5 s, uvicorn cerraba la conexión ociosa mientras el
    servidor estaba ocupado y la llamada se caía a mitad de la negociación.
    Medido con 100 conversaciones simultáneas: 5 a 13 caídas con 5 s, 0 con
    120 s — mismo servidor, misma carga, misma prueba."""
    import inspect

    from realtime import server
    fuente = inspect.getsource(server)
    assert "timeout_keep_alive=keep_alive" in fuente
    assert 'KOBRA_KEEPALIVE_SEG", "120"' in fuente
