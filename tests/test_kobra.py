"""
MV Kobra AI · Tests
=============
Pruebas rápidas del pipeline end-to-end: dataset, ProbPago, negociador y
copiloto de negociación. Corren en segundos con un dataset pequeño.

    pytest -q
"""
import json
import os
import sys
from datetime import date

import pandas as pd
import pytest

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
    assert model.metrics["modelo"] == "Gradient Boosting"
    scored = model.score(df)
    assert scored["probpago"].between(0, 1).all()
    assert set(scored["segmento_propension"].dropna().unique()) <= {"Alta", "Media", "Baja"}


def test_probpago_fit_seleccionado_sin_entrenamiento_previo_cae_en_fallback(monkeypatch, tmp_path):
    """Sin outputs/probpago_model.joblib, fit_seleccionado() debe comportarse
    igual que fit() y etiquetarlo honestamente como fallback (no inventar un
    modelo "seleccionado" que no existe)."""
    import kobra.probpago as pp
    monkeypatch.setattr(pp, "_MODEL_PATH", str(tmp_path / "no_existe.joblib"))
    monkeypatch.setattr(pp, "_SELECTION_PATH", str(tmp_path / "no_existe.json"))
    df = _df()
    model = ProbPagoModel().fit_seleccionado(df)
    assert "fallback" in model.metrics["modelo"]
    assert model.score(df)["probpago"].between(0, 1).all()


