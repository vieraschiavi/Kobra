import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setSesion } from "../api.js";

export default function Login() {
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function entrar(e) {
    e.preventDefault();
    setCargando(true); setError("");
    try {
      const r = await api("/api/auth/login", { metodo: "POST", cuerpo: { password } });
      setSesion(r);
      nav("/");
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
        <p>Plataforma de cobranzas inteligentes</p>
        <form onSubmit={entrar}>
          <input type="password" placeholder="Contraseña" value={password}
                 onChange={(e) => setPassword(e.target.value)} autoFocus />
          <button className="btn" disabled={cargando || !password}>
            {cargando ? "Entrando…" : "Entrar"}
          </button>
        </form>
        {error && <div className="error-note">{error}</div>}
      </div>
    </div>
  );
}
