// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setSesion } from "../api.js";
import { t } from "../i18n/index.js";

export default function Login() {
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [modo, setModo] = useState(null);   // null = cargando, "login" | "setup"
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  // Primer arranque: si no hay admin configurado, mostramos el alta de
  // contraseña en vez del ingreso (antes había que abrir Streamlit — imposible
  // en hosting).
  useEffect(() => {
    api("/api/auth/estado")
      .then((e) => setModo(e.configurado ? "login" : "setup"))
      .catch(() => setModo("login"));
  }, []);

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

  async function crear(e) {
    e.preventDefault();
    setError("");
    if (password.length < 6) { setError(t("login.setup_corta")); return; }
    if (password !== password2) { setError(t("login.setup_no_coincide")); return; }
    setCargando(true);
    try {
      const r = await api("/api/auth/setup", { metodo: "POST", cuerpo: { password } });
      setSesion(r);
      nav("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  const esSetup = modo === "setup";

  // Spotlight que sigue al cursor (ver el bloque CINE de theme.css). El halo
  // lo pinta el CSS a partir de --mx/--my; acá solo se escriben esas dos
  // variables, y dentro de un rAF: el mousemove dispara decenas de eventos
  // por segundo y tocar el estilo en cada uno hace trabajar de más al
  // navegador. Se apaga solo si el visitante pidió menos movimiento o si no
  // hay un cursor de verdad (celular) — en ese caso el CSS ya cae a una
  // viñeta centrada, así que no hay nada que reemplazar.
  const luz = React.useRef(null);
  const frame = React.useRef(0);
  const mover = (e) => {
    const caja = luz.current;
    if (!caja || frame.current) return;
    const x = e.clientX, y = e.clientY;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      const r = caja.getBoundingClientRect();
      caja.style.setProperty("--mx", `${x - r.left}px`);
      caja.style.setProperty("--my", `${y - r.top}px`);
      caja.classList.add("con-luz");
    });
  };
  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  const animable = typeof window !== "undefined" &&
    window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <div className="login-wrap" ref={luz} onMouseMove={animable ? mover : undefined}>
      <div className="card login-card">
        <img src="/mv_icon.png" alt="MV Kobra AI" />
        <h1>MV KOBRA <span>AI</span></h1>
        <p>{esSetup ? t("login.setup_titulo") : t("login.subtitulo")}</p>
        {esSetup && <p style={{ fontSize: 13, color: "var(--muted)", marginTop: -6 }}>{t("login.setup_sub")}</p>}

        {modo === null ? (
          <p style={{ color: "var(--muted)" }}>…</p>
        ) : esSetup ? (
          <form onSubmit={crear}>
            {/* `aria-label` y no un `<label>` visible: el diseño de esta
                pantalla es de campos con placeholder. Pero el placeholder NO
                es un nombre accesible — desaparece al escribir y los lectores
                de pantalla lo tratan distinto según cuál sea. Sin esto, la
                primera pantalla del producto tiene dos campos sin nombre.
                `autoComplete` además le dice al gestor de contraseñas qué es
                cada uno, que es la diferencia entre que ofrezca guardarla o no. */}
            <input type="password" placeholder={t("login.setup_placeholder")}
                   aria-label={t("login.setup_placeholder")}
                   autoComplete="new-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} autoFocus />
            <input type="password" placeholder={t("login.setup_placeholder2")}
                   aria-label={t("login.setup_placeholder2")}
                   autoComplete="new-password" value={password2}
                   onChange={(e) => setPassword2(e.target.value)} />
            <button className="btn" disabled={cargando || !password || !password2}>
              {cargando ? t("login.setup_creando") : t("login.setup_boton")}
            </button>
          </form>
        ) : (
          <form onSubmit={entrar}>
            <input type="password" placeholder={t("login.input.placeholder_password")}
                   aria-label={t("login.input.placeholder_password")}
                   autoComplete="current-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} autoFocus />
            <button className="btn" disabled={cargando || !password}>
              {cargando ? t("login.boton.entrando") : t("login.boton.entrar")}
            </button>
          </form>
        )}
        {error && <div className="error-note">{error}</div>}
      </div>
    </div>
  );
}