def test_probpago_fit_seleccionado_usa_modelo_persistido(monkeypatch, tmp_path):
    """Con outputs/probpago_model.joblib + model_selection.json presentes
    (los que genera `kobra.train`), fit_seleccionado() debe cargar ESE modelo
    calibrado — no reentrenar uno propio — y exponer su nombre real."""
    import kobra.probpago as pp
    from kobra import train as kt

    df = _df()
    model_path = tmp_path / "probpago_model.joblib"
    selection_path = tmp_path / "model_selection.json"
    monkeypatch.setattr(kt, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(pp, "_MODEL_PATH", str(model_path))
    monkeypatch.setattr(pp, "_SELECTION_PATH", str(selection_path))

    kt.entrenar(df=df, guardar=True)
    assert model_path.exists() and selection_path.exists()

    model = ProbPagoModel().fit_seleccionado(df)
    assert "seleccionado por CV" in model.metrics["modelo"]
    assert model.metrics["auc_roc"] > 0.7
    scored = model.score(df)
    assert scored["probpago"].between(0, 1).all()
    imp = model.feature_importance()               # no debe romper con modelos lineales
    assert len(imp) > 0 and imp["importancia"].ge(0).all()


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


def test_copiloto_sentimiento_pt():
    pos = copiloto.analizar_sentimiento("Perfeito, obrigado, aceito o plano", idioma="pt")
    neg = copiloto.analizar_sentimiento("nao consigo pagar sem dinheiro desempregado", idioma="pt")
    assert pos.score > 0 and pos.etiqueta == "positivo"
    assert neg.score < 0 and neg.etiqueta == "negativo"
    # idioma no reconocido cae a español, no explota
    assert copiloto.analizar_sentimiento("gracias", idioma="fr").etiqueta == "positivo"


def test_copiloto_analisis_completo_pt():
    texto = ("Gestor: Ola, bom dia, aqui e da MV Kobra, falo com o senhor?\n"
             "Cliente: Sim, sou eu.\n"
             "Gestor: Entendo sua situacao, vou oferecer uma opcao: parcelas em 3x.\n"
             "Cliente: Aceito, combinamos assim.\n"
             "Gestor: Combinamos, envio o link agora, fica combinado?")
    res = copiloto.analizar_conversacion(texto, canal="llamada", probpago=0.7,
                                         estrategia="Plano de parcelas", idioma="pt")
    assert res["meta"]["idioma"] == "pt"
    assert 0 <= res["calidad"]["score_total"] <= 100
    assert any(res["tecnicas"].values())
    assert res["copiloto"]["proxima_frase"]
    # las etiquetas de criterios de calidad están en portugués
    assert res["calidad"]["criterios"]["empatia"]["nombre"] == "Empatia"


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
    # los gestores con MV Kobra AI tienen mejor calidad que los del grupo control
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


def test_gestor_ia_negocia_y_cierra():
    from kobra.gestor_ia import SesionGestorIA
    ses = SesionGestorIA(id_deudor="KB-100000", canal="Llamada",
                         gestor_id="IA01", usar_claude=False)
    r = ses.responder(None)                       # saludo
    assert not r["fin"] and r["texto"]
    guion = ["Sí, soy yo", "es mucha plata, no me alcanza", "en cuotas dale", "acepto"]
    for m in guion:
        if r["fin"]:
            break
        r = ses.responder(m)
    assert r["fin"] and r["campos_erp"]["resultado"] in ("Promesa", "Sin acuerdo")
    # nunca supera el descuento máximo autorizado del brief
    assert r["campos_erp"]["descuento_aplicado"] <= ses.brief["descuento_recomendado"] + 1e-9


def test_gestor_ia_deriva_a_humano():
    from kobra.gestor_ia import SesionGestorIA
    ses = SesionGestorIA(id_deudor="KB-100000", usar_claude=False)
    ses.responder(None)
    r = ses.responder("quiero hablar con una persona")
    assert r["fin"] and ses.campos_erp["resultado"] == "Derivado a humano"


def test_voicebot_campania_concurrente(tmp_path):
    import asyncio
    from realtime import voicebot
    from kobra import registro
    df = registro._scored()
    if df is None:
        __import__("pytest").skip("outputs/kobra_scored.csv no generado")
    ids = df["id_deudor"].head(30).tolist()
    archivo = str(tmp_path / "g.csv")
    m = asyncio.run(voicebot.correr_campania(
        ids, lineas=25, gestor_id="IA09", archivo_gestiones=archivo,
        usar_claude=False))
    assert m["ok"] == 30 and m["errores"] == 0
    assert m["pico"] <= 25                          # respeta el límite de líneas
    guardado = pd.read_csv(archivo)
    assert len(guardado) == 30
    assert (guardado["gestor_id"] == "IA09").all()


def test_comparativa_ia():
    from kobra import analitica
    g = _gestiones()
    if not g["gestor_id"].astype(str).str.startswith("IA").any():
        __import__("pytest").skip("dataset sin cohorte IA")
    comp = analitica.comparativa_ia(g)
    assert comp and comp["ia"]["gestiones"] > 0 and comp["humanos"]["gestiones"] > 0
    assert comp["volumen_x"] > 1                    # la IA hace más volumen


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


def test_config_cifrado_no_es_texto_plano(tmp_path, monkeypatch):
    """Sin keyring de SO disponible (caso típico en CI/servidor), la config debe
    quedar cifrada en disco — nunca la API key en texto plano."""
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    import importlib
    from kobra import config as c
    importlib.reload(c)
    monkeypatch.setattr(c, "_keyring_disponible", lambda: None)  # forzar sin keyring
    c.limpiar()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    secreto = "sk-ant-super-secreto-000111222"
    c.guardar({"ANTHROPIC_API_KEY": secreto})
    assert c.backend_activo() == "cifrado"
    assert os.path.exists(c.CONFIG_FILE_CIFRADO)
    assert not os.path.exists(c.CONFIG_FILE_PLANO)
    with open(c.CONFIG_FILE_CIFRADO, "rb") as f:
        contenido = f.read()
    assert secreto.encode() not in contenido
    # y sigue siendo recuperable normalmente
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c.aplicar()
    assert os.environ.get("ANTHROPIC_API_KEY") == secreto
    c.limpiar()
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


# ---------------------------------------------------------------------------
# Cumplimiento normativo (contact governance)
# ---------------------------------------------------------------------------
def test_cumplimiento_horario_y_dia():
    from datetime import datetime
    from kobra import cumplimiento as cp
    pol = cp.PoliticaContacto(permitir_feriados=True)   # aislar del calendario
    # Lunes 10:00 → permitido
    assert cp.puede_contactar("KB-1", "Llamada", datetime(2026, 7, 6, 10, 0),
                              politica=pol).permitido
    # Lunes 22:00 → fuera de horario
    d = cp.puede_contactar("KB-1", "Llamada", datetime(2026, 7, 6, 22, 0), politica=pol)
    assert not d.permitido and d.codigo == "FUERA_HORARIO"
    # Domingo 10:00 → día no hábil
    d = cp.puede_contactar("KB-1", "Llamada", datetime(2026, 7, 5, 10, 0), politica=pol)
    assert not d.permitido and d.codigo == "DIA_NO_HABIL"


def test_cumplimiento_feriado():
    from datetime import datetime
    from kobra import cumplimiento as cp
    # 25 de agosto (Declaratoria de la Independencia) → feriado, un martes en 2026
    d = cp.puede_contactar("KB-1", "Llamada", datetime(2026, 8, 25, 10, 0))
    assert not d.permitido and d.codigo == "FERIADO"
    # Semana de Turismo derivada de Pascua (2026: Pascua = 5 de abril)
    fer = cp.feriados_uruguay(2026)
    assert cp._pascua(2026).isoformat() == "2026-04-05"
    assert any("Turismo" in n for n in fer.values())


def test_cumplimiento_feriados_por_pais():
    from datetime import datetime
    from kobra import cumplimiento as cp
    # México: 16 de setiembre (Independencia) es feriado ahí, no en Uruguay.
    pol_mx = cp.PoliticaContacto(pais="MX")
    d = cp.puede_contactar("KB-1", "Llamada", datetime(2026, 9, 16, 10, 0), politica=pol_mx)
    assert not d.permitido and d.codigo == "FERIADO"
    # el mismo día, con política Uruguay (default), no es feriado uruguayo
    d_uy = cp.puede_contactar("KB-1", "Llamada", datetime(2026, 9, 16, 10, 0))
    assert d_uy.permitido
    # Semana Santa (derivada de Pascua) también aplica a los países de Fase 1
    fer_ar = cp.feriados_por_pais("AR", 2026)
    assert any("Santo" in n for n in fer_ar.values())
    # Brasil (Fase 2): tabla propia, en portugués, incluye Sexta-feira Santa
    fer_br = cp.feriados_por_pais("BR", 2026)
    assert any("Independência" in n for n in fer_br.values())
    assert any("Sexta-feira Santa" in n for n in fer_br.values())
    # país sin tabla de feriados propia (fuera del catálogo LATAM) cae a Uruguay
    assert cp.feriados_por_pais("DE", 2026) == cp.feriados_uruguay(2026)


def test_cumplimiento_topes_frecuencia():
    from datetime import datetime, timedelta
    from kobra import cumplimiento as cp
    pol = cp.PoliticaContacto(permitir_feriados=True, max_por_dia=1, max_por_semana=3)
    ahora = datetime(2026, 7, 6, 11, 0)           # lunes
    # ya lo contacté hoy → tope diario
    d = cp.puede_contactar("KB-1", "Llamada", ahora,
                           contactos_previos=[ahora - timedelta(hours=2)], politica=pol)
    assert not d.permitido and d.codigo == "TOPE_DIARIO"
    # 3 contactos en la semana (días distintos) → tope semanal
    previos = [ahora - timedelta(days=k) for k in (1, 2, 3)]
    d = cp.puede_contactar("KB-1", "Llamada", ahora, contactos_previos=previos, politica=pol)
    assert not d.permitido and d.codigo == "TOPE_SEMANAL"


def test_cumplimiento_opt_out(tmp_path):
    from kobra import cumplimiento as cp
    dnc = str(tmp_path / "no_contactar.csv")
    assert not cp.esta_en_no_contactar("KB-9", archivo=dnc)
    assert cp.es_pedido_no_contactar("por favor no me llamen más, sáquenme de la lista")
    assert not cp.es_pedido_no_contactar("no tengo la plata ahora")
    cp.registrar_no_contactar("KB-9", motivo="pedido del deudor", archivo=dnc)
    assert cp.esta_en_no_contactar("KB-9", "Llamada", archivo=dnc)
    d = cp.puede_contactar("KB-9", "Llamada", archivo_dnc=dnc)
    assert not d.permitido and d.codigo == "OPT_OUT"


def test_gestor_ia_opt_out_registra(tmp_path):
    from kobra import cumplimiento as cp
    from kobra.gestor_ia import SesionGestorIA
    dnc = str(tmp_path / "dnc.csv")
    ses = SesionGestorIA(id_deudor="KB-100773", gestor_id="IA01",
                         usar_claude=False, dnc_archivo=dnc)
    ses.responder(None)                                  # saludo
    r = ses.responder("No me llamen más, no quiero que me contacten")
    assert r["fin"] and ses.campos_erp.get("opt_out") is True
    assert cp.esta_en_no_contactar("KB-100773", "Llamada", archivo=dnc)


def test_voicebot_respeta_no_contactar(tmp_path):
    import asyncio
    from kobra import cumplimiento as cp
    from realtime.voicebot import correr_campania
    dnc = str(tmp_path / "dnc.csv")
    gest = str(tmp_path / "g.csv")
    cp.registrar_no_contactar("KB-100000", motivo="opt-out", archivo=dnc)
    ids = ["KB-100000", "KB-100001", "KB-100002"]
    m = asyncio.run(correr_campania(ids, lineas=5, archivo_gestiones=gest,
                                    usar_claude=False, archivo_dnc=dnc))
    assert m["bloqueados_no_contactar"] == 1 and m["total"] == 2


# ---------------------------------------------------------------------------
# Explicabilidad de ProbPago
# ---------------------------------------------------------------------------
def _prep_scored():
    """Genera outputs/kobra_scored.csv si falta (para brief/registro/voicebot)."""
    from kobra import registro
    if registro._scored() is not None:
        return
    from kobra import pipeline
    pipeline.run()
    registro._scored(refrescar=True)


def test_explicabilidad_reason_codes():
    from kobra import explicabilidad as ex
    df = _df()
    model = ProbPagoModel().fit(df)
    scored = model.score(df)
    base = ex.baseline_cartera(df)
    # deudor con score de buró alto y sin promesas incumplidas → drivers positivos
    fila = df.iloc[int(scored["probpago"].idxmax())]
    drivers = ex.explicar(model, fila, base, top=3)
    assert 1 <= len(drivers) <= 3
    assert all("delta_pp" in d and "etiqueta" in d for d in drivers)
    # el texto del brief menciona al menos un driver
    txt = ex.explicar_texto(model, fila, base)
    assert isinstance(txt, str) and len(txt) > 0
    # vectorizado sobre la cartera: una reason code por fila
    serie = ex.explicar_cartera(model, df.head(50))
    assert len(serie) == 50 and serie.notna().all()


# ---------------------------------------------------------------------------
# Caso de negocio (ROI)
# ---------------------------------------------------------------------------
def test_roi_estimador():
    from kobra import roi
    r = roi.estimar(cartera_total_uyu=100_000_000, tasa_recupero_base=0.30,
                    meses=12, costo_mensual_uyu=100_000)
    esc = r["escenarios"]
    # más uplift ⇒ más recupero adicional (monotonía)
    assert (esc["conservador"]["recupero_adicional_uyu"]
            < esc["base"]["recupero_adicional_uyu"]
            < esc["optimista"]["recupero_adicional_uyu"])
    # +5 pp sobre 100M = 5M adicionales
    assert abs(esc["base"]["recupero_adicional_uyu"] - 5_000_000) < 1
    # payback positivo y ROI coherente
    assert esc["base"]["payback_meses"] > 0 and esc["base"]["roi"] > 0
    assert "SUPUESTO" in r["NOTA"]


# ---------------------------------------------------------------------------
# Modo "mi cartera de prueba" (cliente carga sus propios contactos)
# ---------------------------------------------------------------------------
def test_cartera_manual_y_gestor():
    from kobra import cartera_manual as cm
    from kobra import negociador
    from kobra.gestor_ia import SesionGestorIA
    df = _df()
    model = ProbPagoModel().fit(df)
    # contactos ficticios (sin datos reales) con perfiles distintos
    contactos = [
        {"nombre": "Contacto A", "telefono": "099000001", "monto_deuda": 10000, "dias_mora": 20},
        {"nombre": "Contacto B", "telefono": "099000002", "monto_deuda": 6000, "dias_mora": 150},
    ]
    cart = cm.cargar_manual(contactos)
    assert list(cart["id_deudor"]) == ["MP-001", "MP-002"]
    cart = cm.puntuar(model, cart)               # sin qcut (pocas filas)
    assert cart["probpago"].between(0, 1).all()
    cart = negociador.recomendar(cart)
    # el brief pre-cargado se respeta (no lo pisa el lookup de la cartera scoreada)
    brief = cm.brief_desde_fila(cart.iloc[0])
    ses = SesionGestorIA(id_deudor="MP-001", usar_claude=False, brief=brief)
    assert ses.brief["monto_deuda"] == 10000
    r = ses.responder(None)
    assert r["texto"] and not r["fin"]


def test_leer_csv_preserva_telefono(tmp_path):
    from kobra import cartera_manual as cm
    p = tmp_path / "c.csv"
    p.write_text("nombre,telefono,deuda\nWendy,095779569,10000\n", encoding="utf-8")
    contactos = cm.leer_csv(str(p))
    assert contactos[0]["telefono"] == "095779569"      # conserva el 0 inicial
    assert contactos[0]["monto_deuda"] == 10000


def test_procesar_cartera_end_to_end():
    """procesar(): score + reason codes + cumplimiento + negociación por contacto."""
    from realtime.mi_cartera import procesar, resultados_a_dataframe
    from kobra.probpago import ProbPagoModel
    from kobra import explicabilidad
    df = _df()
    model = ProbPagoModel().fit(df)
    base = explicabilidad.baseline_cartera(df)
    contactos = [
        {"nombre": "A", "telefono": "099000001", "monto_deuda": 10000, "dias_mora": 20},
        {"nombre": "B", "telefono": "099000002", "monto_deuda": 15000, "dias_mora": 160},
    ]
    res = procesar(contactos, model, base, usar_claude=False)
    assert len(res) == 2
    for r in res:
        assert 0 <= r["probpago"] <= 1
        assert r["motivo_probpago"] and r["transcript"]
        assert r["resultado"] in ("Promesa", "Sin acuerdo", "No contactar", "Derivado a humano")
        assert r["transcript"][0][0] == "gestor"      # arranca el bot
    tabla = resultados_a_dataframe(res)
    assert "transcript" not in tabla.columns and len(tabla) == 2


def test_desde_dataframe_tolerante():
    from kobra import cartera_manual as cm
    df = pd.DataFrame({"nombre": ["A", "B"], "telefono": ["099000001", "099000002"],
                       "deuda": ["10000", ""], "dias_mora": ["30", ""]})
    contactos = cm.desde_dataframe(df)
    assert len(contactos) == 1                         # descarta la fila sin deuda
    assert contactos[0]["telefono"] == "099000001"
    assert contactos[0]["monto_deuda"] == 10000 and contactos[0]["dias_mora"] == 30


# ---------------------------------------------------------------------------
# Llamada de voz autónoma con el Gestor IA (TwiML Twilio)
# ---------------------------------------------------------------------------
def test_voz_twiml_negociacion(tmp_path):
    """El Gestor IA conduce la llamada por TwiML: saludo → oferta → cierre."""
    import asyncio, os
    from types import SimpleNamespace
    from realtime import server

    class FakeReq:
        def __init__(self, method="POST", query=None, form=None, headers=None):
            self.method = method
            self.query_params = query or {}
            self._form = form or {}
            self.headers = headers or {"host": "t.ngrok.app", "x-forwarded-proto": "https"}
            self.url = SimpleNamespace(scheme="https")
        async def form(self):
            return self._form

    run = asyncio.new_event_loop().run_until_complete

    r = run(server.voz_entrante(FakeReq(query={"id_deudor": "", "monto": "10000"},
                                        form={"CallSid": "CAX"})))
    t = r.body.decode()
    assert r.status_code == 200 and "<Gather" in t and "<Say" in t

    r = run(server.voz_turno(FakeReq(query={"call": "CAX"},
                                     form={"SpeechResult": "Sí, soy yo"})))
    assert "saldo" in r.body.decode().lower() or "pag" in r.body.decode().lower()

    r = run(server.voz_turno(FakeReq(query={"call": "CAX"},
                                     form={"SpeechResult": "Dale, acepto, me sirve"})))
    t = r.body.decode()
    assert "<Gather" not in t and "<Say" in t          # cierre: habla y cuelga
    assert "CAX" not in server._SESIONES_VOZ           # sesión liberada


def test_voz_llamar_sin_credenciales():
    """El disparador de llamada exige credenciales de Twilio (falla claro)."""
    import asyncio, os
    from types import SimpleNamespace
    from realtime import server
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        os.environ.pop(k, None)

    class FakeReq:
        method = "POST"
        query_params = {}
        headers = {"host": "t.app"}
        url = SimpleNamespace(scheme="https")
        async def form(self):
            return {"telefono": "+59809000000"}

    r = asyncio.new_event_loop().run_until_complete(server.voz_llamar(FakeReq()))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Integración ERP / base de datos (sábana de gestiones)
# ---------------------------------------------------------------------------
def test_integracion_sabana_y_exportes():
    from kobra import integracion as ig
    df = _gestiones()
    sab = ig.sabana(df)
    for col in ("resultado", "tipo_gestor", "fecha_gestion", "monto_acordado", "notas"):
        assert col in sab.columns
    assert set(sab["tipo_gestor"].unique()) <= {"IA", "Humano"}
    assert len(ig.a_json(sab.head())) > 2
    assert len(ig.a_csv(sab.head())) > 0
    assert len(ig.a_excel(sab.head())) > 0


def test_integracion_sincronizar_sqlite(tmp_path):
    import sqlite3
    from kobra import integracion as ig
    sab = ig.sabana(_gestiones()).head(30)
    db = str(tmp_path / "erp.db")
    r = ig.sincronizar_db(sab, f"sqlite:///{db}", "gestiones", "replace")
    assert r["ok"] and r["filas"] == 30
    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM gestiones").fetchone()[0]
    assert n == 30


def test_integracion_api_sin_url_y_mapeo():
    from kobra import integracion as ig
    sab = ig.sabana(_gestiones()).head(5)
    r = ig.enviar_api(sab, "")           # sin URL → error controlado
    assert not r["ok"] and r["enviados"] == 0
    mapeado = ig.aplicar_mapeo(sab, {"resultado": "tipificacion", "id_deudor": "cuenta"})
    assert "tipificacion" in mapeado.columns and "cuenta" in mapeado.columns


def _armar_db_prueba(tmp_path):
    """SQLite chica con 2 tablas + FK declarada, para probar consulta_bd sin BD real."""
    import sqlite3
    db = str(tmp_path / "consulta.db")
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE clientes (
            cliente_id INTEGER PRIMARY KEY,
            nombre TEXT,
            departamento TEXT
        );
        CREATE TABLE pagos (
            pago_id INTEGER PRIMARY KEY,
            cliente_id INTEGER NOT NULL REFERENCES clientes(cliente_id),
            monto REAL,
            fecha_pago TEXT
        );
        INSERT INTO clientes VALUES (1,'Juan','Montevideo'),(2,'Ana','Canelones');
        INSERT INTO pagos VALUES
            (1,1,1000.0,'2026-01-05'),(2,1,500.0,'2026-02-10'),(3,2,2000.0,'2026-01-20');
    """)
    con.commit()
    con.close()
    return f"sqlite:///{db}"


def test_consulta_bd_extraer_catalogo_y_fichas(tmp_path):
    from kobra import consulta_bd as kcbd
    url = _armar_db_prueba(tmp_path)
    engine = kcbd.conectar(url)
    catalogo = kcbd.extraer_catalogo(engine)

    assert set(catalogo["tablas"]) == {"clientes", "pagos"}
    assert catalogo["tablas"]["clientes"]["n_filas"] == 2
    pk_pagos = {c["columna"] for c in catalogo["tablas"]["pagos"]["columnas"] if c["pk"]}
    assert pk_pagos == {"pago_id"}
    # FK declarada pagos.cliente_id -> clientes.cliente_id
    assert any(fk["tabla_origen"] == "pagos" and fk["columna_origen"] == "cliente_id"
              and fk["tabla_destino"] == "clientes" for fk in catalogo["fks"])

    fichas = kcbd.catalogo_a_fichas(catalogo)
    tablas_fichas = {f["tabla"] for f in fichas}
    assert {"clientes", "pagos"} <= tablas_fichas
    ficha_pagos = next(f["texto"] for f in fichas if f["tabla"] == "pagos")
    assert "cliente_id" in ficha_pagos and "monto" in ficha_pagos


def test_consulta_bd_recuperador_tfidf(tmp_path):
    from kobra import consulta_bd as kcbd
    url = _armar_db_prueba(tmp_path)
    catalogo = kcbd.extraer_catalogo(kcbd.conectar(url))
    fichas = kcbd.catalogo_a_fichas(catalogo)
    rec = kcbd.RecuperadorEsquema(fichas)
    top = rec.recuperar("cuánto pagó cada cliente", k=2)
    assert {f["tabla"] for f in top} <= {"clientes", "pagos"}
    assert len(top) >= 2


def test_consulta_bd_validador_bloquea_dml_y_tablas_inventadas(tmp_path):
    from kobra import consulta_bd as kcbd
    url = _armar_db_prueba(tmp_path)
    catalogo = kcbd.extraer_catalogo(kcbd.conectar(url))

    ok, problemas = kcbd.validar_sql("SELECT * FROM pagos", catalogo)
    assert ok and not problemas

    ok, problemas = kcbd.validar_sql("DELETE FROM pagos WHERE 1=1", catalogo)
    assert not ok and any("no permitida" in p for p in problemas)

    ok, problemas = kcbd.validar_sql("SELECT * FROM tabla_fantasma", catalogo)
    assert not ok and any("no existe" in p for p in problemas)


def test_consulta_bd_ejecutar_sql_aplica_limite(tmp_path):
    from kobra import consulta_bd as kcbd
    url = _armar_db_prueba(tmp_path)
    engine = kcbd.conectar(url)
    cols, filas, sql_exec = kcbd.ejecutar_sql("SELECT * FROM pagos", engine, limite=2)
    assert "pago_id" in cols
    assert len(filas) == 2
    assert "limit" in sql_exec.lower()


def test_consulta_bd_motor_responder_pipeline_completo(tmp_path, monkeypatch):
    from kobra import consulta_bd as kcbd
    from kobra import auditoria as kaud

    # Espía sobre registrar() en vez de redirigir LOG_FILE: el default de
    # registrar() ya quedó fijado al importar el módulo, así que monkeypatchear
    # kaud.LOG_FILE no alcanza para redirigir escrituras que no pasan archivo=.
    llamadas = []
    monkeypatch.setattr(kaud, "registrar",
                        lambda accion, detalle=None, **kw: llamadas.append(accion))

    url = _armar_db_prueba(tmp_path)
    motor = kcbd.MotorConsultaBD(url)

    # Sin API key real: simulamos la respuesta de Claude para probar el resto del pipeline
    monkeypatch.setattr(kcbd, "generar_sql_claude",
                        lambda pregunta, fichas, dialecto, api_key=None:
                            "SELECT departamento, SUM(monto) AS total FROM pagos "
                            "JOIN clientes ON clientes.cliente_id = pagos.cliente_id "
                            "GROUP BY departamento")

    r = motor.responder("cuánto pagó cada departamento", api_key="fake-key")
    assert r["valido"]
    assert not r["error"]
    df = motor.resultado_a_dataframe(r)
    assert df is not None and "total" in df.columns and len(df) == 2
    assert "consulta_bd_nl2sql" in llamadas


def test_consulta_bd_generar_sql_sin_key_falla_controlado(monkeypatch):
    from kobra import consulta_bd as kcbd
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        kcbd.generar_sql_claude("una pregunta", [{"tabla": "x", "texto": "TABLA: x"}],
                               "sqlite", api_key=None)


def _gestiones_seguimiento():
    """Cartera chica y determinística para probar seguimiento.py:
    - KB-1: arreglo vencido, sin pago después -> debe salir en la agenda.
    - KB-2: promesa vencida, pero con "Pago" posterior -> NO debe salir.
    - KB-3: arreglo con fecha_pago cargada directo en la misma fila -> NO debe salir.
    - KB-4: promesa cuya fecha_compromiso todavía no venció -> NO debe salir.
    """
    filas = [
        dict(id_deudor="KB-1", fecha_gestion="2026-06-01 10:00", resultado="Arreglo de pago",
            fecha_compromiso="2026-06-10", fecha_pago=None, monto_acordado=1000.0,
            cuotas=1, canal="Llamada", gestor="G01", notas=""),
        dict(id_deudor="KB-2", fecha_gestion="2026-06-01 10:00", resultado="Promesa",
            fecha_compromiso="2026-06-05", fecha_pago=None, monto_acordado=500.0,
            cuotas=1, canal="Llamada", gestor="G01", notas=""),
        dict(id_deudor="KB-2", fecha_gestion="2026-06-06 10:00", resultado="Pago",
            fecha_compromiso=None, fecha_pago="2026-06-06", monto_acordado=500.0,
            cuotas=1, canal="Llamada", gestor="G01", notas=""),
        dict(id_deudor="KB-3", fecha_gestion="2026-06-01 10:00", resultado="Arreglo de pago",
            fecha_compromiso="2026-06-03", fecha_pago="2026-06-03", monto_acordado=300.0,
            cuotas=1, canal="WhatsApp", gestor="IA01", notas=""),
        dict(id_deudor="KB-4", fecha_gestion="2026-06-20 10:00", resultado="Promesa",
            fecha_compromiso="2026-07-15", fecha_pago=None, monto_acordado=800.0,
            cuotas=1, canal="Llamada", gestor="G01", notas=""),
    ]
    return pd.DataFrame(filas)


def test_seguimiento_promesas_incumplidas_detecta_solo_lo_pendiente():
    from kobra import seguimiento as kseg
    hoy = date(2026, 7, 6)
    r = kseg.promesas_incumplidas(_gestiones_seguimiento(), hoy=hoy)
    assert set(r["id_deudor"]) == {"KB-1"}
    fila = r.iloc[0]
    assert fila["dias_vencida"] == (hoy - date(2026, 6, 10)).days
    assert fila["monto_acordado"] == 1000.0


def test_seguimiento_agenda_hoy_respeta_no_contactar(tmp_path):
    from kobra import cumplimiento as kcump
    from kobra import seguimiento as kseg

    dnc = str(tmp_path / "no_contactar.csv")
    kcump.registrar_no_contactar("KB-1", canal="todos", archivo=dnc)

    hoy = date(2026, 7, 6)   # lunes
    r = kseg.agenda_hoy(_gestiones_seguimiento(), hoy=hoy, archivo_dnc=dnc)
    fila = r[r["id_deudor"] == "KB-1"].iloc[0]
    assert bool(fila["contactable"]) is False
    assert fila["motivo_bloqueo"] and "No Contactar" in fila["motivo_bloqueo"]


def test_voz_tts_costo_estimado_y_key():
    from kobra import voz_tts
    assert voz_tts.costo_estimado_usd("a" * 1000) == voz_tts.COSTO_POR_1000_CHARS_USD
    assert voz_tts.costo_estimado_usd("") == 0.0
    assert voz_tts.api_key_configurada("corta") == ""
    assert voz_tts.api_key_configurada("sk-una-key-bien-larga") == "sk-una-key-bien-larga"


def test_voz_tts_sintetizar_sin_key_falla_controlado(monkeypatch):
    from kobra import voz_tts
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    r = voz_tts.sintetizar("hola", "voice123", api_key=None)
    assert not r["ok"] and "ELEVENLABS_API_KEY" in r["error"]


def test_voz_tts_sintetizar_ok_mockeado(monkeypatch):
    from kobra import voz_tts

    class _FakeResp:
        content = b"\x00\x01audio-fake"
        def raise_for_status(self):
            pass

    import requests as _requests
    monkeypatch.setattr(_requests, "post", lambda *a, **kw: _FakeResp())

    r = voz_tts.sintetizar("Hola, buenas tardes", "voice123", api_key="sk-fake-000111")
    assert r["ok"] and r["audio"] == b"\x00\x01audio-fake"
    assert r["caracteres"] == len("Hola, buenas tardes")
    assert r["costo_est_usd"] > 0


def _gestiones_campana():
    """Historial con hora de gestión (a diferencia de _gestiones_seguimiento,
    que no la necesita) para poder probar la preferencia de canal/horario."""
    filas = [
        # KB-1: siempre WhatsApp, siempre a la tarde (16hs) -> exitosas
        dict(id_deudor="KB-1", fecha_gestion="2026-06-01 16:00", resultado="Promesa",
            fecha_compromiso=None, fecha_pago=None, canal="WhatsApp",
            monto_acordado=100.0, cuotas=1, gestor="IA01", notas=""),
        dict(id_deudor="KB-1", fecha_gestion="2026-06-10 16:15", resultado="Pago",
            fecha_compromiso=None, fecha_pago="2026-06-10", canal="WhatsApp",
            monto_acordado=100.0, cuotas=1, gestor="IA01", notas=""),
        # KB-2: casi siempre Llamada a la mañana (10hs), un intento fallido por WhatsApp
        dict(id_deudor="KB-2", fecha_gestion="2026-06-02 10:00", resultado="Sin acuerdo",
            fecha_compromiso=None, fecha_pago=None, canal="WhatsApp",
            monto_acordado=None, cuotas=None, gestor="G01", notas=""),
        dict(id_deudor="KB-2", fecha_gestion="2026-06-05 10:30", resultado="Promesa",
            fecha_compromiso="2026-06-12", fecha_pago=None, canal="Llamada",
            monto_acordado=200.0, cuotas=1, gestor="G01", notas=""),
    ]
    return pd.DataFrame(filas)


def test_campana_preferencias_contacto():
    from kobra import campana as kcamp
    r = kcamp.preferencias_contacto(_gestiones_campana(), hoy=date(2026, 7, 6)).set_index("id_deudor")
    assert r.loc["KB-1", "canal_preferido"] == "WhatsApp"
    assert r.loc["KB-1", "hora_preferida"] == 16
    assert r.loc["KB-2", "canal_preferido"] == "Llamada"   # prioriza la exitosa sobre el intento fallido
    assert r.loc["KB-2", "hora_preferida"] == 10


def test_campana_plan_contacto_hoy_prioriza_vencidas_y_excluye(monkeypatch):
    from kobra import campana as kcamp
    _prep_scored()

    g = _gestiones_seguimiento()   # ya definida más arriba para los tests de seguimiento
    hoy = date(2026, 7, 6)
    ahora = pd.Timestamp("2026-07-06 10:00").to_pydatetime()   # lunes, horario permitido

    plan = kcamp.plan_contacto_hoy(g, hoy=hoy, ahora=ahora, max_contactos=5)
    assert not plan.empty
    assert plan.iloc[0]["motivo"].startswith("Promesa/arreglo vencido")
    assert plan["prioridad_rank"].is_monotonic_increasing

    plan_excluido = kcamp.plan_contacto_hoy(g, hoy=hoy, ahora=ahora, max_contactos=5,
                                            excluir={"KB-1"})
    assert "KB-1" not in set(plan_excluido["id_deudor"])


def test_campana_iniciar_llamada_sin_credenciales(monkeypatch):
    from kobra import campana as kcamp
    for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        monkeypatch.delenv(var, raising=False)
    r = kcamp.iniciar_llamada("+59899000000", "KB-1", 1000, "https://miserver.com")
    assert not r["ok"] and "credenciales" in r["detalle"]


def test_campana_iniciar_llamada_ok_mockeado(monkeypatch):
    from kobra import campana as kcamp

    class _FakeResp:
        status_code = 201
        text = ""
        def json(self):
            return {"sid": "CAxxxx"}

    import requests as _requests
    monkeypatch.setattr(_requests, "post", lambda *a, **kw: _FakeResp())
    r = kcamp.iniciar_llamada("+59899000000", "KB-1", 1000, "https://miserver.com",
                             sid="ACxxx", token="tok", from_="+10000000000")
    assert r["ok"] and r["sid"] == "CAxxxx"


def test_campana_enviar_whatsapp_sin_content_sid_falla_controlado(monkeypatch):
    from kobra import campana as kcamp
    monkeypatch.delenv("TWILIO_WHATSAPP_CONTENT_SID", raising=False)
    r = kcamp.enviar_whatsapp("+59899000000", {"1": "KB-1"}, sid="ACxxx", token="tok",
                              from_whatsapp="whatsapp:+10000000000")
    assert not r["ok"] and "plantilla" in r["detalle"]


def test_campana_enviar_whatsapp_ok_mockeado(monkeypatch):
    from kobra import campana as kcamp

    class _FakeResp:
        status_code = 201
        text = ""
        def json(self):
            return {"sid": "SMxxxx"}

    import requests as _requests
    monkeypatch.setattr(_requests, "post", lambda *a, **kw: _FakeResp())
    r = kcamp.enviar_whatsapp("+59899000000", {"1": "KB-1"}, sid="ACxxx", token="tok",
                              from_whatsapp="whatsapp:+10000000000", content_sid="HXxxxx")
    assert r["ok"] and r["sid"] == "SMxxxx"


def test_campana_enviar_email_sin_smtp_falla_controlado(monkeypatch):
    from kobra import campana as kcamp
    for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(var, raising=False)
    r = kcamp.enviar_email("cliente@mail.com", "31-60", {"monto": 1000, "dias_mora": 45})
    assert not r["ok"] and "SMTP" in r["detalle"]


def test_campana_enviar_email_ok_mockeado(monkeypatch):
    from kobra import campana as kcamp

    enviados = []

    class _FakeSMTP:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            pass
        def login(self, user, password):
            enviados.append(("login", user))
        def sendmail(self, from_, to, msg):
            enviados.append(("sendmail", from_, to))

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    r = kcamp.enviar_email("cliente@mail.com", "31-60", {"monto": 5000, "dias_mora": 40},
                          smtp_host="smtp.miempresa.com", smtp_port=587, smtp_user="u",
                          smtp_password="p", from_email="cobranzas@miempresa.com")
    assert r["ok"]
    assert ("sendmail", "cobranzas@miempresa.com", ["cliente@mail.com"]) == enviados[1]


def test_campana_plantillas_default_y_customizadas(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    import importlib
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import campana as kcamp
    importlib.reload(kcamp)

    default = kcamp.obtener_plantillas_email()
    assert "1-30" in default and "{monto" in default["1-30"]["cuerpo"]

    kcamp.guardar_plantilla_email("1-30", "Asunto custom {empresa}", "Cuerpo custom {monto}")
    actualizadas = kcamp.obtener_plantillas_email()
    assert actualizadas["1-30"]["asunto"] == "Asunto custom {empresa}"
    assert actualizadas["61-90"]["asunto"] == default["61-90"]["asunto"]   # el resto no cambió

    importlib.reload(kconfig)


def test_campana_renderizar_plantilla():
    from kobra import campana as kcamp
    asunto, cuerpo = kcamp.renderizar_plantilla(
        {"asunto": "{empresa} debe $U {monto:,.0f}", "cuerpo": "{dias_mora} días de atraso"},
        {"empresa": "ACME", "monto": 12345.678, "dias_mora": 30})
    assert asunto == "ACME debe $U 12,346"
    assert cuerpo == "30 días de atraso"


def test_campana_contactados_hoy_por_campana(monkeypatch):
    from kobra import campana as kcamp
    from kobra import auditoria as kaud

    hoy = date(2026, 7, 6)
    entradas = [
        {"ts": "2026-07-06T09:00:00", "accion": "campana_contacto", "detalle": {"id_deudor": "KB-1"}},
        {"ts": "2026-07-06T09:05:00", "accion": "campana_contacto", "detalle": {"id_deudor": "KB-2"}},
        {"ts": "2026-07-05T09:00:00", "accion": "campana_contacto", "detalle": {"id_deudor": "KB-3"}},
        {"ts": "2026-07-06T09:10:00", "accion": "login_ok", "detalle": {}},
    ]
    monkeypatch.setattr(kaud, "leer", lambda *a, **kw: entradas)
    vistos = kcamp.contactados_hoy_por_campana(hoy)
    assert vistos == {"KB-1", "KB-2"}


def test_campana_cargar_contactos(tmp_path):
    from kobra import campana as kcamp
    csv = tmp_path / "contactos.csv"
    csv.write_text("id_deudor,telefono,email\nKB-1,+59899111111,kb1@mail.com\nKB-2,,kb2@mail.com\n",
                  encoding="utf-8")
    telefonos, emails = kcamp.cargar_contactos(str(csv))
    assert telefonos == {"KB-1": "+59899111111"}
    assert emails == {"KB-1": "kb1@mail.com", "KB-2": "kb2@mail.com"}

    telefonos_vacio, emails_vacio = kcamp.cargar_contactos(str(tmp_path / "no_existe.csv"))
    assert telefonos_vacio == {} and emails_vacio == {}


def test_campana_ejecutar_plan_dispatcha_por_canal(monkeypatch):
    from kobra import campana as kcamp
    from kobra import auditoria as kaud

    llamadas, whatsapps, emails_enviados, auditados = [], [], [], []
    monkeypatch.setattr(kcamp, "iniciar_llamada",
                        lambda tel, d, monto, base: llamadas.append(d) or {"ok": True, "detalle": None})
    monkeypatch.setattr(kcamp, "enviar_whatsapp",
                        lambda tel, cv, **kw: whatsapps.append(cv) or {"ok": True, "detalle": None})
    monkeypatch.setattr(kcamp, "enviar_email",
                        lambda mail, tramo, ctx, **kw: emails_enviados.append((mail, tramo)) or {"ok": True, "detalle": None})
    monkeypatch.setattr(kaud, "registrar", lambda accion, detalle=None, **kw: auditados.append(detalle))

    plan = pd.DataFrame([
        {"id_deudor": "KB-1", "canal": "Llamada", "monto": 100, "motivo": "m"},
        {"id_deudor": "KB-2", "canal": "WhatsApp", "monto": 200, "motivo": "m"},
        {"id_deudor": "KB-3", "canal": "Email", "monto": 300, "motivo": "m", "tramo_mora": "31-60"},
        {"id_deudor": "KB-4", "canal": "Llamada", "monto": 400, "motivo": "m"},   # sin teléfono
    ])
    resultados = kcamp.ejecutar_plan(plan, "https://miserver.com",
                                     telefonos={"KB-1": "+599111", "KB-2": "+599222"},
                                     emails={"KB-3": "kb3@mail.com"})
    assert llamadas == ["KB-1"]
    assert whatsapps and whatsapps[0]["1"] == "KB-2"
    assert emails_enviados == [("kb3@mail.com", "31-60")]
    assert len(auditados) == 4
    assert resultados[3]["ok"] is False and "teléfono" in resultados[3]["detalle"]


def _db_cartera_sqlite(tmp_path):
    """Base SQLite de prueba con una tabla 'cartera' como la tendría un cliente."""
    import sqlite3
    ruta = tmp_path / "cliente.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE cartera (nombre TEXT, telefono TEXT, deuda REAL, dias_mora INT)")
    con.executemany("INSERT INTO cartera VALUES (?,?,?,?)", [
        ("Ana", "099111222", 12000.0, 40),
        ("Beto", "099333444", 6000.0, 95),
        ("Sin Deuda", "099555666", None, 10),   # se descarta: sin monto válido
    ])
    con.commit(); con.close()
    return f"sqlite:///{ruta}"


def test_cartera_desde_base_de_datos(tmp_path):
    from kobra import cartera_manual as cm
    url = _db_cartera_sqlite(tmp_path)
    contactos = cm.desde_base_de_datos(url, "SELECT nombre, telefono, deuda, dias_mora FROM cartera")
    assert len(contactos) == 2   # la fila sin deuda se descarta
    assert {c["nombre"] for c in contactos} == {"Ana", "Beto"}
    assert all("monto_deuda" in c and c["telefono"].startswith("099") for c in contactos)

    # y alimenta el pipeline igual que el CSV: cargar_manual la acepta
    df = cm.cargar_manual(contactos)
    assert len(df) == 2 and "tramo_mora" in df.columns


def test_cartera_desde_base_de_datos_solo_lectura(tmp_path):
    import pytest
    from kobra import cartera_manual as cm
    url = _db_cartera_sqlite(tmp_path)
    for mala in ("DELETE FROM cartera", "DROP TABLE cartera",
                 "SELECT * FROM cartera; DROP TABLE cartera --",
                 "UPDATE cartera SET deuda=0", "   "):
        with pytest.raises(ValueError):
            cm.desde_base_de_datos(url, mala)
    # la tabla sigue intacta después de todos los intentos
    contactos = cm.desde_base_de_datos(url, "SELECT nombre, telefono, deuda FROM cartera")
    assert len(contactos) == 2


def test_cartera_desde_base_de_datos_respeta_limite(tmp_path):
    from kobra import cartera_manual as cm
    url = _db_cartera_sqlite(tmp_path)
    contactos = cm.desde_base_de_datos(
        url, "SELECT nombre, telefono, deuda FROM cartera WHERE deuda IS NOT NULL", limite=1)
    assert len(contactos) == 1


def test_ayuda_construye_base_y_busca():
    from kobra import ayuda as kayuda
    fichas = kayuda.construir_base()
    assert len(fichas) > 20   # README + docs dan decenas de secciones
    assert all({"fuente", "titulo", "texto"} <= set(f) for f in fichas)

    r = kayuda.buscar("¿cómo hago una llamada real con Twilio?", k=3, fichas=fichas)
    assert r and any("TWILIO" in f["fuente"].upper() for f in r)


def test_ayuda_responder_sin_key_devuelve_docs(monkeypatch):
    from kobra import ayuda as kayuda
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = kayuda.responder("¿qué necesito para llamar de verdad por teléfono?")
    assert r["modo"] == "docs"
    assert r["fuentes"] and "Configuración" in r["respuesta"]


def test_ayuda_responder_pregunta_vacia():
    from kobra import ayuda as kayuda
    r = kayuda.responder("   ")
    assert r["modo"] == "vacio" and not r["fuentes"]


def test_ayuda_responder_con_key_mockeado(monkeypatch):
    from kobra import ayuda as kayuda

    class _FakeResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"content": [{"text": "Cargá las claves de Twilio en ⚙️ Configuración."}]}

    import requests as _requests
    capturado = {}
    def _fake_post(url, headers=None, json=None, timeout=None):
        capturado["json"] = json
        return _FakeResp()
    monkeypatch.setattr(_requests, "post", _fake_post)
    r = kayuda.responder("¿dónde cargo Twilio?", api_key="sk-ant-test-key-123")
    assert r["modo"] == "ia"
    assert "Configuración" in r["respuesta"]
    # el contexto de docs viaja en el system prompt, la pregunta como user
    assert "CONTEXTO DE DOCUMENTACIÓN" in capturado["json"]["system"]
    assert capturado["json"]["messages"][0]["content"] == "¿dónde cargo Twilio?"


def test_ayuda_idioma_pt_usa_corpus_traducido(monkeypatch):
    from kobra import ayuda as kayuda
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = kayuda.responder("O que é o ProbPago?", idioma="pt")
    assert r["modo"] == "docs"
    assert r["fuentes"] and all(f.endswith("_pt.md") for f in r["fuentes"])
    assert "documentação" in r["respuesta"]      # intro en portugués, no español


def test_ayuda_idioma_pt_cae_a_espanol_si_no_esta_traducido(monkeypatch):
    from kobra import ayuda as kayuda
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Simula un tema que no tiene ningún match en el corpus pt (parcial, Fase 2)
    # pero sí en el corpus es completo — fuerza el camino de fallback.
    ficha_es = [{"fuente": "docs/GUIA_REGISTRO_LEGAL_URUGUAY.md", "titulo": "DNPI",
                 "texto": "Trámite de registro de marca ante el DNPI.", "score": 0.5}]

    def _buscar_falso(pregunta, k=4, fichas=None, idioma="es"):
        return [] if idioma == "pt" else ficha_es
    monkeypatch.setattr(kayuda, "buscar", _buscar_falso)

    r = kayuda.responder("Como registro minha marca?", idioma="pt")
    assert r["modo"] == "docs"
    assert "não foi traduzida" in r["respuesta"]   # aviso honesto de fallback
    assert "docs/GUIA_REGISTRO_LEGAL_URUGUAY.md" in r["fuentes"]


def test_ayuda_idioma_desconocido_cae_a_espanol(monkeypatch):
    from kobra import ayuda as kayuda
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = kayuda.responder("¿qué es ProbPago?", idioma="fr")
    assert r["modo"] == "docs"
    assert any(not f.endswith("_pt.md") for f in r["fuentes"])


def test_twilio_setup_buscar_numeros_sin_credenciales(monkeypatch):
    from kobra import twilio_setup as ktw
    for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    r = ktw.buscar_numeros_disponibles("UY")
    assert not r["ok"] and r["numeros"] == [] and "credenciales" in r["detalle"]


def test_twilio_setup_buscar_numeros_ok_mockeado(monkeypatch):
    from kobra import twilio_setup as ktw

    class _FakeResp:
        status_code = 200
        def json(self):
            return {"available_phone_numbers": [
                {"phone_number": "+59890000001", "region": "MONTEVIDEO", "locality": "Montevideo"},
                {"phone_number": "+59890000002", "region": "MONTEVIDEO", "locality": "Montevideo"},
            ]}

    import requests as _requests
    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _FakeResp())
    r = ktw.buscar_numeros_disponibles("UY", sid="ACxxx", token="tok")
    assert r["ok"] and len(r["numeros"]) == 2
    assert r["numeros"][0]["numero"] == "+59890000001"


def test_twilio_setup_comprar_numero_sin_credenciales(monkeypatch):
    from kobra import twilio_setup as ktw
    for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    r = ktw.comprar_numero("+59890000001", "https://miserver.com/voz/entrante")
    assert not r["ok"] and "credenciales" in r["detalle"]


def test_twilio_setup_comprar_numero_ok_mockeado(monkeypatch):
    from kobra import twilio_setup as ktw

    class _FakeResp:
        status_code = 201
        text = ""
        def json(self):
            return {"sid": "PNxxxx", "phone_number": "+59890000001"}

    import requests as _requests
    monkeypatch.setattr(_requests, "post", lambda *a, **kw: _FakeResp())
    r = ktw.comprar_numero("+59890000001", "https://miserver.com/voz/entrante",
                          sid="ACxxx", token="tok")
    assert r["ok"] and r["sid"] == "PNxxxx" and r["numero"] == "+59890000001"


def test_twilio_setup_configurar_webhook_numero_no_encontrado(monkeypatch):
    from kobra import twilio_setup as ktw

    class _FakeRespVacia:
        status_code = 200
        def json(self):
            return {"incoming_phone_numbers": []}

    import requests as _requests
    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _FakeRespVacia())
    r = ktw.configurar_webhook_numero("+59890000099", "https://miserver.com/voz/entrante",
                                      sid="ACxxx", token="tok")
    assert not r["ok"] and "no se encontró" in r["detalle"].lower()


def test_twilio_setup_configurar_webhook_numero_ok_mockeado(monkeypatch):
    from kobra import twilio_setup as ktw

    class _FakeRespLista:
        status_code = 200
        def json(self):
            return {"incoming_phone_numbers": [{"sid": "PNxxxx"}]}

    class _FakeRespUpdate:
        status_code = 200

    import requests as _requests
    monkeypatch.setattr(_requests, "get", lambda *a, **kw: _FakeRespLista())
    monkeypatch.setattr(_requests, "post", lambda *a, **kw: _FakeRespUpdate())
    r = ktw.configurar_webhook_numero("+59890000001", "https://miserver.com/voz/entrante",
                                      sid="ACxxx", token="tok")
    assert r["ok"]


def test_auditoria_encadena_y_verifica(tmp_path, monkeypatch):
    from kobra import auditoria as kaud
    archivo = str(tmp_path / "auditoria.log")
    monkeypatch.setattr(kaud, "LOG_FILE", archivo)

    e1 = kaud.registrar("login_ok", {}, usuario="ana", rol="admin", archivo=archivo)
    e2 = kaud.registrar("gestion_registrada", {"id_deudor": "KB-1"}, usuario="ana",
                        rol="admin", archivo=archivo)
    assert e1["hash_prev"] == kaud.GENESIS_HASH
    assert e2["hash_prev"] == e1["hash"]

    chk = kaud.verificar_integridad(archivo)
    assert chk == {"ok": True, "entradas": 2, "primer_error": None}

    entradas = kaud.leer(archivo)
    assert [e["accion"] for e in entradas] == ["login_ok", "gestion_registrada"]
    assert kaud.leer(archivo, limite=1)[0]["accion"] == "gestion_registrada"


def test_auditoria_detecta_manipulacion(tmp_path, monkeypatch):
    from kobra import auditoria as kaud
    archivo = str(tmp_path / "auditoria.log")
    monkeypatch.setattr(kaud, "LOG_FILE", archivo)

    kaud.registrar("login_ok", {}, usuario="ana", rol="admin", archivo=archivo)
    kaud.registrar("config_borrada", {}, usuario="ana", rol="admin", archivo=archivo)

    # alguien edita el log "a mano", por fuera del módulo
    with open(archivo, encoding="utf-8") as f:
        lineas = f.readlines()
    entrada = json.loads(lineas[0])
    entrada["accion"] = "algo_distinto"
    lineas[0] = json.dumps(entrada) + "\n"
    with open(archivo, "w", encoding="utf-8") as f:
        f.writelines(lineas)

    chk = kaud.verificar_integridad(archivo)
    assert chk["ok"] is False
    assert chk["primer_error"] == 0


def _rsa_par_de_prueba():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    pub_pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    return priv_pem, pub_pem


def _oidc_cfg_mock(monkeypatch, valores):
    from kobra import sso_oidc
    monkeypatch.setattr(sso_oidc.kconfig, "leer_extra", lambda k, default=None: valores.get(k, default))


def test_oidc_no_configurado_sin_las_4_claves(monkeypatch):
    from kobra import sso_oidc
    _oidc_cfg_mock(monkeypatch, {"OIDC_ISSUER": "https://idp.example.com"})  # faltan las otras 3
    assert sso_oidc.configurado() is False
    assert sso_oidc.url_autorizacion({}) is None


def test_oidc_rol_admin_vs_gestor(monkeypatch):
    from kobra import sso_oidc
    _oidc_cfg_mock(monkeypatch, {"OIDC_ADMINS": "ana@empresa.com, Otro@Empresa.com"})
    assert sso_oidc.rol_para("ana@empresa.com") == "admin"
    assert sso_oidc.rol_para("OTRO@empresa.com") == "admin"   # case-insensitive
    assert sso_oidc.rol_para("cualquiera@empresa.com") == "gestor"


def test_oidc_callback_verifica_token_de_verdad(monkeypatch):
    """Genera un IdP simulado (par RSA propio) y confirma que procesar_callback
    valida state + firma + issuer + audiencia contra un token real, sin pegarle
    a la red (discovery/JWKS/token-exchange, todos mockeados)."""
    import time
    import jwt as pyjwt
    from kobra import sso_oidc

    priv_pem, pub_pem = _rsa_par_de_prueba()
    issuer, client_id = "https://idp.example.com", "client-abc"
    ahora = int(time.time())
    claims = {"iss": issuer, "aud": client_id, "sub": "u1", "email": "ana@empresa.com",
             "name": "Ana", "iat": ahora, "exp": ahora + 300}
    token = pyjwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": "k1"})

    _oidc_cfg_mock(monkeypatch, {
        "OIDC_ISSUER": issuer, "OIDC_CLIENT_ID": client_id,
        "OIDC_CLIENT_SECRET": "secreto", "OIDC_REDIRECT_URI": "http://localhost:8501",
        "OIDC_ADMINS": "ana@empresa.com",
    })
    monkeypatch.setattr(sso_oidc, "_discovery", lambda iss: {
        "authorization_endpoint": issuer + "/auth",
        "token_endpoint": issuer + "/token",
        "jwks_uri": issuer + "/jwks",
    })

    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"id_token": token, "access_token": "x"}
    monkeypatch.setattr(sso_oidc.requests, "post", lambda *a, **kw: _FakeResp())

    class _FakeSigningKey:
        key = pub_pem
    class _FakeJWKClient:
        def __init__(self, *_a, **_kw): pass
        def get_signing_key_from_jwt(self, _tok): return _FakeSigningKey()
    monkeypatch.setattr(sso_oidc.jwt, "PyJWKClient", _FakeJWKClient)

    session = {"kobra_oidc_state": "el-state-correcto"}
    resultado = sso_oidc.procesar_callback("codigo-x", "el-state-correcto", session)
    assert resultado == {"email": "ana@empresa.com", "nombre": "Ana", "rol": "admin"}
    assert "kobra_oidc_state" not in session   # se consume, no se reutiliza


def test_oidc_callback_rechaza_state_invalido(monkeypatch):
    from kobra import sso_oidc
    _oidc_cfg_mock(monkeypatch, {
        "OIDC_ISSUER": "https://idp.example.com", "OIDC_CLIENT_ID": "c",
        "OIDC_CLIENT_SECRET": "s", "OIDC_REDIRECT_URI": "http://localhost:8501",
    })
    session = {"kobra_oidc_state": "state-real"}
    with pytest.raises(sso_oidc.CallbackError):
        sso_oidc.procesar_callback("codigo", "state-falsificado", session)


def test_oidc_callback_rechaza_firma_de_otra_clave(monkeypatch):
    """Un token firmado con una clave distinta a la del JWKS del proveedor
    (ej. un atacante con su propio par de claves) debe rechazarse."""
    import time
    import jwt as pyjwt
    from kobra import sso_oidc

    priv_atacante, _ = _rsa_par_de_prueba()
    _, pub_real = _rsa_par_de_prueba()
    issuer, client_id = "https://idp.example.com", "client-abc"
    ahora = int(time.time())
    claims = {"iss": issuer, "aud": client_id, "sub": "u1", "email": "atacante@fuera.com",
             "iat": ahora, "exp": ahora + 300}
    token_falso = pyjwt.encode(claims, priv_atacante, algorithm="RS256", headers={"kid": "k1"})

    _oidc_cfg_mock(monkeypatch, {
        "OIDC_ISSUER": issuer, "OIDC_CLIENT_ID": client_id,
        "OIDC_CLIENT_SECRET": "s", "OIDC_REDIRECT_URI": "http://localhost:8501",
    })
    monkeypatch.setattr(sso_oidc, "_discovery", lambda iss: {
        "authorization_endpoint": issuer + "/auth", "token_endpoint": issuer + "/token",
        "jwks_uri": issuer + "/jwks",
    })

    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"id_token": token_falso}
    monkeypatch.setattr(sso_oidc.requests, "post", lambda *a, **kw: _FakeResp())

    class _FakeSigningKey:
        key = pub_real   # el JWKS "real" del proveedor, distinto al del atacante
    class _FakeJWKClient:
        def __init__(self, *_a, **_kw): pass
        def get_signing_key_from_jwt(self, _tok): return _FakeSigningKey()
    monkeypatch.setattr(sso_oidc.jwt, "PyJWKClient", _FakeJWKClient)

    session = {"kobra_oidc_state": "ok"}
    with pytest.raises(sso_oidc.CallbackError):
        sso_oidc.procesar_callback("codigo", "ok", session)


def test_auditoria_concurrente_no_rompe_la_cadena(tmp_path):
    """Regresión: sin lock, escrituras concurrentes hacían que varias entradas
    leyeran el mismo 'último hash' y la cadena quedaba rota (ver historia del
    commit). Con portalocker, 100 registros concurrentes deben verificar OK."""
    import concurrent.futures
    from kobra import auditoria as kaud
    archivo = str(tmp_path / "audit_concurrente.log")

    def escribir(i):
        kaud.registrar("evento_test", {"i": i}, usuario="t", rol="admin", archivo=archivo)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        list(ex.map(escribir, range(100)))

    chk = kaud.verificar_integridad(archivo)
    assert chk == {"ok": True, "entradas": 100, "primer_error": None}


def test_registrar_gestion_concurrente_no_duplica_ids(tmp_path):
    """Regresión: contar líneas del CSV y después escribir no era atómico —
    con gestiones concurrentes (el Gestor IA corre hasta 50 en paralelo,
    ver realtime/voicebot.py), varias terminaban con el mismo id_gestion."""
    import concurrent.futures
    from kobra import registro
    archivo = str(tmp_path / "gestiones_concurrentes.csv")

    def registrar(i):
        return registro.registrar_gestion(f"KB-{i}", gestor_id="IA01", canal="Llamada",
                                          clima=0.5, resultado="Promesa", archivo=archivo)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        resultados = list(ex.map(registrar, range(50)))

    ids = [r["id_gestion"] for r in resultados]
    assert len(set(ids)) == 50
    guardado = pd.read_csv(archivo)
    assert len(guardado) == 50
    assert guardado["id_gestion"].nunique() == 50


def test_gestor_ia_tipifica_arreglo(tmp_path):
    from kobra.gestor_ia import SesionGestorIA
    from kobra import registro
    arch = str(tmp_path / "g.csv")
    ses = SesionGestorIA(id_deudor="KB-100773", gestor_id="IA01", usar_claude=False,
                         brief={"monto_deuda": 6000, "probpago": 0.6, "estrategia": "Plan de cuotas",
                                "descuento_recomendado": 0.1, "plan_cuotas": 3, "segmento_propension": "Media"})
    ses.responder(None)
    r = ses.responder("Sí soy yo")
    for _ in range(8):
        if r["fin"]: break
        r = ses.responder("dale, acepto en cuotas")
    g = ses.registrar(archivo=arch)
    assert g["tipo_gestor"] == "IA"
    assert g["resultado"] in ("Arreglo de pago", "Sin acuerdo")


def test_backup_crea_y_restaura(tmp_path, monkeypatch):
    from kobra import backup as kbackup
    from kobra import config as kconfig
    import importlib

    monkeypatch.setattr(kbackup, "ROOT", str(tmp_path))
    monkeypatch.setattr(kbackup, "_ARCHIVOS_NEGOCIO", ["data/kobra_gestiones.csv", "data/no_contactar.csv"])
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    importlib.reload(kconfig)

    os.makedirs(tmp_path / "data")
    (tmp_path / "data" / "kobra_gestiones.csv").write_text("id_gestion,resultado\nGR-1,Pago\n", encoding="utf-8")
    (tmp_path / "data" / "no_contactar.csv").write_text("id_deudor\nKB-1\n", encoding="utf-8")
    kconfig.guardar({"ANTHROPIC_API_KEY": "sk-ant-test-000111"})

    destino = str(tmp_path / "backups")
    r = kbackup.crear_backup(destino)
    assert r["ok"] and r["archivos"] >= 2 and os.path.exists(r["ruta"])

    listado = kbackup.listar_backups(destino)
    assert len(listado) == 1 and listado[0]["ruta"] == r["ruta"]

    # "perder" los datos originales y restaurar desde el backup
    os.remove(tmp_path / "data" / "kobra_gestiones.csv")
    assert not (tmp_path / "data" / "kobra_gestiones.csv").exists()
    rr = kbackup.restaurar_backup(r["ruta"], destino_root=str(tmp_path))
    assert rr["ok"] and rr["archivos"] >= 2
    assert (tmp_path / "data" / "kobra_gestiones.csv").read_text(encoding="utf-8").startswith("id_gestion")

    importlib.reload(kconfig)


def test_backup_retencion_conserva_los_mas_recientes(tmp_path):
    """No depende de crear_backup() real (el nombre usa timestamp al segundo,
    así que llamarlo 5 veces seguidas podría pisar el mismo archivo) — arma
    5 zips de backup "falsos" con nombres válidos y prueba la retención sola."""
    import zipfile
    from kobra import backup as kbackup
    destino = str(tmp_path / "backups")
    os.makedirs(destino)
    for i in range(5):
        ruta = os.path.join(destino, f"kobra_backup_2026010{i}_000000.zip")
        with zipfile.ZipFile(ruta, "w") as z:
            z.writestr("manifiesto.json", "{}")

    listado_antes = kbackup.listar_backups(destino)
    assert len(listado_antes) == 5
    borrados = kbackup.limpiar_backups_viejos(destino, mantener=2)
    assert borrados == 3
    assert len(kbackup.listar_backups(destino)) == 2


def test_backup_sin_datos_no_falsea_exito(tmp_path, monkeypatch):
    from kobra import backup as kbackup
    monkeypatch.setattr(kbackup, "ROOT", str(tmp_path))
    monkeypatch.setattr(kbackup, "_ARCHIVOS_NEGOCIO", ["data/no_existe.csv"])
    # aislar config/uso para que no "cuelen" archivos reales de este sandbox
    monkeypatch.setattr(kbackup, "_archivos_config", lambda: [])
    monkeypatch.setattr(kbackup, "_archivos_backend_venta", lambda: [])
    r = kbackup.crear_backup(str(tmp_path / "backups"))
    assert r["ok"] is False and r["archivos"] == 0
