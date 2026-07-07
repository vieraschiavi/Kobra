import React, { useState } from "react";
import { api } from "../api.js";

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
      setChat((c) => [...c, { user: false, texto: "No pude responder: " + err.message }]);
    } finally {
      setCargando(false);
    }
  }

  return (
    <>
      <h1 className="page-title">Asistente IA</h1>
      <p className="page-sub">Preguntale al programa en español — responde con la propia
        documentación del producto (no inventa funciones). Con <code>ANTHROPIC_API_KEY</code>
        cargada, redacta; sin key, te muestra la sección exacta que contesta.</p>

      <div className="chat-box">
        {chat.length === 0 && (
          <div className="msg bot">Ejemplos: “¿qué necesito para llamar de verdad por
            teléfono?” · “¿cómo conecto mi ERP?” · “¿qué es ProbPago?”</div>
        )}
        {chat.map((m, i) => (
          <div key={i} className={"msg " + (m.user ? "user" : "bot")}>
            {m.texto}
            {m.fuentes?.length > 0 && (
              <div className="fuentes">Fuentes: {m.fuentes.join(" · ")}</div>
            )}
          </div>
        ))}
        {cargando && <div className="msg bot">Buscando en la documentación…</div>}
      </div>
      <form className="chat-form" onSubmit={preguntar}>
        <input type="text" value={pregunta} placeholder="Tu pregunta sobre MV Kobra AI…"
               onChange={(e) => setPregunta(e.target.value)} />
        <button className="btn" disabled={cargando || !pregunta.trim()}>Preguntar</button>
      </form>
    </>
  );
}
