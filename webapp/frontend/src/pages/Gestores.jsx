import React, { useEffect, useState } from "react";
import { api, fmtUYU } from "../api.js";
import { t } from "../i18n/index.js";

// Columnas curadas del ranking (en orden), con formato profesional — antes se
// volcaba el DataFrame crudo: columna "index" sin sentido, true/false pelados,
// montos sin separadores y tasas 0-1 sin %.
const COLS = [
  { clave: "gestor", tKey: "gestores.tabla.gestor", fmt: (v) => v },
  { clave: "gestiones", tKey: "gestores.tabla.gestiones", num: true, fmt: (v) => v },
  { clave: "calidad_prom", tKey: "gestores.tabla.calidad", num: true, fmt: (v) => Number(v).toFixed(1) },
  { clave: "tasa_conversion", tKey: "gestores.tabla.conversion", num: true, fmt: (v) => `${Math.round(v * 100)}%` },
  { clave: "tasa_recupero", tKey: "gestores.tabla.recupero_pct", num: true, fmt: (v) => `${Math.round(v * 100)}%` },
  { clave: "recupero", tKey: "gestores.tabla.recuperado", num: true, fmt: (v) => fmtUYU(v) },
  { clave: "monto", tKey: "gestores.tabla.gestionado", num: true, fmt: (v) => fmtUYU(v) },
  { clave: "usa_kobra", tKey: "gestores.tabla.usa_kobra", fmt: (v) => (String(v) === "true" ? "✅" : "—") },
];

export default function Gestores() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/gestores/resumen").then(setDatos).catch((e) => setError(e.message));
  }, []);

  const origen = datos && datos.origen;
  const tot = (datos && datos.totales) || null;
  const cols = datos && datos.ranking.length
    ? COLS.filter((c) => c.clave in datos.ranking[0])
    : COLS;

  return (
    <>
      <h1 className="page-title">
        {t("gestores.titulo")}
        {origen && (
          <span className={`badge-origen ${origen.es_real ? "real" : "demo"}`}
                title={origen.detalle}>
            ● {origen.etiqueta}
          </span>
        )}
      </h1>
      <p className="page-sub">{t("gestores.subtitulo")}</p>
      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("gestores.cargando")}</div>}
      {datos && !datos.ranking.length && (
        <div className="empty">{t("gestores.vacio_sin_gestiones")}</div>
      )}
      {datos && datos.ranking.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>#</th>
              {cols.map((c) => <th key={c.clave}>{t(c.tKey)}</th>)}
            </tr></thead>
            <tbody>
              {datos.ranking.map((r, i) => (
                <tr key={i} className="norow">
                  <td className="tnum">{i + 1}</td>
                  {cols.map((c) => (
                    <td key={c.clave} className={c.num ? "tnum" : undefined}>
                      {r[c.clave] == null ? "—" : c.fmt(r[c.clave])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            {tot && (
              <tfoot>
                <tr className="fila-total">
                  <td>—</td>
                  {cols.map((c) => {
                    const v = tot[c.clave];
                    // "usa_kobra" no se suma: se informa cuántos lo usan.
                    if (c.clave === "usa_kobra") {
                      return <td key={c.clave} className="tnum">
                        {tot.usan_kobra}/{tot.gestores}
                      </td>;
                    }
                    if (c.clave === "gestor") {
                      return <td key={c.clave}>{t("gestores.tabla.total")}</td>;
                    }
                    return <td key={c.clave} className={c.num ? "tnum" : undefined}>
                      {v == null ? "—" : c.fmt(v)}
                    </td>;
                  })}
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
      {tot && (
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
          {t("gestores.nota_totales")}
        </p>
      )}
    </>
  );
}
