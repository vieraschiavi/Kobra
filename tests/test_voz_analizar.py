# © 2026 Martín Viera. Todos los derechos reservados.
"""Tests de /api/voz/analizar: subir una grabación real (.wav/.mp3) desde el
dashboard debe analizarse (diarización + emoción acústica), no quedarse sin
responder. Bug real reportado: el cliente subía wav/mp3 y "no analiza"."""
import importlib
import io
import os
import sys

import numpy as np
import pytest
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    kauth.establecer_password("admin", "AdminTest123!")
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    return api, TestClient(api.app)


def _h_admin(c):
    r = c.post("/api/auth/login", json={"password": "AdminTest123!"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _grabacion(fmt="WAV", canales=2, dur_seg=2, sr=16000):
    """Genera una grabación sintética dual-channel (gestor/cliente) en
    memoria — suficiente para ejercitar diarización + prosodia real."""
    n = sr * dur_seg
    t = np.linspace(0, dur_seg, n)
    canal_a = (0.2 * np.sin(2 * np.pi * 120 * t)).astype("float32")
    canal_b = (0.15 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    y = np.stack([canal_a, canal_b], axis=1) if canales >= 2 else canal_a
    buf = io.BytesIO()
    sf.write(buf, y, sr, format=fmt)
    buf.seek(0)
    return buf.read()


def test_analizar_wav_devuelve_diarizacion_y_emocion(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/voz/analizar", headers=h,
              files={"archivo": ("llamada.wav", _grabacion("WAV"), "audio/wav")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["archivo"] == "llamada.wav"
    assert d["voz"]["canales"] == 2
    assert d["voz"]["modo_diarizacion"] == "dual-channel"
    assert d["voz"]["duracion_seg"] > 0
    assert isinstance(d["voz"]["timeline"], list)


def test_analizar_mp3_tambien_funciona(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/voz/analizar", headers=h,
              files={"archivo": ("llamada.mp3", _grabacion("MP3"), "audio/mpeg")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["voz"]["duracion_seg"] > 0


def test_extension_no_soportada_da_400(cliente):
    api, c = cliente
    h = _h_admin(c)
    r = c.post("/api/voz/analizar", headers=h,
              files={"archivo": ("nota.txt", b"hola", "text/plain")})
    assert r.status_code == 400


def test_requiere_sesion(cliente):
    api, c = cliente
    r = c.post("/api/voz/analizar",
              files={"archivo": ("llamada.wav", _grabacion("WAV"), "audio/wav")})
    assert r.status_code == 401


def test_no_deja_archivo_temporal(cliente, tmp_path):
    api, c = cliente
    h = _h_admin(c)
    c.post("/api/voz/analizar", headers=h,
          files={"archivo": ("llamada.wav", _grabacion("WAV"), "audio/wav")})
    scratch = os.path.join(api.DIR_DATOS, ".uploads")
    sobrantes = [f for f in os.listdir(scratch) if f.startswith("voz_")] if os.path.exists(scratch) else []
    assert sobrantes == []
