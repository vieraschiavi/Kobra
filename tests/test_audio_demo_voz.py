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


def test_sin_api_key_no_genera_nada_y_no_rompe():
    r = gav.generar(api_key="", voice_id_gestor="")
    assert r["generados"] == 0 and r["omitidos"] == 0
    assert "motivo" in r


def test_con_key_genera_mp3_y_manifest_para_cada_turno(monkeypatch):
    monkeypatch.setattr(ktts, "sintetizar", lambda texto, voice_id, api_key=None,
                        modelo=None: {"ok": True, "audio": b"MP3-" + texto[:3].encode(),
                                      "caracteres": len(texto), "costo_est_usd": 0.001,
                                      "error": None})
    with tempfile.TemporaryDirectory() as tmp:
        r = gav.generar(voice_id_gestor="voz_gestor", voice_id_cliente="voz_cliente",
                        api_key="fakekey1234567890", out_dir=tmp)
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
        r = gav.generar(voice_id_gestor="v1", api_key="fakekey1234567890", out_dir=tmp)
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

    audio_dir = os.path.join(ROOT, "dashboard_estatico", "audio_demo")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            z = br.build_demo(tmp)
            import zipfile
            with zipfile.ZipFile(z) as zf:
                nombres = zf.namelist()
                assert "dashboard/audio_demo/manifest.js" in nombres
                assert "dashboard/audio_demo/turno_00.mp3" in nombres
        finally:
            import shutil
            shutil.rmtree(audio_dir, ignore_errors=True)
            shutil.rmtree(os.path.join(ROOT, "dist"), ignore_errors=True)
