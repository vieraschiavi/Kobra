// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getSesion } from "../api.js";
import { t } from "../i18n/index.js";
import ModuloNoIncluido, { esFaltaDePlan } from "../components/ModuloNoIncluido.jsx";

const VERDE = "#00c896";
const AMBAR = "#f2b441";
const ROJO = "#ff7675";
const LIMA = "#7cc242";

const estiloTooltip = {
  background: "#0e1628", border: "1px solid #24344f",
  borderRadius: 8, color: "#eaf1fb",
};

// Las subidas de archivo van con fetch crudo: `api()` serializa JSON y acá
// hace falta FormData. Mismo criterio que descargarInforme en Dashboard.jsx.
async function subir(ruta, archivo, params = {}) {
  const ses = JSON.parse(localStorage.getItem("kobra_token") || "null");
  const fd = new FormData();
  fd.append("archivo", archivo);
  const qs = new URLSearchParams(params).toString();
  const r = await fetch(ruta + (qs ? `?${qs}` : ""), {
    method: "POST",
    headers: ses ? { Authorization: `Bearer ${ses.token}` } : {},
    body: fd,
  });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(cuerpo.detail || cuerpo.message || `Error ${r.status}`);
  return cuerpo;
}

// ── El resultado ─────────────────────────────────────────────────────────────
// La brecha entre selección y holdout se muestra SIEMPRE y con nombre propio:
// es cuánto se hubiera exagerado usando el método habitual, y ocultarla sería
// exactamente el problema que este módulo evita.
function Resultado({ r }) {
  const auc = r.holdout.auc;
  const color = auc >= 0.75 ? VERDE : auc >= 0.65 ? AMBAR : ROJO;
  const imp = (r.importancias || []).map((x) => ({
    columna: x.columna.length > 26 ? x.columna.slice(0, 25) + "…" : x.columna,
    peso: Math.round(x.peso * 1000) / 10,
  }));

  return (
    <>
      <div className="kpi-grid" style={{ marginTop: 16 }}>
        <div className="card kpi" style={{ borderTop: `3px solid ${color}` }}>
          <div className="label">{t("automl.kpi_auc")}</div>
          <div className="value tnum" style={{ color }}>{auc}</div>
          <div className="delta">{t("automl.kpi_auc_sub")}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("automl.kpi_modelo")}</div>
          <div className="value" style={{ fontSize: 17 }}>{r.modelo_elegido}</div>
          <div className="delta">{t("automl.kpi_modelo_sub", { n: r.candidatos.length })}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("automl.kpi_brecha")}</div>
          <div className="value tnum" style={{ fontSize: 24 }}>
            {r.brecha_seleccion_holdout > 0 ? "+" : ""}{r.brecha_seleccion_holdout}
          </div>
          <div className="delta">{t("automl.kpi_brecha_sub")}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("automl.kpi_corte")}</div>
          <div className="value" style={{ fontSize: 17 }}>
            {r.corte_temporal ? t("automl.corte_temporal") : t("automl.corte_aleatorio")}
          </div>
          <div className="delta">
            {t("automl.filas_reparto", {
              a: r.filas.entrenamiento, b: r.filas.seleccion, c: r.filas.holdout,
            })}
          </div>
        </div>
      </div>

      {r.avisos && r.avisos.length > 0 && (
        <div className="card" style={{ marginTop: 16, borderTop: `3px solid ${AMBAR}` }}>
          <h3 style={{ marginTop: 0 }}>{t("automl.avisos_titulo")}</h3>
          <ul style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.8, margin: 0 }}>
            {r.avisos.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}

      <div className="charts-grid" style={{ marginTop: 16 }}>
        {imp.length > 0 && (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>{t("automl.importancias_titulo")}</h3>
            <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("automl.importancias_sub")}</p>
            <ResponsiveContainer width="100%" height={Math.max(240, imp.length * 26)}>
              <BarChart data={imp} layout="vertical" margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
                <XAxis type="number" unit="%" tick={{ fill: "#93a5c0", fontSize: 11 }} />
                <YAxis type="category" dataKey="columna" width={150}
                       tick={{ fill: "#93a5c0", fontSize: 10.5 }} />
                <Tooltip contentStyle={estiloTooltip} formatter={(v) => `${v}%`} />
                <Bar dataKey="peso" fill={LIMA} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("automl.candidatos_titulo")}</h3>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("automl.candidatos_sub")}</p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>{t("automl.col_modelo")}</th>
                  <th style={{ textAlign: "right" }}>{t("automl.col_auc_seleccion")}</th>
                </tr>
              </thead>
              <tbody>
                {r.candidatos.map((c, i) => (
                  <tr key={i} style={c.modelo === r.modelo_elegido
                    ? { color: VERDE, fontWeight: 600 } : undefined}>
                    <td>{c.modelo}{c.modelo === r.modelo_elegido ? ` — ${t("automl.elegido")}` : ""}</td>
                    <td className="tnum" style={{ textAlign: "right" }}>{c.seleccion.auc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ color: "var(--faint)", fontSize: 11.5, marginTop: 10, marginBottom: 0 }}>
            {t("automl.nota_seleccion")}
          </p>
        </div>
      </div>
    </>
  );
}

