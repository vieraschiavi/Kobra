"""
MV Kobra AI · Análisis de voz (diarización + emoción acústica)
========================================================
Complementa al Copiloto con la señal de VOZ de la llamada:

  1. Diarización: separa quién habla (gestor vs. cliente).
     - Telefonía real: la grabación suele ser DUAL-CHANNEL (una pata por
       interlocutor) → separación exacta por canal.
     - Audio mono: segmentación por energía + clustering de 2 hablantes
       (KMeans sobre features espectrales). Offline, sin modelos pesados.
  2. Emoción acústica (prosodia): a partir de energía, tono (F0), variación
     de tono, ritmo del habla y brillo espectral estima arousal/valencia y una
     etiqueta emocional. Se combina con el sentimiento de TEXTO del copiloto.

Sin dependencias pesadas (soundfile + numpy + scipy + scikit-learn). En
producción se puede reemplazar el estimador por un modelo SER entrenado
(wav2vec2 / SpeechBrain) manteniendo la misma interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

try:
    import soundfile as sf
except Exception:                      # pragma: no cover
    sf = None


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def cargar_audio(path: str):
    """Devuelve (y, sr, n_canales). y es (n,) mono o (n, canales)."""
    if sf is None:
        raise RuntimeError("soundfile no disponible")
    y, sr = sf.read(path, always_2d=True)          # (n, canales)
    return y, sr, y.shape[1]


# ---------------------------------------------------------------------------
# Features prosódicos
# ---------------------------------------------------------------------------
def _rms(x):
    return float(np.sqrt(np.mean(x ** 2) + 1e-12))


def _zcr(x):
    return float(np.mean(np.abs(np.diff(np.sign(x))) > 0))


def _f0_autocorr(x, sr, fmin=80, fmax=350):
    """Estimación simple de F0 por autocorrelación (rango voz humana)."""
    x = x - np.mean(x)
    if _rms(x) < 1e-4:
        return 0.0
    corr = np.correlate(x, x, mode="full")[len(x) - 1:]
    lag_min, lag_max = int(sr / fmax), int(sr / fmin)
    if lag_max >= len(corr):
        return 0.0
    seg = corr[lag_min:lag_max]
    if len(seg) == 0 or np.max(seg) <= 0:
        return 0.0
    lag = np.argmax(seg) + lag_min
    return float(sr / lag) if lag > 0 else 0.0


def _spectral_centroid(x, sr):
    mag = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    s = np.sum(mag)
    return float(np.sum(freqs * mag) / s) if s > 0 else 0.0


def _frames(x, sr, win=0.03, hop=0.015):
    n, h = int(win * sr), int(hop * sr)
    return [x[i:i + n] for i in range(0, max(len(x) - n, 1), h)]


def extraer_features(y_mono, sr) -> dict:
    """Features prosódicos agregados de un segmento de audio mono."""
    y_mono = np.asarray(y_mono, float)
    frames = _frames(y_mono, sr)
    energias = np.array([_rms(f) for f in frames]) if frames else np.array([0.0])
    voiced = energias > (0.35 * energias.max() + 1e-9)
    f0s = np.array([_f0_autocorr(f, sr) for f, v in zip(frames, voiced) if v] or [0.0])
    f0s = f0s[f0s > 0] if np.any(f0s > 0) else np.array([0.0])
    centroides = np.array([_spectral_centroid(f, sr) for f in frames] or [0.0])

    # Ritmo: onsets de energía por segundo (proxy de sílabas/velocidad de habla)
    de = np.diff(energias)
    onsets = int(np.sum(de > (0.15 * energias.max() + 1e-9)))
    dur = max(len(y_mono) / sr, 0.1)
    ritmo = onsets / dur

    return {
        "energia_media": float(energias.mean()),
        "energia_max": float(energias.max()),
        "f0_medio": float(f0s.mean()),
        "f0_var": float(f0s.std()),
        "zcr": _zcr(y_mono),
        "centroide": float(centroides.mean()),
        "ritmo_onsets_seg": float(ritmo),
        "prop_voz": float(voiced.mean()),
        "duracion_seg": float(dur),
    }


def _norm(v, lo, hi):
    return float(np.clip((v - lo) / (hi - lo + 1e-9), 0, 1))


# ---------------------------------------------------------------------------
# Emoción acústica (arousal / valencia → etiqueta)
# ---------------------------------------------------------------------------
@dataclass
class EmocionVoz:
    emocion: str
    arousal: float        # 0 (calmo) .. 1 (activado)
    valencia: float       # -1 (negativo) .. +1 (positivo)
    intensidad: float     # 0 .. 1

    def dict(self):
        return asdict(self)


def emocion_acustica(feat: dict) -> EmocionVoz:
    """Mapea prosodia → emoción (heurística fundada en prosodia del habla)."""
    energia = _norm(feat["energia_media"], 0.018, 0.045)
    f0var = _norm(feat["f0_var"], 5, 35)          # variación de tono: gran discriminador
    ritmo = _norm(feat["ritmo_onsets_seg"], 8, 16)

    # Activación (arousal): energía + variación de tono + velocidad de habla
    arousal = float(np.clip(0.30 * energia + 0.40 * f0var + 0.30 * ritmo, 0, 1))
    # Valencia acústica: agitación (tono inestable + energía + habla rápida) →
    # tensión/negatividad; voz calma y estable → neutral/positiva.
    tension = 0.5 * f0var + 0.3 * energia + 0.2 * ritmo
    valencia = float(np.clip(0.6 - 1.4 * tension, -1, 1))

    if arousal >= 0.6 and valencia < -0.1:
        emo = "enojo" if (valencia < -0.55 and f0var > 0.75) else "frustracion"
    elif arousal >= 0.5 and valencia < 0.15:
        emo = "ansiedad"
    elif arousal < 0.30 and valencia < 0.1:
        emo = "resignacion"
    elif valencia > 0.3 and arousal >= 0.25:
        emo = "positivo"
    else:
        emo = "neutro"
    intensidad = float(np.clip(0.5 * arousal + 0.5 * abs(valencia), 0, 1))
    return EmocionVoz(emo, round(arousal, 3), round(valencia, 3), round(intensidad, 3))


def voz_para_copiloto(feat: dict) -> dict:
    """Adapta features al formato que consume copiloto.analizar_sentimiento()."""
    return {
        "energia": _norm(feat["energia_media"], 0.018, 0.045),
        "pitch_var": _norm(feat["f0_var"], 5, 35),
        "ritmo": _norm(feat["ritmo_onsets_seg"], 8, 16),
    }


# ---------------------------------------------------------------------------
# Diarización
# ---------------------------------------------------------------------------
@dataclass
class Segmento:
    inicio: float
    fin: float
    hablante: str

    def dict(self):
        return asdict(self)


def _vad_segmentos(y, sr, win=0.5, umbral_rel=0.22, min_dur=0.4):
    """Segmentos con voz (energía sobre umbral)."""
    n = int(win * sr)
    if n <= 0:
        return []
    energias, tiempos = [], []
    for i in range(0, len(y) - n, n):
        energias.append(_rms(y[i:i + n])); tiempos.append(i / sr)
    if not energias:
        return []
    energias = np.array(energias)
    umbral = umbral_rel * energias.max()
    activo = energias > umbral
    segs, ini = [], None
    for k, a in enumerate(activo):
        if a and ini is None:
            ini = tiempos[k]
        elif not a and ini is not None:
            if tiempos[k] - ini >= min_dur:
                segs.append((ini, tiempos[k]))
            ini = None
    if ini is not None:
        segs.append((ini, len(y) / sr))
    return segs


def diarizar(path: str, etiqueta_canal=("Gestor", "Cliente")) -> list:
    """
    Diarización de la llamada.
    - Estéreo (dual-channel): canal 0 → gestor, canal 1 → cliente (exacto).
    - Mono: VAD + KMeans(2) sobre features espectrales de cada segmento.
    """
    y, sr, canales = cargar_audio(path)

    if canales >= 2:
        segmentos = []
        for c in range(min(canales, 2)):
            for (a, b) in _vad_segmentos(y[:, c], sr):
                segmentos.append(Segmento(round(a, 2), round(b, 2), etiqueta_canal[c]))
        return sorted(segmentos, key=lambda s: s.inicio)

    # --- Mono: clustering de 2 hablantes ---
    mono = y[:, 0]
    bloques = _vad_segmentos(mono, sr, win=0.4, umbral_rel=0.18, min_dur=0.3)
    if len(bloques) < 2:
        return [Segmento(round(a, 2), round(b, 2), "Hablante") for a, b in bloques]
    feats = []
    for a, b in bloques:
        seg = mono[int(a * sr):int(b * sr)]
        f = extraer_features(seg, sr)
        feats.append([f["f0_medio"], f["centroide"], f["zcr"], f["energia_media"]])
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    X = StandardScaler().fit_transform(np.array(feats))
    lab = KMeans(n_clusters=2, n_init=10, random_state=42).fit_predict(X)
    # El cluster con F0 más alto suele ser un hablante distinto; etiquetamos 1/2
    f0_by = {c: np.mean([feats[i][0] for i in range(len(feats)) if lab[i] == c])
             for c in (0, 1)}
    orden = sorted((0, 1), key=lambda c: f0_by[c])
    nombre = {orden[0]: etiqueta_canal[0], orden[1]: etiqueta_canal[1]}
    return [Segmento(round(a, 2), round(b, 2), nombre[lab[i]])
            for i, (a, b) in enumerate(bloques)]


# ---------------------------------------------------------------------------
# Análisis completo de la grabación
# ---------------------------------------------------------------------------
def analizar_llamada(path: str, etiqueta_canal=("Gestor", "Cliente")) -> dict:
    """Diarización + emoción acústica por segmento y por hablante."""
    y, sr, canales = cargar_audio(path)
    mono_full = y.mean(axis=1)
    segs = diarizar(path, etiqueta_canal)

    timeline, por_hablante = [], {}
    for s in segs:
        if canales >= 2 and s.hablante in etiqueta_canal:
            ch = etiqueta_canal.index(s.hablante)
            audio = y[int(s.inicio * sr):int(s.fin * sr), ch]
        else:
            audio = mono_full[int(s.inicio * sr):int(s.fin * sr)]
        feat = extraer_features(audio, sr)
        emo = emocion_acustica(feat)
        timeline.append({
            "inicio": s.inicio, "fin": s.fin, "hablante": s.hablante,
            "emocion_voz": emo.emocion, "arousal": emo.arousal,
            "valencia": emo.valencia, "intensidad": emo.intensidad,
            "energia": round(voz_para_copiloto(feat)["energia"], 3),
            "f0_medio": round(feat["f0_medio"], 1),
        })
        por_hablante.setdefault(s.hablante, []).append(emo)

    resumen = {}
    for h, emos in por_hablante.items():
        ar = np.mean([e.arousal for e in emos]); va = np.mean([e.valencia for e in emos])
        etiquetas = [e.emocion for e in emos]
        dom = max(set(etiquetas), key=etiquetas.count)
        resumen[h] = {"segmentos": len(emos), "arousal_prom": round(float(ar), 3),
                      "valencia_prom": round(float(va), 3), "emocion_dominante": dom}

    return {"canales": canales, "modo_diarizacion": "dual-channel" if canales >= 2 else "mono/KMeans",
            "duracion_seg": round(len(mono_full) / sr, 2),
            "timeline": timeline, "resumen_por_hablante": resumen}


# ---------------------------------------------------------------------------
# Transcripción alineada por hablante
# ---------------------------------------------------------------------------
def _emisor(hablante: str) -> str:
    return "gestor" if str(hablante).lower().startswith("gestor") else "cliente"


def _whisper_segmentos(path: str):
    """Whisper con timestamps por segmento (si hay OPENAI_API_KEY)."""
    import os
    key = os.getenv("OPENAI_API_KEY", "")
    if len(key) < 10:
        return None
    try:
        import requests
        with open(path, "rb") as f:
            r = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": f},
                data={"model": "whisper-1", "language": "es",
                      "response_format": "verbose_json",
                      "timestamp_granularities[]": "segment"}, timeout=180)
        r.raise_for_status()
        return r.json().get("segments")
    except Exception:
        return None


def _hablante_por_overlap(a, b, segs):
    mejor, mejor_ov = segs[0].hablante if segs else "Hablante", 0
    for s in segs:
        ov = max(0, min(b, s.fin) - max(a, s.inicio))
        if ov > mejor_ov:
            mejor_ov, mejor = ov, s.hablante
    return mejor


def transcribir_llamada(path, transcript_turnos=None, etiqueta_canal=("Gestor", "Cliente")):
    """
    Transcripción alineada por hablante. Devuelve (lista, modo).
    Cada item: {inicio, fin, hablante, texto}.
    - modo 'whisper': transcribe con Whisper y asigna cada segmento al hablante
      diarizado con mayor solapamiento temporal.
    - modo 'alineado': usa una transcripción provista (turnos {emisor,texto}) y
      la alinea a los segmentos diarizados por orden de hablante.
    - modo 'sin_texto': solo segmentos (sin texto disponible).
    """
    segs = diarizar(path, etiqueta_canal)
    wseg = _whisper_segmentos(path)
    if wseg:
        out = [{"inicio": round(w["start"], 2), "fin": round(w["end"], 2),
                "hablante": _hablante_por_overlap(w["start"], w["end"], segs),
                "texto": w["text"].strip()} for w in wseg]
        return out, "whisper"

    if transcript_turnos:
        turnos = list(transcript_turnos)
        usado = [False] * len(turnos)
        out = []
        for s in segs:
            em = _emisor(s.hablante)
            idx = next((i for i, t in enumerate(turnos)
                        if not usado[i] and t.get("emisor") == em), None)
            if idx is None:
                idx = next((i for i in range(len(turnos)) if not usado[i]), None)
            texto = turnos[idx]["texto"] if idx is not None else ""
            if idx is not None:
                usado[idx] = True
            out.append({"inicio": s.inicio, "fin": s.fin, "hablante": s.hablante,
                        "texto": texto})
        return out, "alineado"

    return ([{"inicio": s.inicio, "fin": s.fin, "hablante": s.hablante, "texto": ""}
             for s in segs], "sin_texto")


def copiloto_desde_audio(path, transcript_turnos=None, probpago=None,
                         estrategia=None, etiqueta_canal=("Gestor", "Cliente")):
    """
    Pipeline completo desde una grabación: diarización + transcripción por
    hablante + emoción acústica + fusión voz/texto + asesoría del copiloto.
    """
    from kobra import copiloto
    y, sr, canales = cargar_audio(path)
    mono_full = y.mean(axis=1)
    trans, modo = transcribir_llamada(path, transcript_turnos, etiqueta_canal)

    turnos_fusion = []
    for t in trans:
        if canales >= 2 and t["hablante"] in etiqueta_canal:
            ch = etiqueta_canal.index(t["hablante"])
            audio = y[int(t["inicio"] * sr):int(t["fin"] * sr), ch]
        else:
            audio = mono_full[int(t["inicio"] * sr):int(t["fin"] * sr)]
        feat = extraer_features(audio, sr)
        emo_voz = emocion_acustica(feat)
        vozc = voz_para_copiloto(feat)
        s_texto = copiloto.analizar_sentimiento(t["texto"]) if t["texto"] else None
        s_fusion = copiloto.analizar_sentimiento(t["texto"], voz=vozc) if t["texto"] else None
        turnos_fusion.append({
            "inicio": t["inicio"], "fin": t["fin"], "hablante": t["hablante"],
            "emisor": _emisor(t["hablante"]), "texto": t["texto"],
            "emocion_voz": emo_voz.emocion, "arousal": emo_voz.arousal,
            "sent_texto": s_texto.score if s_texto else None,
            "sent_fusion": s_fusion.score if s_fusion else None,
        })

    texto = "\n".join(f"{t['hablante']}: {t['texto']}" for t in trans if t["texto"])
    cop = (copiloto.analizar_conversacion(texto, canal="llamada", probpago=probpago,
                                          estrategia=estrategia, nombre_gestor="Gestor")
           if texto else None)
    return {
        "modo_transcripcion": modo,
        "voz": analizar_llamada(path, etiqueta_canal),
        "turnos": turnos_fusion,
        "copiloto": cop["copiloto"] if cop else None,
        "calidad": cop["calidad"] if cop else None,
        "tecnicas": cop["tecnicas"] if cop else None,
    }
