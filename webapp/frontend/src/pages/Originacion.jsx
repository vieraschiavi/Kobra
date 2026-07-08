import React, { useEffect, useState } from "react";
import { api, fmtMonto } from "../api.js";

const PILL_DECISION = {
  "Aprobar": "alta",
  "Derivar a análisis": "media",
  "Rechazar": "baja",
};

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
              {detalle.decision} · score {detalle.score}
            </span>
            <div className="kv">
              <span className="k">Probabilidad de mora</span>
              <span className="tnum">{(detalle.prob_mora * 100).toFixed(1)}%</span>
              <span className="k">Solicita</span>
              <span className="tnum">{fmtMonto(solicitud.monto_solicitado)} · {solicitud.plazo_meses} meses</span>
              <span className="k">Sugerido</span>
              <span className="tnum">
                {detalle.monto_sugerido > 0
                  ? `${fmtMonto(detalle.monto_sugerido)} · ${detalle.plazo_sugerido_meses} meses`
                  : "—"}
              </span>
              <span className="k">Ingreso declarado</span>
              <span className="tnum">{fmtMonto(solicitud.ingreso_declarado)}</span>
              <span className="k">Perfil</span>
              <span>{solicitud.situacion_laboral} · {solicitud.tipo_credito} · {solicitud.departamento}</span>
              <span className="k">Historial interno</span>
              <span>{solicitud.creditos_previos} créditos previos · {solicitud.atrasos_previos} atrasos</span>
              <span className="k">Confianza del modelo</span>
              <span>{detalle.confianza} ({detalle.datos_presentes} datos presentes)</span>
            </div>
            <div className="guion">
              <b>Por qué (top {detalle.razones.length}):</b>{"\n"}
              {detalle.razones.map((r) =>
                `• ${r.factor}: ${r.direccion} (${r.efecto_pp > 0 ? "+" : ""}${r.efecto_pp} pp)`
              ).join("\n")}
              {"\n\n"}La decisión final es del oficial de crédito — el modelo sugiere y explica.
            </div>
          </>
        )}
      </aside>
    </>
  );
}

export default function Originacion() {
  const [datos, setDatos] = useState(null);
  const [sel, setSel] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/originacion/cola?n=20").then(setDatos).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="page-title">Originación — cola de decisiones</h1>
      <p className="page-sub">Cada solicitud llega evaluada: score, decisión sugerida y
        explicación. Hacé clic en una fila para ver el porqué. La decisión final siempre
        es del oficial de crédito.</p>

      {datos && (
        <div className="card" style={{ marginBottom: 16, fontSize: 13 }}>
          <b>Modelo (demo sintética · se reentrena con tus datos):</b>{" "}
          AUC walk-forward <span className="tnum">{datos.metricas_modelo.auc_walk_forward}</span>
          {" "}· KS <span className="tnum">{datos.metricas_modelo.ks_walk_forward}</span>
          {" "}· mejora vs. regla del oficial{" "}
          <span className="tnum" style={{ color: "var(--green-deep)" }}>
            +{datos.metricas_modelo.mejora_vs_regla}
          </span>
          {" "}· validación: {datos.metricas_modelo.validacion}
        </div>
      )}

      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">Cargando…</div>}
      {datos && (
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>Solicitud</th><th>Fecha</th><th>Tipo</th><th>Monto</th><th>Plazo</th>
              <th>Ingreso</th><th>Score</th><th>Decisión sugerida</th><th>Confianza</th>
            </tr></thead>
            <tbody>
              {datos.solicitudes.map((s) => (
                <tr key={s.id_solicitud} onClick={() => setSel(s)}>
                  <td>{s.id_solicitud}</td>
                  <td>{s.fecha_solicitud}</td>
                  <td>{s.tipo_credito}</td>
                  <td className="tnum">{fmtMonto(s.monto_solicitado)}</td>
                  <td className="tnum">{s.plazo_meses} m</td>
                  <td className="tnum">{fmtMonto(s.ingreso_declarado)}</td>
                  <td className="tnum"><b>{s.score}</b></td>
                  <td><span className={"pill " + PILL_DECISION[s.decision]}>{s.decision}</span></td>
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
