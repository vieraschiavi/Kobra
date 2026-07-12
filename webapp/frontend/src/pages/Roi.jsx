import React, { useState } from "react";
import { fmtUYU, fmtPct, getPais } from "../api.js";
import { t } from "../i18n/index.js";

// Calculadora de ROI para la reunión de venta. Todo el cálculo es local y
// transparente: la "mejora de recupero" es un SUPUESTO editable y está
// rotulada como tal — el número honesto sale del piloto con cartera real,
// no de esta pantalla (misma convención de honestidad que el resto).
export default function Roi() {
  const p = getPais();
  const [cartera, setCartera] = useState(100_000_000);
  const [recuperoActual, setRecuperoActual] = useState(30);   // % anual de la cartera
  const [mejora, setMejora] = useState(10);                    // % relativo, supuesto editable
  const [costoAnual, setCostoAnual] = useState(0);

  const recuperoHoy = cartera * (recuperoActual / 100);
  const adicionalMedio = recuperoHoy * (mejora / 100);
  const adicionalConservador = adicionalMedio / 2;
  const roi = (x) => (costoAnual > 0 ? x / costoAnual : null);
  const meses = (x) => (x > 0 && costoAnual > 0 ? Math.ceil(costoAnual / (x / 12)) : null);

  const num = (setter) => (e) => setter(Math.max(0, Number(e.target.value) || 0));

  const Fila = ({ label, children }) => (
    <label style={{ display: "grid", gap: 4, marginBottom: 14 }}>
      <span style={{ color: "var(--muted)", fontSize: 13 }}>{label}</span>
      {children}
    </label>
  );

  const Escenario = ({ titulo, adicional }) => (
    <div className="card" style={{ flex: 1, minWidth: 240 }}>
      <h3 style={{ marginTop: 0 }}>{titulo}</h3>
      <div className="kv">
        <span className="k">{t("roi.res.adicional")}</span>
        <span className="tnum" style={{ color: "var(--green-deep)", fontWeight: 800 }}>
          {fmtUYU(adicional)}
        </span>
        <span className="k">{t("roi.res.roi")}</span>
        <span className="tnum">{roi(adicional) ? roi(adicional).toFixed(1) + "×" : "—"}</span>
        <span className="k">{t("roi.res.repago")}</span>
        <span className="tnum">
          {meses(adicional) ? t("roi.res.meses", { n: meses(adicional) }) : "—"}
        </span>
      </div>
    </div>
  );

  return (
    <>
      <h1 className="page-title">{t("roi.titulo")}</h1>
      <p className="page-sub">{t("roi.subtitulo")}</p>

      <div className="grid-2">
        <div className="card">
          <Fila label={t("roi.in.cartera", { moneda: p.moneda })}>
            <input type="number" value={cartera} onChange={num(setCartera)} />
          </Fila>
          <Fila label={t("roi.in.recupero_actual")}>
            <input type="number" value={recuperoActual} onChange={num(setRecuperoActual)} />
          </Fila>
          <Fila label={t("roi.in.costo", { moneda: p.moneda })}>
            <input type="number" value={costoAnual} onChange={num(setCostoAnual)}
                   placeholder={t("roi.in.costo_placeholder")} />
          </Fila>
          <Fila label={t("roi.in.mejora")}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <input type="range" min="2" max="25" step="1" value={mejora}
                     onChange={(e) => setMejora(Number(e.target.value))} style={{ flex: 1 }} />
              <b className="tnum" style={{ width: 46 }}>{mejora}%</b>
            </div>
          </Fila>
          <p style={{ color: "var(--amber)", fontSize: 12.5, margin: 0 }}>
            {t("roi.supuesto")}
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="card kpi">
            <div className="label">{t("roi.res.recupero_hoy")}</div>
            <div className="value tnum">{fmtUYU(recuperoHoy)}</div>
            <div className="delta">{fmtPct(recuperoActual / 100, 0)} · {t("roi.res.por_anio")}</div>
          </div>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <Escenario titulo={t("roi.esc.conservador", { pct: (mejora / 2).toFixed(0) })}
                       adicional={adicionalConservador} />
            <Escenario titulo={t("roi.esc.medio", { pct: mejora })}
                       adicional={adicionalMedio} />
          </div>
        </div>
      </div>
    </>
  );
}
