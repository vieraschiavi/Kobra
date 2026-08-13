# © 2026 Martín Viera. Todos los derechos reservados.
"""Gestor/Cliente confundidos en el análisis de voz — y el sentimiento con ellos.

Reporte del usuario: en la pestaña de voz de Streamlit, la tabla "Transcripción
alineada por hablante" mostraba TODO como "Cliente" pese a que el texto era
claramente del gestor (agenda pagos, cita montos, ofrece descuentos). Las
tarjetas de emoción dominante también salían mal.

Causa raíz: `diarizar()` en modo mono (sin canales separados, como cualquier
grabación real de una central telefónica) etiqueta Gestor/Cliente por TONO
(F0) — una heurística que el propio código admite que "a menudo lo invierte".
Existía una corrección por CONTENIDO (`asignar_roles_por_contenido`), pero
solo estaba conectada en el backend FastAPI (`webapp/backend/api.py`), nunca
en `kobra.voz.transcribir_llamada`/`copiloto_desde_audio` — que es lo que usa
el dashboard de Streamlit (`app/app.py`), de donde salió la captura del bug.

Encima, el resumen acústico de `analizar_llamada` (el gráfico y las tarjetas
de "emoción dominante por hablante") se calculaba aparte, directo sobre el
tono — así que aunque se corrigiera la transcripción, el gráfico de arriba
podía seguir mostrando los roles al revés.

El arreglo: `copiloto_desde_audio` corrige por contenido (solo en mono; en
estéreo el canal ya es exacto) y propaga el MISMO mapeo tanto a los turnos de
texto como al resumen acústico (`_remapear_voz`), para que ambos coincidan.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import voz  # noqa: E402

try:
    import soundfile as sf
except Exception:
    sf = None


# --- La pieza pura: corregir por contenido -----------------------------------
def test_asignar_roles_por_contenido_corrige_la_inversion():
    # Diarización por tono etiquetó al revés: el texto de "Cliente" es
    # claramente del gestor, y el de "Gestor" es claramente del cliente.
    turnos = [
        {"hablante": "Cliente", "texto": "Le informamos que la fecha de pago vence el día 12"},
        {"hablante": "Gestor", "texto": "No puedo pagar eso, no tengo esa plata"},
        {"hablante": "Cliente", "texto": "Su deuda tiene un monto vencido de 17500 pesos"},
        {"hablante": "Gestor", "texto": "No me alcanza, cuanto seria el total"},
    ]
    corregidos = voz.asignar_roles_por_contenido(turnos)
    assert [t["hablante"] for t in corregidos] == ["Gestor", "Cliente", "Gestor", "Cliente"]
    # El texto no se toca, solo la etiqueta.
    assert [t["texto"] for t in corregidos] == [t["texto"] for t in turnos]


def test_asignar_roles_por_contenido_no_toca_si_no_hay_señal():
    turnos = [{"hablante": "Cliente", "texto": "hola qué tal"},
              {"hablante": "Gestor", "texto": "todo bien y usted"}]
    assert voz.asignar_roles_por_contenido(turnos) == turnos


def test_asignar_roles_por_contenido_no_toca_con_un_solo_hablante():
    turnos = [{"hablante": "Hablante", "texto": "le informamos su deuda"}]
    assert voz.asignar_roles_por_contenido(turnos) == turnos


def test_mapa_roles_es_none_sin_señal_clara():
    assert voz._mapa_roles_por_contenido([
        {"hablante": "A", "texto": "buen día"},
        {"hablante": "B", "texto": "buenas tardes"},
    ]) is None


# --- Propagar el mismo mapeo al resumen acústico ------------------------------
def test_remapear_voz_propaga_el_mismo_mapeo():
    resultado = {
        "timeline": [
            {"inicio": 0.0, "fin": 2.0, "hablante": "Cliente", "emocion_voz": "neutro"},
            {"inicio": 2.5, "fin": 4.5, "hablante": "Gestor", "emocion_voz": "frustracion"},
        ],
        "resumen_por_hablante": {
            "Cliente": {"segmentos": 1, "arousal_prom": 0.2, "valencia_prom": 0.1,
                       "emocion_dominante": "neutro"},
            "Gestor": {"segmentos": 1, "arousal_prom": 0.8, "valencia_prom": -0.5,
                      "emocion_dominante": "frustracion"},
        },
    }
    mapa = {"Cliente": "Gestor", "Gestor": "Cliente"}
    out = voz._remapear_voz(resultado, mapa)
    assert [s["hablante"] for s in out["timeline"]] == ["Gestor", "Cliente"]
    assert out["resumen_por_hablante"]["Gestor"]["emocion_dominante"] == "neutro"
    assert out["resumen_por_hablante"]["Cliente"]["emocion_dominante"] == "frustracion"


def test_remapear_voz_fusiona_si_dos_hablantes_crudos_caen_en_el_mismo_rol():
    resultado = {
        "timeline": [{"inicio": 0.0, "fin": 1.0, "hablante": "A", "emocion_voz": "neutro"},
                    {"inicio": 1.0, "fin": 2.0, "hablante": "B", "emocion_voz": "neutro"}],
        "resumen_por_hablante": {
            "A": {"segmentos": 2, "arousal_prom": 0.4, "valencia_prom": 0.0,
                 "emocion_dominante": "neutro"},
            "B": {"segmentos": 1, "arousal_prom": 0.8, "valencia_prom": -0.8,
                 "emocion_dominante": "enojo"},
        },
    }
    out = voz._remapear_voz(resultado, {"A": "Gestor", "B": "Gestor"})
    assert set(out["resumen_por_hablante"]) == {"Gestor"}
    assert out["resumen_por_hablante"]["Gestor"]["segmentos"] == 3
    # Domina "A" (2 segmentos) sobre "B" (1 segmento).
    assert out["resumen_por_hablante"]["Gestor"]["emocion_dominante"] == "neutro"


# --- End-to-end: copiloto_desde_audio con diarización mono al revés ----------
_SEGMENTOS_CRUDOS_INVERTIDOS = [
    voz.Segmento(0.0, 2.0, "Cliente"),   # en realidad es el GESTOR
    voz.Segmento(2.5, 4.5, "Gestor"),    # en realidad es el CLIENTE
    voz.Segmento(5.0, 7.0, "Cliente"),   # GESTOR
    voz.Segmento(7.5, 9.5, "Gestor"),    # CLIENTE
]
_WHISPER_FALSO = [
    {"start": 0.0, "end": 2.0, "text": "Le informamos que la fecha de pago vence el día 12"},
    {"start": 2.5, "end": 4.5, "text": "No puedo pagar eso, no tengo esa plata"},
    {"start": 5.0, "end": 7.0, "text": "Su deuda tiene un monto vencido de 17500 pesos"},
    {"start": 7.5, "end": 9.5, "text": "No me alcanza, cuanto seria el total"},
]


def _wav_mono(tmp_path, dur=10.0, sr=8000):
    rng = np.random.default_rng(0)
    y = (0.05 * rng.standard_normal(int(dur * sr))).astype(np.float32)
    path = str(tmp_path / "call.wav")
    sf.write(path, y, sr)
    return path


def test_copiloto_desde_audio_corrige_diarizacion_mono_por_contenido(tmp_path, monkeypatch):
    if sf is None:
        pytest.skip("soundfile no disponible")
    wav = _wav_mono(tmp_path)

    # Antes del fix: la diarización cruda (por tono) tiene los roles al revés
    # — lo confirma esta misma fixture (documenta el bug reportado).
    crudos = {s.hablante for s in _SEGMENTOS_CRUDOS_INVERTIDOS}
    assert crudos == {"Cliente", "Gestor"}

    monkeypatch.setattr(voz, "diarizar", lambda *a, **k: _SEGMENTOS_CRUDOS_INVERTIDOS)
    monkeypatch.setattr(voz, "_whisper_segmentos", lambda *a, **k: _WHISPER_FALSO)

    res = voz.copiloto_desde_audio(wav)

    por_texto = {t["texto"]: t["hablante"] for t in res["turnos"]}
    assert por_texto["Le informamos que la fecha de pago vence el día 12"] == "Gestor"
    assert por_texto["Su deuda tiene un monto vencido de 17500 pesos"] == "Gestor"
    assert por_texto["No puedo pagar eso, no tengo esa plata"] == "Cliente"
    assert por_texto["No me alcanza, cuanto seria el total"] == "Cliente"

    # El resumen acústico (gráfico + tarjetas) queda consistente con la misma
    # corrección, no con el tono crudo.
    resumen = res["voz"]["resumen_por_hablante"]
    assert set(resumen) == {"Gestor", "Cliente"}
    assert resumen["Gestor"]["segmentos"] == 2
    assert resumen["Cliente"]["segmentos"] == 2
    assert {s["hablante"] for s in res["voz"]["timeline"]} == {"Gestor", "Cliente"}

    # Y el sentimiento en cascada: el texto del copiloto arma la conversación
    # con las etiquetas YA corregidas, así que el cliente no aparece
    # diciendo "le informamos su deuda" con signo de gestor.
    assert res["copiloto"] is not None
