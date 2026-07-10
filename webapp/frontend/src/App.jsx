import React, { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, cargarPais, getPais, getSesion, setSesion } from "./api.js";
import Tour from "./components/Tour.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Originacion from "./pages/Originacion.jsx";
import Cartera from "./pages/Cartera.jsx";
import Agenda from "./pages/Agenda.jsx";
import Gestores from "./pages/Gestores.jsx";
import Asistente from "./pages/Asistente.jsx";
import Configuracion from "./pages/Configuracion.jsx";

const NAV = [
  { ruta: "/", ico: "📊", txt: "Visión general" },
  { ruta: "/originacion", ico: "🏦", txt: "Originación" },
  { ruta: "/cartera", ico: "📋", txt: "Cartera priorizada" },
  { ruta: "/agenda", ico: "📅", txt: "Agenda de hoy" },
  { ruta: "/gestores", ico: "📇", txt: "Gestores" },
  { ruta: "/asistente", ico: "🤖", txt: "Asistente IA" },
  { ruta: "/configuracion", ico: "⚙️", txt: "Configuración", admin: true },
];

function PaisSelector({ esAdmin }) {
  const [pais, setPais] = useState(getPais());
  const [catalogo, setCatalogo] = useState(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    cargarPais().then(setPais).catch(() => {});
    if (esAdmin) api("/api/paises").then((r) => setCatalogo(r.paises)).catch(() => {});
  }, [esAdmin]);

  if (!esAdmin) {
    return (
      <div className="pais-chip" title={pais.nota_cumplimiento || ""}>
        🌎 {pais.nombre} · {pais.moneda}
      </div>
    );
  }

  return (
    <div className="pais-chip" title={pais.nota_cumplimiento || ""}>
      🌎
      <select
        disabled={guardando || !catalogo}
        value={pais.codigo}
        onChange={async (e) => {
          setGuardando(true);
          try {
            await api("/api/tenant/pais", { metodo: "POST", cuerpo: { codigo: e.target.value } });
            // Recarga completa: los formateadores de moneda leen un caché
            // de módulo, y es un cambio raro (una vez por tenant) — más
            // simple que enchufar un contexto reactivo para esto.
            window.location.reload();
          } catch {
            setGuardando(false);
          }
        }}
      >
        {(catalogo || [pais]).map((p) => (
          <option key={p.codigo} value={p.codigo}>{p.nombre} ({p.moneda})</option>
        ))}
      </select>
    </div>
  );
}

function Sidebar({ sesion }) {
  const nav = useNavigate();
  const loc = useLocation();
  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/mv_icon.png" alt="MV Kobra AI" />
        <b>MV KOBRA <span>AI</span></b>
      </div>
      {NAV.filter((n) => !n.admin || sesion.rol === "admin").map((n) => (
        <button key={n.ruta} onClick={() => nav(n.ruta)}
                className={"nav-item" + (loc.pathname === n.ruta ? " on" : "")}>
          <span className="ico">{n.ico}</span><span className="txt">{n.txt}</span>
        </button>
      ))}
      <div className="spacer" />
      <PaisSelector esAdmin={sesion.rol === "admin"} />
      <div className="session-chip">
        {sesion.rol === "admin" ? "🛡️ Administrador" : "👤 Gestor"} · {sesion.empresa}
      </div>
      <button className="nav-item" onClick={() => { setSesion(null); nav("/login"); }}>
        <span className="ico">⏻</span><span className="txt">Cerrar sesión</span>
      </button>
    </aside>
  );
}

export default function App() {
  const sesion = getSesion();
  const loc = useLocation();
  if (!sesion && loc.pathname !== "/login") return <Navigate to="/login" replace />;
  if (loc.pathname === "/login") return <Login />;
  return (
    <div className="layout">
      <Sidebar sesion={sesion} />
      <main className="main">
        <Tour />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/originacion" element={<Originacion />} />
          <Route path="/cartera" element={<Cartera />} />
          <Route path="/agenda" element={<Agenda />} />
          <Route path="/gestores" element={<Gestores />} />
          <Route path="/asistente" element={<Asistente />} />
          <Route path="/configuracion" element={<Configuracion />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
