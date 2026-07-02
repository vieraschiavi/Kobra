"""
Kobra · Tests
=============
Pruebas rápidas del pipeline end-to-end: dataset, ProbPago, negociador y
copiloto de negociación. Corren en segundos con un dataset pequeño.

    pytest -q
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.generate_dataset import generar
from kobra.probpago import ProbPagoModel
from kobra import negociador, copiloto, analitica


def _df():
    return generar(n=1500, seed=7)


def test_dataset_schema():
    df = _df()
    for col in ["id_deudor", "monto_deuda", "dias_mora", "pago", "tramo_mora"]:
        assert col in df.columns
    assert df["pago"].isin([0, 1]).all()
    assert (df["monto_deuda"] > 0).all()
    assert 0.2 < df["pago"].mean() < 0.9   # tasa de pago razonable


def test_probpago_entrena_y_scorea():
    df = _df()
    model = ProbPagoModel().fit(df)
    assert model.metrics["auc_roc"] > 0.7          # el modelo aprende señal
    scored = model.score(df)
    assert scored["probpago"].between(0, 1).all()
    assert set(scored["segmento_propension"].dropna().unique()) <= {"Alta", "Media", "Baja"}


def test_negociador_recomienda():
    df = _df()
    scored = ProbPagoModel().fit(df).score(df)
    full = negociador.recomendar(scored)
    assert (full["valor_esperado_recupero"] >= 0).all()
    assert full["prioridad"].nunique() == len(full)   # prioridad única
    assert full["guion"].str.len().gt(10).all()       # todos tienen guion


def test_copiloto_sentimiento():
    pos = copiloto.analizar_sentimiento("Perfecto, muchas gracias, acepto el plan")
    neg = copiloto.analizar_sentimiento("No puedo pagar, estoy sin trabajo y harto")
    assert pos.score > 0 and pos.etiqueta == "positivo"
    assert neg.score < 0 and neg.etiqueta == "negativo"


def test_copiloto_analisis_completo():
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "ejemplo_whatsapp.txt")
    texto = open(ruta, encoding="utf-8").read()
    res = copiloto.analizar_conversacion(texto, canal="whatsapp", probpago=0.7,
                                         estrategia="Plan de cuotas")
    assert res["meta"]["mensajes"] > 5
    assert 0 <= res["calidad"]["score_total"] <= 100
    assert any(res["tecnicas"].values())               # detecta alguna técnica
    assert len(res["copiloto"]["sugerencias"]) >= 1
    assert res["copiloto"]["proxima_frase"]


def test_copiloto_parser_plano():
    conv = copiloto.parsear_conversacion(
        "Gestor: Hola, buenos dias\nCliente: hola\nGestor: le ofrezco un plan",
        canal="llamada")
    assert conv.total_mensajes == 3
    assert conv.nombre_gestor == "Gestor"


def _gestiones():
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "kobra_gestiones.csv")
    if os.path.exists(ruta):
        return pd.read_csv(ruta)
    from data.generate_gestiones import generar as gen_g
    return gen_g(7)


def test_analitica_caracteristicas():
    g = _gestiones()
    car = analitica.caracteristicas_por(g, "tramo_mora")
    assert {"gestiones", "calidad_prom", "tasa_conversion", "emocion_top"} <= set(car.columns)
    assert (car["tasa_conversion"].between(0, 1)).all()


def test_analitica_impacto_kobra():
    g = _gestiones()
    ik = analitica.impacto_kobra(g)
    # los gestores con Kobra tienen mejor calidad que los del grupo control
    assert ik["con_kobra"]["calidad_prom"] > ik["sin_kobra"]["calidad_prom"]
    assert "uplift_conversion" in ik


def test_analitica_evolucion_y_mejora():
    g = _gestiones()
    ev = analitica.evolucion_mensual(g)
    assert ev["mes"].is_monotonic_increasing
    mej = analitica.mejora_por_gestor(g)
    assert {"delta_calidad", "usa_kobra"} <= set(mej.columns)


def test_voz_diarizacion_y_emocion(tmp_path):
    pytest = __import__("pytest")
    try:
        import soundfile  # noqa: F401
    except Exception:
        pytest.skip("soundfile no disponible")
    from kobra import voz
    from data.generate_audio_demo import generar
    wav = str(tmp_path / "call.wav")
    generar(seed=1, out=wav)
    res = voz.analizar_llamada(wav)
    # dual-channel → separa exactamente 2 hablantes
    assert res["canales"] == 2
    assert set(res["resumen_por_hablante"].keys()) == {"Gestor", "Cliente"}
    # la voz del cliente en los tramos difíciles marca emoción negativa (arousal alto)
    emos_cli = [t["emocion_voz"] for t in res["timeline"] if t["hablante"] == "Cliente"]
    assert any(e in ("enojo", "frustracion", "ansiedad") for e in emos_cli)


def test_voz_transcripcion_alineada(tmp_path):
    pytest = __import__("pytest")
    try:
        import soundfile  # noqa: F401
    except Exception:
        pytest.skip("soundfile no disponible")
    from kobra import voz, copiloto
    from data.generate_audio_demo import generar
    wav = str(tmp_path / "call.wav")
    generar(seed=2, out=wav)
    conv = copiloto.parsear_conversacion(
        open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "ejemplo_whatsapp.txt"), encoding="utf-8").read(),
        nombre_gestor="Gestor")
    tt = [{"emisor": t.emisor, "texto": t.texto} for t in conv.turnos]
    res = voz.copiloto_desde_audio(wav, transcript_turnos=tt, probpago=0.7)
    assert res["modo_transcripcion"] in ("alineado", "whisper")
    assert res["turnos"] and all("hablante" in t and "texto" in t for t in res["turnos"])
    # la fusión voz+texto existe y el copiloto produjo asesoría
    assert any(t["sent_fusion"] is not None for t in res["turnos"])
    assert res["copiloto"] and res["copiloto"]["sugerencias"]


def test_voz_fusion_texto():
    from kobra import copiloto
    base = copiloto.analizar_sentimiento("está todo bien, coordinamos")
    tenso = copiloto.analizar_sentimiento(
        "está todo bien, coordinamos", voz={"energia": 0.9, "pitch_var": 0.9, "ritmo": 0.8})
    # misma frase, pero voz tensa empuja el sentimiento hacia abajo
    assert tenso.score < base.score


def test_stream_session():
    import numpy as np
    from realtime import connectors
    sess = connectors.StreamSession(sr=8000, probpago=0.7, estrategia="Plan de cuotas")
    tono = (0.2 * np.sin(2 * np.pi * 180 * np.arange(8000) / 8000)).astype("float32")
    sess.agregar("cliente", tono)
    r = sess.cerrar_turno("cliente", texto_hint="estoy sin trabajo, no puedo pagar")
    assert r["turno"]["canal"] == "cliente"
    assert r["turno"]["sent_fusion"] is not None
    assert r["calidad"] is not None and r["proxima_frase"]


def test_config_persistencia(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    import importlib
    from kobra import config as c
    importlib.reload(c)          # recalcula CONFIG_DIR con el tmp_path
    c.limpiar()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c.guardar({"OPENAI_API_KEY": "sk-abcdefgh1234"})
    assert os.environ.get("OPENAI_API_KEY") == "sk-abcdefgh1234"
    # simula reinicio: sin la var en entorno, aplicar() la recupera del archivo
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c.aplicar()
    assert os.environ.get("OPENAI_API_KEY") == "sk-abcdefgh1234"
    assert c.estado()["OPENAI_API_KEY"] is True
    c.limpiar()
    assert c.estado()["OPENAI_API_KEY"] is False
    importlib.reload(c)


def test_brief_pre_llamada():
    from kobra import registro
    df = registro._scored()
    if df is None:
        __import__("pytest").skip("outputs/kobra_scored.csv no generado")
    algun_id = df["id_deudor"].iloc[0]
    b = registro.brief(algun_id)
    assert b is not None
    for campo in ("probpago", "estrategia", "descuento_recomendado",
                  "canal_recomendado", "guion", "prioridad", "resumen"):
        assert campo in b
    assert 0 <= b["probpago"] <= 1
    assert registro.brief("KB-NOEXISTE") is None


def test_registrar_gestion(tmp_path):
    from kobra import registro
    df = registro._scored()
    if df is None:
        __import__("pytest").skip("outputs/kobra_scored.csv no generado")
    archivo = str(tmp_path / "gestiones.csv")
    algun_id = df["id_deudor"].iloc[0]
    g = registro.registrar_gestion(
        id_deudor=algun_id, gestor_id="G03", calidad=88.0, clima=0.4,
        emociones=["intencion_pago"], tecnicas=["Cierre", "Alternativas"],
        archivo=archivo)
    assert g["resultado"] == "Promesa"          # clima positivo + cierre
    assert g["recupero"] > 0 and g["usa_kobra"] is True
    guardado = pd.read_csv(archivo)
    assert len(guardado) == 1
    assert list(guardado.columns) == registro.GESTION_COLS
    # segunda gestión: id incremental y append sin duplicar header
    registro.registrar_gestion(id_deudor=algun_id, archivo=archivo, clima=-0.5)
    guardado = pd.read_csv(archivo)
    assert len(guardado) == 2
    assert guardado["resultado"].iloc[1] == "Sin acuerdo"


def test_stream_session_resumen_final():
    from realtime import connectors
    sess = connectors.StreamSession(id_deudor="KB-100773", gestor_id="G05")
    sess.cerrar_turno("cliente", texto_hint="dale, acepto, gracias")
    fin = sess.resumen_final()
    assert fin["id_deudor"] == "KB-100773" and fin["gestor_id"] == "G05"
    assert fin["calidad"] is not None and fin["turnos"] == 1


def test_g711_codecs_bit_exactos():
    """Codecs G.711 propios (μ-law y A-law) idénticos a la referencia."""
    import numpy as np
    from realtime.connectors import ulaw_to_float, alaw_to_float
    from realtime.simular_rtp import lin_a_ulaw, lin_a_alaw
    xs = np.arange(-32768, 32768, dtype=np.int32).astype(np.float32) / 32767.0
    # round-trip: error acotado a la cuantización G.711
    assert np.max(np.abs(ulaw_to_float(lin_a_ulaw(xs)) - xs)) < 0.04
    assert np.max(np.abs(alaw_to_float(lin_a_alaw(xs)) - xs)) < 0.04
    try:
        import audioop                     # referencia (no existe en 3.13+)
        pcm = (np.clip(np.arange(-32768, 32768, dtype=np.int32), -32767, 32767)
               .astype(np.int16).tobytes())
        assert lin_a_ulaw(xs) == audioop.lin2ulaw(pcm, 2)
        assert lin_a_alaw(xs) == audioop.lin2alaw(pcm, 2)
        assert alaw_to_float(bytes(range(256))).tobytes() == (
            np.frombuffer(audioop.alaw2lin(bytes(range(256)), 2), dtype=np.int16)
            .astype(np.float32) / 32768.0).tobytes()
    except ImportError:
        pass


def test_conector_avaya_rtp():
    """Parseo RTP y decodificación por payload type (0=PCMU, 8=PCMA)."""
    import numpy as np
    from realtime.simular_rtp import rtp_packet, lin_a_alaw, lin_a_ulaw
    from realtime.conector_avaya import parse_rtp, decodificar
    x = (0.3 * np.sin(2 * np.pi * 200 * np.arange(160) / 8000)).astype("float32")
    for pt, enc in ((8, lin_a_alaw), (0, lin_a_ulaw)):
        pkt = rtp_packet(pt, 7, 1600, 0xABCD, enc(x))
        pt2, seq, payload = parse_rtp(pkt)
        assert (pt2, seq) == (pt, 7)
        dec = decodificar(pt2, payload)
        assert dec.shape[0] == 160
        assert np.max(np.abs(dec - x)) < 0.01
    assert parse_rtp(b"corto") is None                 # basura → ignorada
    assert parse_rtp(bytes(20)) is None                # versión RTP inválida


def test_stream_decoders():
    import numpy as np
    from realtime import connectors
    pcm = (np.array([0, 16000, -16000, 8000], dtype="int16")).tobytes()
    f = connectors.pcm16_to_float(pcm)
    assert f.shape[0] == 4 and -1.0 <= f.min() and f.max() <= 1.0
    # μ-law: decodificador numpy propio (audioop no existe en Python 3.13+)
    u = connectors.ulaw_to_float(bytes(range(256)))
    assert u.shape[0] == 256 and -1.0 <= u.min() and u.max() <= 1.0
    try:
        import audioop
        ref = (np.frombuffer(audioop.ulaw2lin(bytes(range(256)), 2), dtype=np.int16)
               .astype(np.float32) / 32768.0)
        assert np.array_equal(u, ref)          # bit-exacto vs. audioop
    except ImportError:
        pass
