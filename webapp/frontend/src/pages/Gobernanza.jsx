// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api.js";
import { t } from "../i18n/index.js";
import ModuloNoIncluido, { esFaltaDePlan } from "../components/ModuloNoIncluido.jsx";

// Recharts no lee variables CSS, así que los colores van literales — mismo
// criterio que el resto de las páginas (ver Dashboard.jsx).
const VERDE = "#00c896";
const AMBAR = "#f2b441";
const ROJO = "#ff7675";
const AZUL = "#6c8cd5";
const GRIS = "#64748b";

// Cada nivel de sensibilidad con su color Y su texto. El color solo no
// alcanza: quien no distingue los matices tiene que poder leer el nivel
// igual (WCAG 1.4.1), así que la etiqueta siempre acompaña.
const COLOR_NIVEL = {
  publico: GRIS,
  interno: AZUL,
  personal: AMBAR,
  sensible: ROJO,
};

const estiloTooltip = {
  background: "#0e1628",
  border: "1px solid #24344f",
  borderRadius: 8,
  color: "#eaf1fb",
};

// ── Semáforo de una dimensión de calidad ─────────────────────────────────────
function Dimension({ nombre, pct }) {
  const color = pct >= 100 ? VERDE : pct >= 80 ? AMBAR : ROJO;
  return (
    <div className="card kpi" style={{ margin: 0, borderTop: `3px solid ${color}` }}>
      <div className="label">{t(`gobernanza.dim.${nombre}`)}</div>
      <div className="value tnum" style={{ color, fontSize: 26 }}>{pct}%</div>
    </div>
  );
}

