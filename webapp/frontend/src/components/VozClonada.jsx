// © 2026 Martín Viera. Todos los derechos reservados.

// Voz clonada del Gestor IA en tres pasos, sin salir de Kobra:
//   1. grabar (o subir) una muestra,  2. clonar,  3. escucharla.
// Antes había que clonar en elevenlabs.io, copiar el id y volver — y ni así
// sonaba en las llamadas (ver kobra/voz_clonada.py::voz_activa).

import React, { useEffect, useRef, useState } from "react";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";
import { aWav } from "./wav.js";

async function enviar(ruta, cuerpo) {
  const ses = getSesion();
  const r = await fetch(ruta, {
    method: "POST",
    headers: {
      ...(cuerpo instanceof FormData ? {} : { "content-type": "application/json" }),
      ...(ses ? { Authorization: `Bearer ${ses.token}` } : {}),
    },
    body: cuerpo instanceof FormData ? cuerpo : JSON.stringify(cuerpo),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail || `Error ${r.status}`);
  }
  return r;
}

function Paso({ n, titulo, children, apagado }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "32px 1fr", gap: 10,
                  opacity: apagado ? 0.45 : 1, marginTop: 14 }}>
      <div aria-hidden="true" style={{ width: 28, height: 28, borderRadius: "50%",
                   display: "grid", placeItems: "center", fontWeight: 800, fontSize: 13,
                   background: "var(--navy-800)", border: "1px solid var(--line)" }}>{n}</div>
      <div>
        <strong style={{ fontSize: 14 }}>{titulo}</strong>
        <div style={{ marginTop: 6 }}>{children}</div>
      </div>
    </div>
  );
}

