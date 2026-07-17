import React, { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, cargarPais, getPais, getSesion, setPaisCache, setSesion } from "./api.js";
import { t } from "./i18n/index.js";
import Tour from "./components/Tour.jsx";
import Login from "./pages/Login.jsx";
import Activacion from "./pages/Activacion.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Originacion from "./pages/Originacion.jsx";
import Cartera from "./pages/Cartera.jsx";
import Agenda from "./pages/Agenda.jsx";
import Gestores from "./pages/Gestores.jsx";
import Asistente from "./pages/Asistente.jsx";
import Roi from "./pages/Roi.jsx";
import Configuracion from "./pages/Configuracion.jsx";

const NAV = [
  { ruta: "/", ico: "📊", clave: "app.nav.vision_general" },
  { ruta: "/originacion", ico: "🏦", clave: "app.nav.originacion" },
  { ruta: "/cartera", ico: "📋", clave: "app.nav.cartera" },
  { ruta: "/agenda", ico: "📅", clave: "app.nav.agenda" },
  { ruta: "/gestores", ico: "📇", clave: "app.nav.gestores" },
  { ruta: "/asistente", ico: "🤖", clave: "app.nav.asistente" },
  { ruta: "/roi", ico: "📈", clave: "app.nav.roi" },
  { ruta: "/configuracion", ico: "⚙️", clave: "app.nav.configuracion", admin: true },
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
            const nuevo = await api("/api/tenant/pais", { metodo: "POST", cuerpo: { codigo: e.target.value } });
            // Cachear ANTES de recargar: si no, la primera pintada de la
            // página recargada (sidebar incluido) lee el país viejo de
            // localStorage hasta que el propio PaisSelector vuelva a pedirlo.
            setPaisCache(nuevo);
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
          <span className="ico">{n.ico}</span><span className="txt">{t(n.clave)}</span>
        </button>
      ))}
      <div className="spacer" />
      <PaisSelector esAdmin={sesion.rol === "admin"} />
      <div className="session-chip">
        {sesion.rol === "admin" ? t("app.sidebar.rol_admin") : t("app.sidebar.rol_gestor")} · {sesion.empresa}
      </div>
      <button className="nav-item" onClick={() => { setSesion(null); nav("/login"); }}>
        <span className="ico">⏻</span><span className="txt">{t("app.sidebar.cerrar_sesion")}</span>
      </button>
    </aside>
  );
}

function DatosOrigenBanner() {
  const [origen, setOrigen] = useState(null);
  useEffect(() => { api("/api/cartera/origen").then(setOrigen).catch(() => {}); }, []);
  // Solo se avisa cuando son datos de demo — es la aclaración que importa
  // (honestidad de los números); con datos reales no hace falta un banner.
  if (!origen || origen.tipo !== "demo") return null;
  return (
    <div className="trial-banner" style={{ background: "rgba(47,116,192,.10)",
                                            borderColor: "rgba(47,116,192,.3)" }}>
      {t("importar_cartera.banner_demo")}
    </div>
  );
}

function TrialBanner({ licEstado }) {
  if (!licEstado || !licEstado.trial) return null;
  return (
    <div className="trial-banner">
      {t("activacion.banner_trial", { dias: licEstado.dias_restantes })}
      {" "}
      <a href="https://mvkobranzaia.com/#precios" target="_blank" rel="noreferrer">
        {t("activacion.link_comprar")}
      </a>
    </div>
  );
}

export default function App() {
  // undefined = todavía no se sabe (evita parpadear Login/Activación antes de
  // tiempo); en modo hosted (Vercel) standalone=false y esto no cambia nada.
  const [licEstado, setLicEstado] = useState(undefined);
  useEffect(() => {
    api("/api/licencia/estado").then(async (e) => {
      // Copia del owner (carpeta owner/): entra directo como admin, sin
      // licencia ni contraseña — el backend solo habilita ese endpoint en
      // el server local con KOBRA_OWNER=1.
      if (e.standalone && e.owner && !getSesion()) {
        try { setSesion(await api("/api/licencia/owner-login", { metodo: "POST", cuerpo: {} })); }
        catch { /* si falla, sigue el flujo normal de login */ }
      }
      // País/idioma ANTES del primer render real: si no, la barra lateral
      // pinta con el idioma viejo cacheado y no se vuelve a renderizar —
      // quedaba la app mezclada (contenido en portugués, menú en español)
      // hasta la próxima recarga.
      if (getSesion()) {
        try { await cargarPais(); } catch { /* offline: queda el cacheado */ }
      }
      setLicEstado(e);
    }).catch(() => setLicEstado({ standalone: false }));
  }, []);

  const sesion = getSesion();
  const loc = useLocation();

  if (licEstado === undefined) return null;
  if (licEstado.standalone && !licEstado.activa) {
    return (
      <Activacion
        vencida={licEstado.error === "licencia_expirada"}
        onActivada={(r) => setLicEstado({ standalone: true, activa: true,
                                          plan: r.plan, trial: r.trial, dias_restantes: r.dias_restantes })}
      />
    );
  }

  if (!sesion && loc.pathname !== "/login") return <Navigate to="/login" replace />;
  if (loc.pathname === "/login") return <Login />;
  return (
    <div className="layout">
      <Sidebar sesion={sesion} />
      <main className="main">
        <Tour />
        <TrialBanner licEstado={licEstado} />
        <DatosOrigenBanner />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/originacion" element={<Originacion />} />
          <Route path="/cartera" element={<Cartera />} />
          <Route path="/agenda" element={<Agenda />} />
          <Route path="/gestores" element={<Gestores />} />
          <Route path="/asistente" element={<Asistente />} />
          <Route path="/roi" element={<Roi />} />
          <Route path="/configuracion" element={<Configuracion />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
