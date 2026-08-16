// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useState } from "react";
import { api, avisarPlan, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

const EMO_COLOR = {
  enojo: "var(--red)", frustracion: "var(--red)", ansiedad: "var(--amber)",
  resignacion: "var(--muted)", neutro: "var(--muted)", positivo: "var(--green-deep)",
};

function GestorIADemo() {
  const [canal, setCanal] = useState("Llamada");
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  const simular = async (c) => {
    setCanal(c); setCargando(true); setError(""); setRes(null);
    try {
      // `api()` ya avisa el plan por su cuenta (éxito o error) — no hace
      // falta envolver la respuesta acá.
      setRes(await api("/api/gestor-ia/demo", { metodo: "POST", cuerpo: { canal: c } }));
    } catch (e) { setError(e.message); }
    finally { setCargando(false); }
  };

  const esWpp = canal === "WhatsApp";
  const money = (n) => "$U " + Math.round(n).toLocaleString("es-UY");

  return (
    <div className="card" style={{ maxWidth: 820, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("gestor_demo.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("gestor_demo.subtitulo")}</p>
      <div className="toolbar" style={{ gap: 8 }}>
        <button className={"btn" + (canal === "Llamada" && res ? "" : " ghost")}
                disabled={cargando} onClick={() => simular("Llamada")}>
          {t("gestor_demo.por_voz")}
        </button>
        <button className={"btn" + (esWpp && res ? "" : " ghost")}
                disabled={cargando} onClick={() => simular("WhatsApp")}>
          {t("gestor_demo.por_whatsapp")}
        </button>
        {cargando && <span style={{ color: "var(--muted)", fontSize: 13 }}>{t("gestor_demo.negociando")}</span>}
      </div>
      {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}

      {res && (
        <>
          {/* Diagnóstico ProbPago */}
          <div className="toolbar" style={{ gap: 16, flexWrap: "wrap", fontSize: 12.5,
                 padding: "8px 12px", borderRadius: 10, background: "rgba(124,194,66,.08)" }}>
            <span><b>{res.brief.nombre}</b> · {res.brief.telefono}</span>
            <span>{t("gestor_demo.deuda")}: <b>{money(res.brief.monto_deuda)}</b></span>
            <span>ProbPago: <b style={{ color: "var(--green-deep)" }}>{(res.brief.probpago * 100).toFixed(0)}%</b></span>
            <span>{res.brief.estrategia}</span>
            <span>{t("gestor_demo.desc_max")}: <b>{(res.brief.descuento_recomendado * 100).toFixed(0)}%</b></span>
          </div>

          {/* Conversación como burbujas de chat */}
          <div style={{ margin: "14px 0", display: "flex", flexDirection: "column", gap: 8 }}>
            {res.turnos.map((tn, i) => (
              <div key={i} style={{ alignSelf: tn.quien === "gestor" ? "flex-start" : "flex-end",
                     maxWidth: "78%" }}>
                <div style={{ padding: "9px 13px", borderRadius: 12, fontSize: 13.5,
                       background: tn.quien === "gestor"
                         ? (esWpp ? "rgba(37,211,102,.14)" : "rgba(47,116,192,.14)")
                         : "var(--card2, rgba(255,255,255,.05))",
                       border: "1px solid rgba(255,255,255,.06)" }}>
                  <b style={{ fontSize: 11, color: "var(--muted)" }}>
                    {tn.quien === "gestor" ? t("gestor_demo.gestor_ia") : t("gestor_demo.cliente")}
                  </b>
                  <div>{tn.texto}</div>
                </div>
                {tn.quien === "cliente" && (
                  <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 3, textAlign: "right" }}>
                    {t("gestor_demo.ia_interpreta")}: {tn.sentimiento >= 0 ? "+" : ""}{tn.sentimiento}
                    {tn.senales.length > 0 && " · " + tn.senales.join(", ")}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Conclusiones que van al ERP */}
          <div className="tablewrap">
            <table style={{ minWidth: 0 }}>
              <tbody>
                <tr className="norow"><td>{t("gestor_demo.resultado")}</td>
                  <td><b style={{ color: "var(--green-deep)" }}>{res.conclusion.resultado}</b></td></tr>
                {res.conclusion.oferta && (
                  <tr className="norow"><td>{t("gestor_demo.acuerdo")}</td>
                    <td>{money(res.conclusion.oferta.total)}
                      {res.conclusion.oferta.cuotas > 1
                        ? ` · ${res.conclusion.oferta.cuotas} ${t("gestor_demo.cuotas_de")} ${money(res.conclusion.oferta.valor_cuota)}`
                        : ` · ${t("gestor_demo.al_contado")}`}
                      {` (${(res.conclusion.oferta.desc * 100).toFixed(0)}% ${t("gestor_demo.beneficio")})`}</td></tr>
                )}
                <tr className="norow"><td>{t("gestor_demo.fecha_promesa")}</td><td>{res.conclusion.fecha_promesa || "—"}</td></tr>
                <tr className="norow"><td>{t("gestor_demo.calidad")}</td><td>{res.conclusion.calidad_gestion}/100</td></tr>
                <tr className="norow"><td>{t("gestor_demo.emociones")}</td><td>{(res.conclusion.emociones || []).join(", ") || "—"}</td></tr>
                <tr className="norow"><td>{t("gestor_demo.tecnicas")}</td><td>{(res.conclusion.tecnicas || []).join(", ") || "—"}</td></tr>
                <tr className="norow"><td>{t("gestor_demo.turnos")}</td><td>{res.conclusion.turnos}</td></tr>
              </tbody>
            </table>
          </div>
          <p style={{ color: "var(--muted)", fontSize: 11.5, marginTop: 10 }}>
            {t("gestor_demo.nota_twilio")}
          </p>
        </>
      )}
    </div>
  );
}

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
      // Antes del throw: si el cupo se agotó (402), la MISMA respuesta trae
      // el plan actualizado — es el momento en que el chip más lo necesita.
      avisarPlan(d);
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
        <input type="file" accept=".wav,.mp3,audio/wav,audio/mpeg" aria-label={t("analizar_voz.archivo_aria")}
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
      {/* HTML propio y estatico: el texto sale del diccionario i18n del
          repo (src/i18n), no de la API ni del usuario. Lleva <b> y <br> a
          proposito. Cualquier dato dinamico va por {…}, nunca por aca. */}
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
      <GestorIADemo />
      <AnalizarVoz />
    </>
  );
}