export default function VozClonada() {
  const [est, setEst] = useState(null);
  const [errorCarga, setErrorCarga] = useState("");
  const [muestra, setMuestra] = useState(null);       // { archivo, nombreArchivo, segundos }
  const [grabando, setGrabando] = useState(false);
  const [segundos, setSegundos] = useState(0);
  const [nombre, setNombre] = useState("");
  const [consiento, setConsiento] = useState(false);
  const [quitarRuido, setQuitarRuido] = useState(false);
  const [ocupado, setOcupado] = useState("");
  const [nota, setNota] = useState(null);             // { ok, texto }
  const [texto, setTexto] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [voces, setVoces] = useState(null);
  const grabador = useRef(null);
  const reloj = useRef(null);

  const cargar = () => api("/api/voz/clonada")
    .then((d) => { setEst(d); setTexto((x) => x || d.frase_prueba); })
    .catch((e) => setErrorCarga(e.message));
  useEffect(() => {
    cargar();
    return () => {
      clearInterval(reloj.current);
      if (grabador.current?.state === "recording") grabador.current.stop();
    };
  }, []);
  // El objeto de audio de la prueba anterior se libera al reemplazarlo.
  useEffect(() => () => { if (audioUrl) URL.revokeObjectURL(audioUrl); }, [audioUrl]);

  if (errorCarga) return null;      // gestor o admin de otra empresa: no es su sección
  if (!est) return null;

  const empezar = async () => {
    setNota(null);
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setNota({ ok: false, texto: t("voz_clonada.sin_microfono") });
      return;
    }
    const mr = new MediaRecorder(stream);
    const trozos = [];
    mr.ondataavailable = (e) => { if (e.data.size) trozos.push(e.data); };
    mr.onstop = async () => {
      stream.getTracks().forEach((pista) => pista.stop());
      clearInterval(reloj.current);
      try {
        const { wav, segundos: s } = await aWav(new Blob(trozos, { type: mr.mimeType }));
        setMuestra({ archivo: wav, nombreArchivo: "grabacion.wav", segundos: s });
      } catch {
        setNota({ ok: false, texto: t("voz_clonada.no_decodifica") });
      }
    };
    grabador.current = mr;
    mr.start();
    setGrabando(true);
    setSegundos(0);
    const inicio = Date.now();
    reloj.current = setInterval(() => setSegundos(Math.floor((Date.now() - inicio) / 1000)), 250);
  };

  const parar = () => {
    if (grabador.current?.state === "recording") grabador.current.stop();
    setGrabando(false);
  };

  const elegirArchivo = (archivo) => {
    setNota(null);
    setMuestra(archivo ? { archivo, nombreArchivo: archivo.name, segundos: null } : null);
  };

  const clonar = async () => {
    setOcupado("clonar"); setNota(null);
    try {
      const fd = new FormData();
      fd.append("archivo", muestra.archivo, muestra.nombreArchivo);
      fd.append("nombre", nombre.trim());
      fd.append("consentimiento", consiento ? "true" : "false");
      fd.append("quitar_ruido", quitarRuido ? "true" : "false");
      const d = await (await enviar("/api/voz/clonada", fd)).json();
      setEst(d);
      setNota({ ok: true, texto: [t("voz_clonada.clonada_ok"), d.aviso].filter(Boolean).join(" ") });
      await probar();
    } catch (e) {
      setNota({ ok: false, texto: e.message });
    } finally {
      setOcupado("");
    }
  };

  const probar = async () => {
    setOcupado("probar");
    try {
      const r = await enviar("/api/voz/clonada/probar", { texto });
      setAudioUrl(URL.createObjectURL(await r.blob()));
    } catch (e) {
      setNota({ ok: false, texto: e.message });
    } finally {
      setOcupado("");
    }
  };

  const verVoces = async () => {
    setNota(null);
    try { setVoces((await api("/api/voz/voces")).voces); }
    catch (e) { setNota({ ok: false, texto: e.message }); }
  };

  const elegir = async (voiceId) => {
    if (!voiceId) return;
    const v = voces.find((x) => x.voice_id === voiceId);
    try {
      setEst(await api("/api/voz/clonada/elegir",
        { metodo: "POST", cuerpo: { voice_id: voiceId, nombre: v?.nombre || "" } }));
      setNota({ ok: true, texto: t("voz_clonada.elegida_ok") });
    } catch (e) { setNota({ ok: false, texto: e.message }); }
  };

  const desactivar = async () => {
    try {
      setEst(await api("/api/voz/clonada/desactivar", { metodo: "POST" }));
      setAudioUrl("");
      setNota({ ok: true, texto: t("voz_clonada.desactivada") });
    } catch (e) { setNota({ ok: false, texto: e.message }); }
  };

  const activa = est.motor_llamadas === "elevenlabs";
  const corta = muestra?.segundos != null && muestra.segundos < est.duracion_minima_s;
  const puedeClonar = est.hay_key && muestra && !corta && nombre.trim() && consiento && !ocupado;

  return (
    <div className="card" style={{ maxWidth: 720, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("voz_clonada.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("voz_clonada.subtitulo")}</p>

      <div className="toolbar" style={{ alignItems: "center", gap: 12, padding: "10px 12px",
             borderRadius: 10, background: activa ? "rgba(124,194,66,.12)" : "rgba(242,180,65,.10)" }}>
        <b style={{ fontSize: 13 }}>
          {activa
            ? t("voz_clonada.estado_activa", { nombre: est.nombre || est.voice_id })
            : t("voz_clonada.estado_twilio")}
        </b>
        {activa && <button className="btn ghost" onClick={desactivar}>{t("voz_clonada.desactivar")}</button>}
      </div>
      {est.forzada_por_entorno && (
        <p style={{ color: "var(--amber)", fontSize: 12.5 }}>{t("voz_clonada.forzada_entorno")}</p>
      )}
      {!est.hay_key && (
        <p style={{ color: "var(--amber)", fontSize: 12.5 }}>{t("voz_clonada.falta_key")}</p>
      )}

      <Paso n="1" titulo={t("voz_clonada.paso1")} apagado={!est.hay_key}>
        <p style={{ color: "var(--muted)", fontSize: 12.5, margin: "0 0 8px" }}>
          {t("voz_clonada.paso1_ayuda", { minimo: est.duracion_minima_s })}
        </p>
        <blockquote style={{ margin: "0 0 10px", padding: "8px 12px", fontSize: 13, lineHeight: 1.6,
                             borderLeft: "3px solid var(--green)", background: "var(--navy-800)" }}>
          {t("voz_clonada.guion_lectura")}
        </blockquote>
        <div className="toolbar" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {grabando ? (
            <button className="btn" onClick={parar} aria-live="polite">
              ■ {t("voz_clonada.parar")} · {segundos}s
            </button>
          ) : (
            <button className="btn" onClick={empezar} disabled={!est.hay_key || !!ocupado}>
              ● {t("voz_clonada.grabar")}
            </button>
          )}
          <span style={{ color: "var(--muted)", fontSize: 12.5 }}>{t("voz_clonada.o")}</span>
          <input type="file" accept=".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4"
                 aria-label={t("voz_clonada.archivo_aria")} disabled={!est.hay_key || grabando}
                 onChange={(e) => elegirArchivo(e.target.files[0] || null)} />
        </div>
        {muestra && (
          <p style={{ fontSize: 12.5, marginBottom: 0,
                      color: corta ? "var(--red)" : "var(--muted)" }}>
            {muestra.segundos != null
              ? t(corta ? "voz_clonada.muestra_corta" : "voz_clonada.muestra_lista",
                  { segundos: Math.round(muestra.segundos), minimo: est.duracion_minima_s })
              : t("voz_clonada.muestra_archivo", { archivo: muestra.nombreArchivo })}
          </p>
        )}
      </Paso>

      <Paso n="2" titulo={t("voz_clonada.paso2")} apagado={!muestra}>
        <div className="toolbar" style={{ flexWrap: "wrap", gap: 10 }}>
          <input type="text" value={nombre} maxLength={100} style={{ flex: 1, minWidth: 200 }}
                 aria-label={t("voz_clonada.nombre_ph")} placeholder={t("voz_clonada.nombre_ph")}
                 onChange={(e) => setNombre(e.target.value)} />
          <button className="btn" disabled={!puedeClonar} onClick={clonar}>
            {ocupado === "clonar" ? t("voz_clonada.clonando") : t("voz_clonada.clonar")}
          </button>
        </div>
        <label style={{ display: "flex", gap: 8, fontSize: 12.5, marginTop: 8, alignItems: "flex-start" }}>
          <input type="checkbox" checked={consiento} onChange={(e) => setConsiento(e.target.checked)} />
          {t("voz_clonada.consentimiento")}
        </label>
        <label style={{ display: "flex", gap: 8, fontSize: 12.5, marginTop: 6, alignItems: "center" }}>
          <input type="checkbox" checked={quitarRuido} onChange={(e) => setQuitarRuido(e.target.checked)} />
          {t("voz_clonada.quitar_ruido")}
        </label>
      </Paso>

      <Paso n="3" titulo={t("voz_clonada.paso3")} apagado={!activa}>
        <textarea value={texto} rows={2} maxLength={300} style={{ width: "100%" }}
                  aria-label={t("voz_clonada.texto_aria")} onChange={(e) => setTexto(e.target.value)} />
        <div className="toolbar" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn ghost" disabled={!activa || !!ocupado || !texto.trim()} onClick={probar}>
            {ocupado === "probar" ? t("voz_clonada.generando") : `▶ ${t("voz_clonada.escuchar")}`}
          </button>
          {audioUrl && <audio src={audioUrl} controls autoPlay style={{ height: 34 }} />}
        </div>
      </Paso>

      {est.hay_key && (
        <div style={{ marginTop: 14, fontSize: 12.5 }}>
          {voces === null ? (
            <button className="btn ghost" onClick={verVoces}>{t("voz_clonada.ver_voces")}</button>
          ) : (
            <select defaultValue="" aria-label={t("voz_clonada.ver_voces")} style={{ minWidth: 260 }}
                    onChange={(e) => elegir(e.target.value)}>
              <option value="">{t("voz_clonada.elegir_existente")}</option>
              {voces.map((v) => <option key={v.voice_id} value={v.voice_id}>{v.nombre}</option>)}
            </select>
          )}
        </div>
      )}

      {nota && (
        <p role="status" style={{ fontSize: 13, color: nota.ok ? "var(--green)" : "var(--red)" }}>
          {nota.texto}
        </p>
      )}
      <p style={{ color: "var(--faint)", fontSize: 11.5, marginBottom: 0 }}>{t("voz_clonada.nota_llamadas")}</p>
    </div>
  );
}
