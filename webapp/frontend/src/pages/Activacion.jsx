// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useState } from "react";
import { api, setSesion } from "../api.js";
import { t } from "../i18n/index.js";

// Puerta de entrada de la versión standalone (instalador de Windows): en vez
// de una contraseña arbitraria, lo que gatea el acceso es la licencia que el
// cliente recibió al comprar (o el trial de 7 días si descargó la demo desde
// mvkobranzaia.com). Ver webapp/backend/api.py::MODO_STANDALONE.
export default function Activacion({ onActivada, vencida }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function activar(e) {
    e.preventDefault();
    setCargando(true); setError("");
    try {
      const r = await api("/api/licencia/activar", { metodo: "POST", cuerpo: { token: token.trim() } });
      setSesion(r);
      onActivada(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <img src="/mv_icon.png" alt="MV Kobra AI" />
        <h1>MV KOBRA <span>AI</span></h1>
        <p>{vencida ? t("activacion.subtitulo_vencida") : t("activacion.subtitulo")}</p>
        <form onSubmit={activar}>
          <input type="text" placeholder={t("activacion.placeholder")} value={token}
                 onChange={(e) => setToken(e.target.value)} autoFocus />
          <button className="btn" disabled={cargando || !token.trim()}>
            {cargando ? t("activacion.boton_activando") : t("activacion.boton_activar")}
          </button>
        </form>
        {error && <div className="error-note">{error}</div>}
        <p className="login-nota">
          <a href="https://mvkobranzaia.com/#precios" target="_blank" rel="noreferrer">
            {t("activacion.link_comprar")}
          </a>
        </p>
      </div>
    </div>
  );
}
