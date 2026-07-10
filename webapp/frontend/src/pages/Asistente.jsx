import React, { useState } from "react";
import { api } from "../api.js";
import { t } from "../i18n/index.js";

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
    </>
  );
}
