"""
Kobra · Análisis de voz (diarización + emoción acústica)
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
