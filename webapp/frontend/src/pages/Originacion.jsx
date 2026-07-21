import React, { useEffect, useState } from "react";
import { api, fmtMonto, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

// La API de originación (kobra/originacion.py) siempre devuelve estas 3
// decisiones en español — son datos, no texto de UI — así que la clave de
// esta tabla queda en español; solo la etiqueta que se muestra se traduce.
const PILL_DECISION = {
  "Aprobar": "alta",
  "Derivar a análisis": "media",
  "Rechazar": "baja",
};
const CLAVE_DECISION = {
  "Aprobar": "originacion.decision.aprobar",
  "Derivar a análisis": "originacion.decision.derivar",
  "Rechazar": "originacion.decision.rechazar",
};
const tDecision = (d) => t(CLAVE_DECISION[d] || d);

const CAMPOS_SOLICITUD = [
  "edad", "ingreso_declarado", "antiguedad_laboral_meses", "monto_solicitado",
  "plazo_meses", "antiguedad_socio_meses", "creditos_previos", "atrasos_previos",
  "tipo_credito", "situacion_laboral", "departamento",
];

function DrawerSolicitud({ solicitud, onClose }) {
  const [detalle, setDetalle] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const cuerpo = { solicitud: Object.fromEntries(
      CAMPOS_SOLICITUD.map((c) => [c, solicitud[c]])) };
    api("/api/originacion/score", { metodo: "POST", cuerpo })
      .then(setDetalle).catch((e) => setError(e.message));
  }, [solicitud]);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer">
        <button className="btn ghost close" onClick={onClose}>✕</button>
        <h2>{solicitud.id_solicitud}</h2>
        {error && <div className="empty">{error}</div>}
        {detalle && (
          <>
            <span className={"pill " + PILL_DECISION[detalle.decision]}>
              {tDecision(detalle.decision)} · score {detalle.score}
            </span>
            <div className="kv">
              <span className="k">{t("originacion.drawer.probabilidad_mora")}</span>
              <span className="tnum">{(detalle.prob_mora * 100).toFixed(1)}%</span>
              <span className="k">{t("originacion.drawer.solicita")}</span>
              <span className="tnum">{fmtMonto(solicitud.monto_solicitado)} · {solicitud.plazo_meses} {t("originacion.drawer.meses_sufijo")}</span>
              <span className="k">{t("originacion.drawer.sugerido")}</span>
              <span className="tnum">
                {detalle.monto_sugerido > 0
                  ? `${fmtMonto(detalle.monto_sugerido)} · ${detalle.plazo_sugerido_meses} ${t("originacion.drawer.meses_sufijo")}`
                  : "—"}
              </span>
              <span className="k">{t("originacion.drawer.ingreso_declarado")}</span>
              <span className="tnum">{fmtMonto(solicitud.ingreso_declarado)}</span>
              <span className="k">{t("originacion.drawer.perfil")}</span>
              <span>{solicitud.situacion_laboral} · {solicitud.tipo_credito} · {solicitud.departamento}</span>
              <span className="k">{t("originacion.drawer.historial_interno")}</span>
              <span>{solicitud.creditos_previos} {t("originacion.drawer.creditos_previos_sufijo")} · {solicitud.atrasos_previos} {t("originacion.drawer.atrasos_sufijo")}</span>
              <span className="k">{t("originacion.drawer.confianza_modelo")}</span>
              <span>{detalle.confianza} ({detalle.datos_presentes} {t("originacion.drawer.datos_presentes_sufijo")})</span>
            </div>
            <div className="guion">
              <b>{t("originacion.drawer.por_que_titulo", { n: detalle.razones.length })}</b>{"\n"}
              {detalle.razones.map((r) =>
                `• ${r.factor}: ${r.direccion} (${r.efecto_pp > 0 ? "+" : ""}${r.efecto_pp} ${t("originacion.drawer.pp_sufijo")})`
              ).join("\n")}
              {"\n\n"}{t("originacion.drawer.decision_final")}
            </div>
          </>
        )}
      </aside>
    </>
  );
}