export default function Gobernanza() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [sinPlan, setSinPlan] = useState(null);

  useEffect(() => {
    api("/api/gobernanza/resumen")
      .then(setDatos)
      .catch((e) => {
          // 403 con el link de compra = falta el módulo en el plan.
          // Es distinto de un error: no hay nada roto que arreglar.
          const msg = String(e.message || e);
          (esFaltaDePlan(e) ? setSinPlan : setError)(msg);
      });
  }, []);

  if (sinPlan) return <ModuloNoIncluido modulo="gobernanza" detalle={sinPlan} ventas={["venta_clasificacion", "venta_enmascarado", "venta_calidad", "venta_linaje"]} />;
  if (error) return <div className="empty">{error}</div>;
  if (!datos) return <div className="empty">{t("common.cargando")}</div>;

  const { por_nivel: porNivel, clasificacion, visibles, calidad, integridad_log: integridad } = datos;

  const datosNivel = Object.entries(porNivel)
    .filter(([, n]) => n > 0)
    .map(([nivel, n]) => ({ nivel: t(`gobernanza.nivel.${nivel}`), n, clave: nivel }));

  const fallas = (calidad.resultados || []).filter((r) => r.estado === "falla");
  const noAplican = (calidad.resultados || []).filter((r) => r.estado === "no_aplica");

  return (
    <>
      <h2 className="page-title">{t("gobernanza.titulo")}</h2>
      <p className="page-sub">{t("gobernanza.subtitulo")}</p>

      {/* Estado general */}
      <div className="kpi-grid">
        <div className="card kpi">
          <div className="label">{t("gobernanza.kpi_columnas")}</div>
          <div className="value tnum">{datos.columnas}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("gobernanza.kpi_filas")}</div>
          <div className="value tnum">{datos.filas.toLocaleString("es-UY")}</div>
        </div>
        <div className="card kpi" style={{ borderTop: `3px solid ${porNivel.sensible ? ROJO : GRIS}` }}>
          <div className="label">{t("gobernanza.kpi_sensibles")}</div>
          <div className="value tnum" style={{ color: porNivel.sensible ? ROJO : undefined }}>
            {porNivel.sensible + porNivel.personal}
          </div>
          <div className="delta">{t("gobernanza.kpi_sensibles_sub")}</div>
        </div>
        <div className="card kpi" style={{ borderTop: `3px solid ${calidad.apto ? VERDE : ROJO}` }}>
          <div className="label">{t("gobernanza.kpi_calidad")}</div>
          <div className="value" style={{ color: calidad.apto ? VERDE : ROJO, fontSize: 22 }}>
            {calidad.apto ? t("gobernanza.apto") : t("gobernanza.con_fallas")}
          </div>
          <div className="delta">
            {t("gobernanza.reglas_corridas", { n: calidad.reglas_corridas })}
          </div>
        </div>
      </div>

      {/* Las seis dimensiones DAMA */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("gobernanza.dimensiones_titulo")}</h3>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("gobernanza.dimensiones_sub")}</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12 }}>
          {Object.entries(calidad.por_dimension).map(([dim, pct]) => (
            <Dimension key={dim} nombre={dim} pct={pct} />
          ))}
        </div>
      </div>

      {/* Reglas que fallan — lo accionable va primero */}
      {fallas.length > 0 && (
        <div className="card" style={{ marginTop: 16, borderTop: `3px solid ${ROJO}` }}>
          <h3 style={{ marginTop: 0 }}>{t("gobernanza.fallas_titulo")}</h3>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>{t("gobernanza.col_regla")}</th>
                  <th>{t("gobernanza.col_dimension")}</th>
                  <th style={{ textAlign: "right" }}>{t("gobernanza.col_filas_malas")}</th>
                  <th>{t("gobernanza.col_por_que")}</th>
                </tr>
              </thead>
              <tbody>
                {fallas.map((f, i) => (
                  <tr key={i}>
                    <td>{f.regla}</td>
                    <td>{t(`gobernanza.dim.${f.dimension}`)}</td>
                    <td className="tnum" style={{ textAlign: "right", color: ROJO }}>
                      {f.malas.toLocaleString("es-UY")} ({f.pct_malas}%)
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 12.5 }}>{f.detalle}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Clasificación */}
      <div className="charts-grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("gobernanza.clasificacion_titulo")}</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={datosNivel} layout="vertical" margin={{ left: 20, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
              <XAxis type="number" allowDecimals={false} tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <YAxis type="category" dataKey="nivel" width={100} tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <Tooltip contentStyle={estiloTooltip} />
              <Bar dataKey="n" radius={[0, 3, 3, 0]}>
                {datosNivel.map((d) => (
                  <Cell key={d.clave} fill={COLOR_NIVEL[d.clave] || GRIS} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("gobernanza.catalogo_titulo")}</h3>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("gobernanza.catalogo_sub")}</p>
          <div className="tablewrap" style={{ maxHeight: 320, overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>{t("gobernanza.col_columna")}</th>
                  <th>{t("gobernanza.col_nivel")}</th>
                  <th>{t("gobernanza.col_ves")}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(clasificacion).map(([col, nivel]) => (
                  <tr key={col}>
                    <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{col}</td>
                    <td>
                      <span className="pill" style={{ borderColor: COLOR_NIVEL[nivel], color: COLOR_NIVEL[nivel] }}>
                        {t(`gobernanza.nivel.${nivel}`)}
                      </span>
                    </td>
                    <td style={{ fontSize: 12.5, color: visibles[col] ? "var(--ink)" : "var(--muted)" }}>
                      {visibles[col] ? t("gobernanza.en_claro") : t("gobernanza.enmascarada")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Integridad del registro */}
      <div className="card" style={{ marginTop: 16, borderTop: `3px solid ${integridad.ok ? VERDE : ROJO}` }}>
        <h3 style={{ marginTop: 0 }}>{t("gobernanza.integridad_titulo")}</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 8 }}>
          {t("gobernanza.integridad_sub")}
        </p>
        <div style={{ fontSize: 15, color: integridad.ok ? VERDE : ROJO, fontWeight: 600 }}>
          {integridad.ok ? t("gobernanza.integridad_ok") : t("gobernanza.integridad_rota")}
        </div>
      </div>

      {noAplican.length > 0 && (
        <p style={{ color: "var(--faint)", fontSize: 12, marginTop: 14 }}>
          {t("gobernanza.no_aplican", { n: noAplican.length })}
        </p>
      )}
    </>
  );
}
