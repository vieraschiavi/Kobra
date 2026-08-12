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
import Calidad from "./pages/Calidad.jsx";
import Asistente from "./pages/Asistente.jsx";
import Roi from "./pages/Roi.jsx";
import Configuracion from "./pages/Configuracion.jsx";
import PortalCobros from "./pages/PortalCobros.jsx";
import PortalPago from "./pages/PortalPago.jsx";
import {
  IcoAjustes, IcoAsistente, IcoBanco, IcoCalendario, IcoCalidad, IcoEquipo,
  IcoEscudo, IcoGlobo, IcoGrafica, IcoLista, IcoPago, IcoSalir, IcoTendencia,
  IcoUsuario,
} from "./icons.jsx";

// Iconos SVG de línea (ver icons.jsx) en vez de emojis: consistentes entre
// sistemas operativos y con el acabado sobrio que pide una plataforma B2B.
const NAV = [
  { ruta: "/", ico: <IcoGrafica />, clave: "app.nav.vision_general" },
  { ruta: "/originacion", ico: <IcoBanco />, clave: "app.nav.originacion" },
  { ruta: "/cartera", ico: <IcoLista />, clave: "app.nav.cartera" },
  { ruta: "/agenda", ico: <IcoCalendario />, clave: "app.nav.agenda" },
  { ruta: "/gestores", ico: <IcoEquipo />, clave: "app.nav.gestores" },
  { ruta: "/calidad", ico: <IcoCalidad />, clave: "app.nav.calidad" },
  { ruta: "/asistente", ico: <IcoAsistente />, clave: "app.nav.asistente" },
  { ruta: "/roi", ico: <IcoTendencia />, clave: "app.nav.roi" },
  { ruta: "/portal-cobros", ico: <IcoPago />, clave: "app.nav.portal_cobros", admin: true },
  { ruta: "/configuracion", ico: <IcoAjustes />, clave: "app.nav.configuracion", admin: true },
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
        <IcoGlobo size={14} /> {pais.nombre} · {pais.moneda}
      </div>
    );
  }

  return (
    <div className="pais-chip" title={pais.nota_cumplimiento || ""}>
      <IcoGlobo size={14} />
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

function Sidebar({ sesion, plan }) {
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
      <PlanChip plan={plan} />
      <PaisSelector esAdmin={sesion.rol === "admin"} />
      <div className="session-chip">
        {sesion.rol === "admin" ? <IcoEscudo size={12} /> : <IcoUsuario size={12} />}{" "}
        {sesion.rol === "admin" ? t("app.sidebar.rol_admin") : t("app.sidebar.rol_gestor")} · {sesion.empresa}
      </div>
      <button className="nav-item" onClick={() => { setSesion(null); nav("/login"); }}>
        <span className="ico"><IcoSalir /></span><span className="txt">{t("app.sidebar.cerrar_sesion")}</span>
      </button>
    </aside>
  );
}

// Consumo del plan, siempre a la vista en la barra lateral. El límite no
// puede aparecer recién cuando ya se chocó contra él: para cuando el cliente
// llegue a las 300 gestiones de Básico tiene que haberlo visto venir.
function PlanChip({ plan }) {
  if (!plan || plan.ilimitado) return null;
  const pct = plan.cupo > 0 ? Math.min(1, plan.usado / plan.cupo) : 0;
  const estado = plan.bloqueado ? "alto" : plan.avisar ? "medio" : "";
  return (
    <div className={"plan-chip " + estado}
         title={t("plan.chip", { usado: plan.usado, cupo: plan.cupo })}>
      <div className="plan-chip-txt">
        {t("plan.chip", { usado: plan.usado, cupo: plan.cupo })}
      </div>
      <div className="plan-barra"><i style={{ width: `${Math.round(pct * 100)}%` }} /></div>
    </div>
  );
}

function PlanBanner({ plan }) {
  if (!plan || plan.ilimitado) return null;
  let texto = null;
  if (plan.bloqueado) texto = t("plan.agotado", { cupo: plan.cupo });
  else if (plan.excedente > 0) texto = t("plan.excedente", { excedente: plan.excedente, cupo: plan.cupo });
  else if (plan.avisar) texto = t("plan.aviso", { usado: plan.usado, cupo: plan.cupo });
  if (!texto) return null;
  const rojo = plan.bloqueado;
  return (
    <div className="trial-banner" style={rojo ? { background: "rgba(200,54,54,.12)",
                                                  borderColor: "rgba(200,54,54,.35)" } : undefined}>
      {texto}{" "}
      <a href="https://mvkobranzaia.com/#precios" target="_blank" rel="noreferrer">
        {t("plan.link_mejorar")}
      </a>
    </div>
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

  // Consumo del plan. Se refresca solo cuando una pantalla acaba de gastar una
  // gestión: los endpoints medidos devuelven el estado nuevo en su respuesta y
  // la pantalla lo emite acá, así el chip no queda mostrando un número viejo
  // ni hay que poner un polling contra el propio backend local.
  const [plan, setPlan] = useState(null);
  useEffect(() => {
    const oir = (e) => { if (e.detail) setPlan(e.detail); };
    window.addEventListener("kobra:plan", oir);
    return () => window.removeEventListener("kobra:plan", oir);
  }, []);

  const sesion = getSesion();
  const loc = useLocation();
  useEffect(() => {
    if (!sesion) return;
    api("/api/plan").then(setPlan).catch(() => {});
  }, [sesion?.token]);

  // Portal público de pagos: lo abre el DEUDOR desde el link/QR que le mandó
  // la empresa. Sin login de la plataforma, sin sidebar, y antes de cualquier
  // pantalla de licencia — el deudor no es un usuario de Kobra.
  if (loc.pathname === "/pagar") return <PortalPago />;

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
      <Sidebar sesion={sesion} plan={plan} />
      <main className="main">
        <Tour />
        <TrialBanner licEstado={licEstado} />
        <PlanBanner plan={plan} />
        <DatosOrigenBanner />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/originacion" element={<Originacion />} />
          <Route path="/cartera" element={<Cartera />} />
          <Route path="/agenda" element={<Agenda />} />
          <Route path="/gestores" element={<Gestores />} />
          <Route path="/calidad" element={<Calidad />} />
          <Route path="/asistente" element={<Asistente />} />
          <Route path="/roi" element={<Roi />} />
          <Route path="/portal-cobros" element={<PortalCobros />} />
          <Route path="/configuracion" element={<Configuracion />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
