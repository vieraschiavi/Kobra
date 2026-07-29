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

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data import generar_audio_demo_voz as gav  # noqa: E402
from kobra import voz_tts as ktts  # noqa: E402


def test_leer_guion_extrae_el_guion_real():
    """Lee el guion de dashboard_estatico/guiones.js — misma fuente que consume
    el navegador, para que nunca se desincronicen texto y audio."""
    turnos = gav.leer_guion()
    assert len(turnos) == 9
    assert turnos[0] == {"who": "ia", "text":
        "Buenos días, hablo de MV Kobra AI en representación de su entidad "
        "financiera. ¿Hablo con Juan Pérez?"}
    assert turnos[1] == {"who": "cliente", "text": "Sí, soy yo."}
    quienes = {t["who"] for t in turnos}
    assert quienes == {"ia", "cliente"}


def test_hay_guion_en_los_tres_idiomas():
    """Regresión: el guion estaba solo en castellano, así que elegir portugués
    o inglés en el sitio no cambiaba ni el texto ni el audio de la llamada."""
    guiones = gav.leer_guiones()
    assert set(guiones) == set(gav.IDIOMAS)
    largos, whos = set(), set()
    for idioma in gav.IDIOMAS:
        turnos = gav.leer_guion(idioma)
        largos.add(len(turnos))
        whos.add(tuple(t["who"] for t in turnos))
        assert all(t["text"].strip() for t in turnos), idioma
        assert guiones[idioma]["whatsapp"], idioma
        assert guiones[idioma]["ui"]["etiqueta_cliente"], idioma
    # Mismo número de turnos y mismos roles en los tres: si no, el manifest de
    # audio de un idioma no encajaría con el guion que se muestra.
    assert len(largos) == 1 and len(whos) == 1


def test_los_tres_idiomas_dicen_cosas_distintas():
    """Un guion 'traducido' que quedó copiado del castellano no se nota hasta
    que alguien escucha el audio."""
    textos = {i: " ".join(t["text"] for t in gav.leer_guion(i))
              for i in gav.IDIOMAS}
    assert len({textos[i] for i in gav.IDIOMAS}) == 3
    assert "instituição" in textos["pt"]
    assert "instalments" in textos["en"]


def test_idioma_sin_guion_falla_claro():
    with pytest.raises(ValueError, match="Idioma sin guion"):
        gav.leer_guion("fr")


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
    # Regresión: asetrate es relativo al sample rate de ENTRADA. El material
    # de origen está a 44,1 kHz, así que sin remuestrear ANTES el factor
    # efectivo era (24000·f)/44100 — la voz salía muchísimo más grave de lo
    # pedido. El aresample tiene que ir antes del asetrate.
    assert "aresample=24000,asetrate=24000*{factor}" in fuente
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


def test_descarta_la_toma_donde_el_modelo_se_traba_repitiendo():
    """Regresión: 'Sí, confirmo.' (13 caracteres) salió como 4,4 s de audio —
    el modelo se trabó repitiendo y ese turno quedó inservible en la demo. El
    largo del audio tiene que ser coherente con el del texto."""
    from kobra import voz_clon_local as klocal
    sr = 24000
    assert klocal._toma_creible(int(sr * 1.2), sr, "Sí, confirmo.") is True
    assert klocal._toma_creible(int(sr * 4.4), sr, "Sí, confirmo.") is False
    # Una frase larga sí puede durar varios segundos: el tope es proporcional.
    larga = "Lo contacto por un saldo pendiente de 6.000 pesos con más de 60 días."
    assert klocal._toma_creible(int(sr * 7.0), sr, larga) is True
    # Y no divide por cero si el motor devuelve un sample rate raro.
    assert klocal._toma_creible(0, 0, "hola") is True


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
        assert r["manifest"][0] == {"i": 0, "who": "ia", "archivo": "turno_00.mp3"}

        gav.escribir_manifest({"es": r["manifest"]}, destino=tmp)
        manifest_js = open(os.path.join(tmp, "manifest.js")).read()
        assert "window.AUDIO_DEMO_MANIFEST" in manifest_js
        data = json.loads(manifest_js.split("=", 1)[1].strip().rstrip(";"))
        # Un manifest por idioma, no una lista suelta: el HTML elige la rama.
        assert set(data) == {"es"} and len(data["es"]) == 9


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
    assert '<script src="guiones.js"></script>' in html
    assert "AUDIO_MANIFEST_POR_INDICE" in html
    assert "playPremium" in html
    # El MP3 se busca en la carpeta del idioma activo, no en la raíz: los tres
    # idiomas tienen archivos con el mismo nombre y se pisarían.
    assert "'audio_demo/'+IDIOMA+'/'+archivo" in html
    # Y la rama del manifest se elige por idioma.
    assert "todo[IDIOMA]" in html


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
                assert "dashboard/guiones.js" in nombres
                for idioma in gav.IDIOMAS:
                    assert f"dashboard/audio_demo/{idioma}/turno_00.mp3" in nombres
        finally:
            shutil.rmtree(audio_dir, ignore_errors=True)
            shutil.rmtree(os.path.join(ROOT, "dist"), ignore_errors=True)
            if respaldo:
                shutil.copytree(os.path.join(respaldo, "audio_demo"), audio_dir)
                shutil.rmtree(respaldo, ignore_errors=True)


def test_el_build_sin_motor_no_borra_el_audio_versionado(monkeypatch, tmp_path):
    """Regresión: el audio pre-renderizado está versionado —lo sirve el sitio,
    no solo el ZIP— y `_prerenderizar_voz_demo()` empezaba borrándolo para
    regenerarlo. En una máquina sin motor de voz eso dejaba el árbol de trabajo
    sin los MP3 y el paquete sin voz, por un build que no tenía nada que ver.
    Ahora solo limpia si hay con qué regenerar."""
    spec = importlib.util.spec_from_file_location(
        "br_sin_motor", os.path.join(ROOT, "packaging", "build_release.py"))
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)

    from kobra import voz_clon_local as klocal
    for v in ("KOBRA_TTS_MOTOR", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_GESTOR"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(klocal, "motor_disponible", lambda: "")

    audio_dir = os.path.join(ROOT, "dashboard_estatico", "audio_demo")
    antes = sorted(os.listdir(audio_dir)) if os.path.isdir(audio_dir) else []
    br._prerenderizar_voz_demo()
    despues = sorted(os.listdir(audio_dir)) if os.path.isdir(audio_dir) else []
    assert despues == antes, "el build borró el audio que no podía regenerar"


def test_el_audio_del_demo_esta_versionado():
    """El sitio sirve estos MP3. Estuvieron en .gitignore y el demo hospedado
    nunca los tuvo: daban 404 y caía a la voz del navegador."""
    import subprocess
    rel = "dashboard_estatico/audio_demo"
    ignorado = subprocess.run(["git", "check-ignore", f"{rel}/es/turno_00.mp3"],
                              cwd=ROOT, capture_output=True).returncode == 0
    assert not ignorado, f"{rel} volvió a estar ignorado: el sitio no lo va a servir"
    for idioma in gav.IDIOMAS:
        carpeta = os.path.join(ROOT, rel, idioma)
        assert os.path.isdir(carpeta), f"falta el audio de {idioma}"
        mp3 = [f for f in os.listdir(carpeta) if f.endswith(".mp3")]
        assert len(mp3) == len(gav.leer_guion(idioma)), idioma
