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
