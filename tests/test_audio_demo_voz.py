"""Tests de la voz premium pre-renderizada del chatvoice de la demo offline
(data/generar_audio_demo_voz.py). Bug real reportado: el chatvoice de la demo
sonaba con la voz robótica del navegador (Web Speech API) y con latencia — no
la voz premium que se ve en el video de marketing. Este módulo sintetiza el
guion UNA vez con el mismo motor premium del producto (ElevenLabs,
kobra/voz_tts.py) y lo deja listo para que el HTML lo reproduzca como audio
real, sin romper el fallback a la voz del navegador cuando no hay API key."""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data import generar_audio_demo_voz as gav  # noqa: E402
from kobra import voz_tts as ktts  # noqa: E402


def test_leer_guion_extrae_el_call_script_real():
    """Lee el guion directamente del HTML — misma fuente que se ve en pantalla,
    para que nunca se desincronicen texto y audio."""
    turnos = gav.leer_guion()
    assert len(turnos) == 9
    assert turnos[0] == {"who": "ia", "text":
        "Buenos días, hablo de MV Kobra AI en representación de su entidad "
        "financiera. ¿Hablo con Juan Pérez?"}
    assert turnos[1] == {"who": "cliente", "text": "Sí, soy yo."}
    quienes = {t["who"] for t in turnos}
    assert quienes == {"ia", "cliente"}


def test_sin_api_key_no_genera_nada_y_no_rompe(monkeypatch):
    from kobra import voz_clon_local as klocal
    monkeypatch.setattr(klocal, "motor_disponible", lambda: "")
    r = gav.generar(api_key="", voice_id_gestor="")
    assert r["generados"] == 0 and r["omitidos"] == 0
    assert "motivo" in r


# --- elección de motor: gratis primero, y nunca gastar sin permiso ----------
_K = "k" * 20