// Panel para cargar el dataset real de solicitudes de originación.
function ImportarOrig({ onListo }) {
  const [archivo, setArchivo] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  const subir = async () => {
    if (!archivo) return;
    setCargando(true); setError(""); setMsg("");
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const ses = getSesion();
      const r = await fetch("/api/originacion/importar", {
        method: "POST", headers: ses ? { Authorization: `Bearer ${ses.token}` } : {}, body: fd });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
      setMsg(`${d.solicitudes} ${t("originacion.importar_ok")}`);
      onListo && onListo();
    } catch (e) { setError(e.message.replace(/^\d+:\s*/, "")); }
    finally { setCargando(false); }
  };

  return (
    <div className="card" style={{ marginBottom: 16, maxWidth: 760 }}>
      <h3 style={{ marginTop: 0 }}>{t("originacion.importar_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("originacion.importar_sub")}</p>
      <div className="toolbar" style={{ gap: 8, flexWrap: "wrap" }}>
        <input type="file" accept=".csv,.xlsx,.xls"
               onChange={(e) => setArchivo(e.target.files[0] || null)} />
        <button className="btn" disabled={!archivo || cargando} onClick={subir}>
          {cargando ? t("originacion.importar_procesando") : t("originacion.importar_boton")}
        </button>
        {msg && <span style={{ color: "var(--green-deep)", fontSize: 13 }}>{msg}</span>}
        {error && <span style={{ color: "var(--red)", fontSize: 13 }}>{error}</span>}
      </div>
    </div>
  );
}

export default function Originacion() {
  const [datos, setDatos] = useState(null);
  const [sel, setSel] = useState(null);
  const [error, setError] = useState("");

  const cargar = () => api("/api/originacion/cola?n=20").then(setDatos).catch((e) => setError(e.message));
  useEffect(() => { cargar(); }, []);

  const esReal = datos && datos.es_real;
  const sinDatos = datos && datos.sin_datos_reales;

  return (
    <>
      <h1 className="page-title">{t("originacion.titulo")}
        {datos && <span className="pill" style={{ marginLeft: 10, fontSize: 12,
          background: esReal ? "#00c89622" : "#f2b44122", color: esReal ? "#00c896" : "#f2b441" }}>
          {esReal ? "● " + t("originacion.modo_real") : "○ " + t("originacion.modo_demo")}</span>}
      </h1>
      <p className="page-sub">{t("originacion.subtitulo")}</p>

      {/* En modo real sin dataset propio: se informa y se ofrece cargarlo (no
          se inventa una cola sintética). En demo, el import queda disponible igual. */}
      {(sinDatos || esReal) && <ImportarOrig onListo={cargar} />}
      {sinDatos && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid #f2b441" }}>
          <p style={{ margin: 0, fontSize: 13.5 }}>{datos.aviso}</p>
        </div>
      )}

      {datos && !sinDatos && (
        <div className="card" style={{ marginBottom: 16, fontSize: 13 }}>
          <b>{t("originacion.modelo.prefijo")}</b>{" "}
          {t("originacion.modelo.auc_label")} <span className="tnum">{datos.metricas_modelo.auc_walk_forward}</span>
          {" "}{t("originacion.modelo.ks_label")} <span className="tnum">{datos.metricas_modelo.ks_walk_forward}</span>
          {" "}{t("originacion.modelo.mejora_label")}{" "}
          <span className="tnum" style={{ color: "var(--green-deep)" }}>
            +{datos.metricas_modelo.mejora_vs_regla}
          </span>
          {" "}{t("originacion.modelo.validacion_label")} {datos.metricas_modelo.validacion}
        </div>
      )}

      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("common.cargando")}</div>}
      {datos && !sinDatos && (
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>{t("originacion.tabla.col_solicitud")}</th><th>{t("originacion.tabla.col_fecha")}</th>
              <th>{t("originacion.tabla.col_tipo")}</th><th>{t("originacion.tabla.col_monto")}</th>
              <th>{t("originacion.tabla.col_plazo")}</th>
              <th>{t("originacion.tabla.col_ingreso")}</th><th>{t("originacion.tabla.col_score")}</th>
              <th>{t("originacion.tabla.col_decision")}</th><th>{t("originacion.tabla.col_confianza")}</th>
            </tr></thead>
            <tbody>
              {datos.solicitudes.map((s) => (
                <tr key={s.id_solicitud} onClick={() => setSel(s)}>
                  <td>{s.id_solicitud}</td>
                  <td>{s.fecha_solicitud}</td>
                  <td>{s.tipo_credito}</td>
                  <td className="tnum">{fmtMonto(s.monto_solicitado)}</td>
                  <td className="tnum">{s.plazo_meses} {t("originacion.tabla.plazo_sufijo")}</td>
                  <td className="tnum">{fmtMonto(s.ingreso_declarado)}</td>
                  <td className="tnum"><b>{s.score}</b></td>
                  <td><span className={"pill " + PILL_DECISION[s.decision]}>{tDecision(s.decision)}</span></td>
                  <td>{s.confianza}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {sel && <DrawerSolicitud solicitud={sel} onClose={() => setSel(null)} />}
    </>
  );
}
