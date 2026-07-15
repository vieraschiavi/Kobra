import React, { useState } from "react";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

const EMO_COLOR = {
  enojo: "var(--red)", frustracion: "var(--red)", ansiedad: "var(--amber)",
  resignacion: "var(--muted)", neutro: "var(--muted)", positivo: "var(--green-deep)",
};

function AnalizarVoz() {
  const [archivo, setArchivo] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  const elegir = (f) => {
    setArchivo(f || null);
    setResultado(null); setError("");
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  };

  const analizar = async () => {
    if (!archivo) return;
    setCargando(true); setError(""); setResultado(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const ses = getSesion();
      const r = await fetch("/api/voz/analizar", {
        method: "POST",
        headers: ses ? { Authorization: `Bearer ${ses.token}` } : {},
        body: fd,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
      setResultado(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="card" style={{ maxWidth: 820, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("analizar_voz.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("analizar_voz.subtitulo")}</p>
      <div className="toolbar">
        <input type="file" accept=".wav,.mp3,audio/wav,audio/mpeg"
               onChange={(e) => elegir(e.target.files[0] || null)} />
        <button className="btn" disabled={!archivo || cargando} onClick={analizar}>
          {cargando ? t("analizar_voz.analizando") : t("analizar_voz.boton")}
        </button>
      </div>
      {previewUrl && <audio controls src={previewUrl} style={{ width: "100%", marginBottom: 12 }} />}
      {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}
      {resultado && (
        <>
          <div className="toolbar" style={{ gap: 18 }}>
            <span><b>{resultado.voz.canales}</b> {t("analizar_voz.canales")}</span>
            <span>{resultado.voz.modo_diarizacion}</span>
            <span>{resultado.voz.duracion_seg.toFixed(0)}s</span>
            <span>{resultado.voz.timeline.length} {t("analizar_voz.segmentos")}</span>
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>{t("analizar_voz.tabla.hablante")}</th>
                <th>{t("analizar_voz.tabla.tiempo")}</th>
                <th>{t("analizar_voz.tabla.emocion")}</th>
              </tr></thead>
              <tbody>
                {resultado.voz.timeline.map((s, i) => (
                  <tr key={i} className="norow">
                    <td>{s.hablante}</td>
                    <td style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {s.inicio.toFixed(1)}s–{s.fin.toFixed(1)}s
                    </td>
                    <td style={{ color: EMO_COLOR[s.emocion_voz] || "var(--muted)", fontWeight: 700 }}>
                      {s.emocion_voz}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {resultado.copiloto ? (
            <p style={{ fontSize: 13, marginTop: 10 }}>
              {t("analizar_voz.copiloto_ok")}
            </p>
          ) : (
            <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 10 }}>
              {t("analizar_voz.sin_transcripcion")}
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default function Asistente() {
  const [chat, setChat] = useState([]);
  const [pregunta, setPregunta] = useState("");
  const [cargando, setCargando] = useState(false);

  async function preguntar(e) {
    e.preventDefault();
    const p = pregunta.trim();
    if (!p) return;
    setPregunta(""); setCargando(true);
    setChat((c) => [...c, { user: true, texto: p }]);
    try {
      const r = await api("/api/ayuda", { metodo: "POST", cuerpo: { pregunta: p } });
      setChat((c) => [...c, { user: false, texto: r.respuesta, fuentes: r.fuentes }]);
    } catch (err) {
      setChat((c) => [...c, { user: false, texto: t("asistente.error_no_pude_responder") + err.message }]);
    } finally {
      setCargando(false);
    }
  }

  return (
    <>
      <h1 className="page-title">{t("asistente.titulo")}</h1>
      <p className="page-sub" dangerouslySetInnerHTML={{ __html: t("asistente.subtitulo") }} />

      <div className="chat-box">
        {chat.length === 0 && (
          <div className="msg bot">{t("asistente.chat.ejemplo")}</div>
        )}
        {chat.map((m, i) => (
          <div key={i} className={"msg " + (m.user ? "user" : "bot")}>
            {m.texto}
            {m.fuentes?.length > 0 && (
              <div className="fuentes">{t("asistente.chat.fuentes_prefijo")} {m.fuentes.join(" · ")}</div>
            )}
          </div>
        ))}
        {cargando && <div className="msg bot">{t("asistente.chat.buscando")}</div>}
      </div>
      <form className="chat-form" onSubmit={preguntar}>
        <input type="text" value={pregunta} placeholder={t("asistente.placeholder_input")}
               onChange={(e) => setPregunta(e.target.value)} />
        <button className="btn" disabled={cargando || !pregunta.trim()}>{t("asistente.boton_preguntar")}</button>
      </form>
      <AnalizarVoz />
    </>
  );
}