export default function AutoML() {
  const [archivo, setArchivo] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [objetivo, setObjetivo] = useState("");
  const [fecha, setFecha] = useState("");
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState(null);
  const [sinPlan, setSinPlan] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const esAdmin = (getSesion() || {}).rol === "admin";

  const manejarError = (e) => {
      // 403 con el link de compra = falta el módulo en el plan.
      // Es distinto de un error: no hay nada roto que arreglar.
      const msg = String(e.message || e);
      (esFaltaDePlan(e) ? setSinPlan : setError)(msg);
  };

  const elegirArchivo = async (f) => {
    setArchivo(f); setPrevia(null); setResultado(null); setError(null);
    if (!f) return;
    setOcupado(true);
    try {
      const d = await subir("/api/automl/columnas", f);
      setPrevia(d);
      setObjetivo(d.columnas[d.columnas.length - 1] || "");
    } catch (e) { manejarError(e); } finally { setOcupado(false); }
  };

  const entrenar = async () => {
    setOcupado(true); setError(null); setResultado(null);
    try {
      const params = { objetivo };
      if (fecha) params.columna_fecha = fecha;
      setResultado(await subir("/api/automl/entrenar", archivo, params));
    } catch (e) { manejarError(e); } finally { setOcupado(false); }
  };

  if (sinPlan) return <ModuloNoIncluido modulo="automl" detalle={sinPlan} />;
  if (!esAdmin) {
    return (
      <div className="empty">{t("automl.solo_admin")}</div>
    );
  }

  return (
    <>
      <h2 className="page-title">{t("automl.titulo")}</h2>
      <p className="page-sub">{t("automl.subtitulo")}</p>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>{t("automl.paso1")}</h3>
        <input type="file" accept=".csv,.xlsx,.xls"
               onChange={(e) => elegirArchivo(e.target.files[0])} />
        <p style={{ color: "var(--faint)", fontSize: 12, marginBottom: 0 }}>
          {t("automl.nota_archivo")}
        </p>
      </div>

      {previa && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>{t("automl.paso2")}</h3>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            {t("automl.filas_leidas", { n: previa.filas.toLocaleString("es-UY") })}
          </p>
          <div className="grid-2" style={{ gap: 12 }}>
            <label>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>{t("automl.campo_objetivo")}</span>
              <select value={objetivo} onChange={(e) => setObjetivo(e.target.value)}>
                {previa.columnas.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>{t("automl.campo_fecha")}</span>
              <select value={fecha} onChange={(e) => setFecha(e.target.value)}>
                <option value="">{t("automl.sin_fecha")}</option>
                {previa.columnas.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>
          <p style={{ color: "var(--faint)", fontSize: 12 }}>{t("automl.nota_fecha")}</p>
          <button className="btn" onClick={entrenar} disabled={ocupado || !objetivo}>
            {ocupado ? t("automl.entrenando") : t("automl.entrenar")}
          </button>
        </div>
      )}

      {error && (
        <div className="card" style={{ marginTop: 16, borderTop: `3px solid ${ROJO}` }}>
          <strong style={{ color: ROJO }}>{t("automl.no_se_pudo")}</strong>
          <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 0 }}>{error}</p>
        </div>
      )}

      {resultado && <Resultado r={resultado} />}
    </>
  );
}