def _elegir(monkeypatch, local, key="", vid="", forzar=None):
    from kobra import voz_clon_local as klocal
    for v in ("KOBRA_TTS_MOTOR", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_GESTOR"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(klocal, "motor_disponible", lambda: local)
    return gav.elegir_motor(api_key=key, voice_id_gestor=vid, forzar=forzar)[1]


def test_prefiere_el_clonador_local_gratuito(monkeypatch):
    """Con ambos disponibles gana el local: es gratis y no manda la voz afuera."""
    assert _elegir(monkeypatch, "chatterbox", _K, "vid") == "local"
    assert _elegir(monkeypatch, "chatterbox") == "local"


def test_cae_a_elevenlabs_solo_si_no_hay_local(monkeypatch):
    assert _elegir(monkeypatch, "", _K, "vid") == "elevenlabs"
    assert _elegir(monkeypatch, "") == ""


def test_forzar_local_sin_motor_no_gasta_en_elevenlabs(monkeypatch):
    """Regresión: forzar 'local' es pedir explícitamente NO gastar. Caer al
    motor pago en ese caso le costaría plata a alguien que pidió lo contrario."""
    assert _elegir(monkeypatch, "", _K, "vid", forzar="local") == ""


def test_forzar_elevenlabs_lo_respeta(monkeypatch):
    assert _elegir(monkeypatch, "chatterbox", _K, "vid", forzar="elevenlabs") == "elevenlabs"


def test_usa_el_modelo_multilingue_no_el_ingles():
    """Regresión: se cargaba ChatterboxTTS (modelo de inglés) y se le pasaba
    texto en castellano, así que lo pronunciaba con fonética inglesa — sonaba
    raro y perdía el acento. Tiene que cargar el modelo MULTILINGÜE y pasarle
    el idioma."""
    import inspect
    from kobra import voz_clon_local as klocal
    fuente = inspect.getsource(klocal._cargar)
    assert "ChatterboxMultilingualTTS" in fuente
    assert "from chatterbox.tts import ChatterboxTTS" not in fuente
    # Y el idioma tiene que viajar hasta generate() como language_id.
    assert "language_id=idioma" in inspect.getsource(klocal.sintetizar)


def test_el_generador_pasa_el_idioma_al_motor_local(monkeypatch):
    """El idioma no puede quedar librado al default: el producto también
    vende en portugués."""
    from kobra import voz_clon_local as klocal
    vistos = []

    def fake_sint(texto, referencia=None, idioma="es", **kw):
        vistos.append(idioma)
        return {"ok": True, "audio": b"X", "caracteres": len(texto),
                "costo_est_usd": 0.0, "error": None}

    monkeypatch.setattr(klocal, "motor_disponible", lambda: "chatterbox")
    monkeypatch.setattr(klocal, "sintetizar", fake_sint)
    with tempfile.TemporaryDirectory() as tmp:
        gav.generar(out_dir=tmp, idioma="pt")
    assert vistos and set(vistos) == {"pt"}


def test_gestor_y_cliente_no_usan_la_misma_voz(monkeypatch):
    """Regresión: los dos roles se sintetizaban con la misma muestra clonada,
    así que la 'llamada' era una sola persona hablando sola — y el cliente,
    que en el guion es Juan Pérez (varón), sonaba con la voz femenina de la
    locución oficial. Cada rol tiene que recibir una referencia distinta."""
    from kobra import voz_clon_local as klocal
    refs = {}

    def fake_sint(texto, referencia=None, idioma="es", **kw):
        refs[texto] = referencia
        return {"ok": True, "audio": b"X", "caracteres": len(texto),
                "costo_est_usd": 0.0, "error": None}

    monkeypatch.setattr(klocal, "motor_disponible", lambda: "chatterbox")
    monkeypatch.setattr(klocal, "sintetizar", fake_sint)
    monkeypatch.setattr(klocal, "referencia_grave",
                        lambda origen=None, factor=0.74: "/ref/grave.wav")
    with tempfile.TemporaryDirectory() as tmp:
        gav.generar(out_dir=tmp, referencia="/ref/oficial.wav")

    turnos = gav.leer_guion()
    por_rol = {t["who"]: refs[t["text"]] for t in turnos}
    assert por_rol["ia"] == "/ref/oficial.wav"
    assert por_rol["cliente"] == "/ref/grave.wav"
    assert por_rol["ia"] != por_rol["cliente"]
    # Y todos los turnos del cliente comparten esa voz (no una por turno).
    del_cliente = {refs[t["text"]] for t in turnos if t["who"] == "cliente"}
    assert del_cliente == {"/ref/grave.wav"}


def test_referencia_grave_baja_el_tono_de_la_muestra():
    """La voz del cliente sale de la misma locución bajada de tono: `asetrate`
    baja tono y formantes juntos (eso es lo que la vuelve masculina) y
    `atempo` devuelve la duración original — sin él quedaría en cámara lenta."""
    import inspect
    from kobra import voz_clon_local as klocal
    fuente = inspect.getsource(klocal.referencia_grave)
    assert "asetrate" in fuente and "atempo" in fuente
    # El centinela no es una ruta: no se puede usar como origen del ffmpeg.
    assert "is not SIN_CLONAR" in fuente


def test_parte_el_texto_en_frases_manejables():
    """Regresión: una frase de 112 caracteres tumbaba el proceso entero
    (crash duro, no excepción) al sintetizarla de una. Se parte por fin de
    oración, y por coma si una oración sola sigue siendo muy larga."""
    from kobra import voz_clon_local as klocal
    tope = 90

    culpable = ("Excelente. Quedó registrado el acuerdo de pago en 3 cuotas. "
                "Muchas gracias por su tiempo, que tenga un buen día.")
    partes = klocal._partir_en_frases(culpable, tope)
    assert len(partes) > 1
    assert all(len(p) <= tope for p in partes)

    # Una sola oración larguísima se corta por comas, no queda entera.
    larga = ("Puedo ofrecerle cancelar hoy con un 5% de descuento, quedando en "
             "5.700 pesos, o dividirlo en 3 cuotas de 1.900 pesos sin recargo.")
    assert all(len(p) <= tope for p in klocal._partir_en_frases(larga, tope))

    # No se pierde ni se duplica texto: las partes reconstruyen el original.
    assert " ".join(klocal._partir_en_frases(culpable, tope)) == culpable
    # Texto corto queda tal cual, en una sola parte.
    assert klocal._partir_en_frases("Sí, soy yo.", tope) == ["Sí, soy yo."]


def test_motor_local_sin_dependencias_no_rompe(monkeypatch):
    """Si no hay motor instalado, sintetizar devuelve ok=False con el motivo,
    nunca una excepción que corte el build."""
    from kobra import voz_clon_local as klocal
    monkeypatch.setattr(klocal, "motor_disponible", lambda: "")
    r = klocal.sintetizar("hola")
    assert r["ok"] is False and r["costo_est_usd"] == 0.0 and r["error"]


def test_con_key_genera_mp3_y_manifest_para_cada_turno(monkeypatch):
    monkeypatch.setattr(ktts, "sintetizar", lambda texto, voice_id, api_key=None,
                        modelo=None: {"ok": True, "audio": b"MP3-" + texto[:3].encode(),
                                      "caracteres": len(texto), "costo_est_usd": 0.001,
                                      "error": None})
    with tempfile.TemporaryDirectory() as tmp:
        r = gav.generar(voice_id_gestor="voz_gestor", voice_id_cliente="voz_cliente",
                        api_key="fakekey1234567890", out_dir=tmp, motor="elevenlabs")
        assert r["generados"] == 9 and r["omitidos"] == 0
        assert os.path.exists(os.path.join(tmp, "turno_00.mp3"))
        assert os.path.exists(os.path.join(tmp, "turno_08.mp3"))
        manifest_js = open(os.path.join(tmp, "manifest.js")).read()
        assert "window.AUDIO_DEMO_MANIFEST" in manifest_js
        data = json.loads(manifest_js.split("=", 1)[1].strip().rstrip(";"))
        assert len(data) == 9
        assert data[0]["archivo"] == "turno_00.mp3"
        assert data[0]["who"] == "ia"


def test_turno_que_falla_sintetizar_no_frena_a_los_demas(monkeypatch):
    """Si ElevenLabs falla para un turno puntual, el resto igual se genera —
    ese turno específico cae al fallback de navegador en el HTML."""
    def fake(texto, voice_id, api_key=None, modelo=None):
        ok = texto != "Sí, soy yo."
        return {"ok": ok, "audio": b"X" if ok else None, "caracteres": len(texto),
                "costo_est_usd": 0.001 if ok else 0.0, "error": None if ok else "boom"}
    monkeypatch.setattr(ktts, "sintetizar", fake)
    with tempfile.TemporaryDirectory() as tmp:
        r = gav.generar(voice_id_gestor="v1", api_key="fakekey1234567890", out_dir=tmp,
                        motor="elevenlabs")
        assert r["generados"] == 8 and r["omitidos"] == 1


def test_dashboard_estatico_carga_manifest_con_fallback_seguro():
    """El HTML incluye <script src="audio_demo/manifest.js"> — si no existe
    (build sin ElevenLabs), el <script> simplemente no carga nada (sin romper
    la página) y AUDIO_MANIFEST_POR_INDICE queda vacío en el JS."""
    html = open(os.path.join(ROOT, "dashboard_estatico", "index.html"),
               encoding="utf-8").read()
    assert '<script src="audio_demo/manifest.js"></script>' in html
    assert "AUDIO_MANIFEST_POR_INDICE" in html
    assert "playPremium" in html


def test_build_demo_bundlea_audio_premium_cuando_hay_key(monkeypatch):
    """packaging/build_release.py::build_demo() pre-renderiza y empaqueta el
    audio premium cuando el entorno de build tiene la key configurada."""
    spec = importlib.util.spec_from_file_location(
        "br_test", os.path.join(ROOT, "packaging", "build_release.py"))
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)

    monkeypatch.setattr(ktts, "sintetizar", lambda texto, voice_id, api_key=None,
                        modelo=None: {"ok": True, "audio": b"MP3-DATA",
                                      "caracteres": len(texto), "costo_est_usd": 0.001,
                                      "error": None})
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fakekey1234567890")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID_GESTOR", "voz_gestor_demo")
    # Sin esto ganaría el clonador local (si está instalado) y el test se
    # pondría a sintetizar de verdad: minutos por frase.
    monkeypatch.setenv("KOBRA_TTS_MOTOR", "elevenlabs")

    import shutil
    audio_dir = os.path.join(ROOT, "dashboard_estatico", "audio_demo")
    # build_demo() regenera el audio en el árbol de trabajo (es lo que hace un
    # build de verdad). Si ya había audio generado a mano — que cuesta minutos
    # de CPU — el test lo borraría. Se guarda aparte y se restaura al final.
    respaldo = None
    if os.path.isdir(audio_dir):
        respaldo = tempfile.mkdtemp()
        shutil.copytree(audio_dir, os.path.join(respaldo, "audio_demo"))
    with tempfile.TemporaryDirectory() as tmp:
        try:
            z = br.build_demo(tmp)
            import zipfile
            with zipfile.ZipFile(z) as zf:
                nombres = zf.namelist()
                assert "dashboard/audio_demo/manifest.js" in nombres
                assert "dashboard/audio_demo/turno_00.mp3" in nombres
        finally:
            shutil.rmtree(audio_dir, ignore_errors=True)
            shutil.rmtree(os.path.join(ROOT, "dist"), ignore_errors=True)
            if respaldo:
                shutil.copytree(os.path.join(respaldo, "audio_demo"), audio_dir)
                shutil.rmtree(respaldo, ignore_errors=True)
