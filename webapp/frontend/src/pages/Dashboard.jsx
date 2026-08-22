// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, descargar, fmtPct, fmtUYU, getPais } from "../api.js";
import { t } from "../i18n/index.js";

// `avisar` es el `setError` de la página. El informe ejecutivo tarda en
// armarse: si falla y nadie dice nada, el usuario se queda mirando un botón
// que aparentemente no hizo nada — o peor, con un PDF de 40 bytes que no abre.
async function descargarInforme(avisar) {
  try {
    await descargar("/api/informe/ejecutivo.pdf", "informe_ejecutivo.pdf");
  } catch (e) {
    avisar(e.message);
  }
}

const VERDE = "#00c896", LIMA = "#7cc242", AMBAR = "#f2b441", ROJO = "#ff7675",
      AZUL = "#6c8cd5", GRIS = "#24344f", TINTA = "#93a5c0";
const COLOR_PROP = { Alta: VERDE, Media: AMBAR, Baja: ROJO };

const estiloTooltip = {
  contentStyle: { background: "#142036", border: "1px solid #24344f",
                  borderRadius: 10, fontSize: 12.5 },
  labelStyle: { color: "#eaf1fb" },
};

function Kpi({ label, value, delta, bad }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value tnum">{value}</div>
      {delta && <div className={"delta" + (bad ? " bad" : "")}>{delta}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [kpis, setKpis] = useState(null);
  const [graf, setGraf] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/kpis").then(setKpis).catch((e) => setError(e.message));
    api("/api/graficos/resumen").then(setGraf).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="empty">{error}</div>;
  if (!kpis || !graf) return <div className="empty">{t("common.cargando")}</div>;

  return (
    <>
      {/* `flexWrap` en el encabezado: el botón del informe no se encoge
          (`flexShrink: 0`, y con razón — el texto no se puede partir), así
          que en un celular sumaba 18px de desborde a toda la página. Al
          envolver, baja a su propia línea y ahí entra holgado. */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between",
                    gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="page-title">{t("dashboard.titulo")}</h1>
          <p className="page-sub">{t("dashboard.subtitulo")}</p>
        </div>
        <button className="btn ghost" style={{ flexShrink: 0 }} onClick={() => descargarInforme(setError)}>
          {t("dashboard.boton_informe")}
        </button>
      </div>

      <div className="kpi-grid">
        <Kpi label={t("dashboard.kpi.deudores")} value={kpis.deudores.toLocaleString(getPais().locale)} />
        <Kpi label={t("dashboard.kpi.cartera_label", { moneda: getPais().moneda })} value={fmtUYU(kpis.cartera_uyu)} />
        <Kpi label={t("dashboard.kpi.recupero_esperado")} value={fmtUYU(kpis.recupero_esperado_uyu)}
             delta={t("dashboard.kpi.recupero_esperado_delta", { pct: fmtPct(kpis.recupero_pct) })} />
        <Kpi label={t("dashboard.kpi.probpago_promedio")} value={fmtPct(kpis.probpago_promedio)} />
        <Kpi label={t("dashboard.kpi.mora_promedio")}
             value={t("dashboard.kpi.mora_promedio_valor", { dias: Math.round(kpis.mora_promedio_dias) })} />
        <Kpi label={t("dashboard.kpi.cartera_riesgo")} value={fmtUYU(kpis.cartera_riesgo_uyu)}
             delta={"↑ " + fmtPct(kpis.riesgo_pct)} bad />
      </div>

      <div className="charts-grid">
        <div className="card">
          <h3>{t("dashboard.chart.cartera_vs_recupero")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={graf.por_tramo}>
              <CartesianGrid stroke={GRIS} vertical={false} />
              <XAxis dataKey="tramo_mora" stroke={TINTA} fontSize={12} />
              <YAxis stroke={TINTA} fontSize={11}
                     tickFormatter={(v) => (v / 1e6).toFixed(0) + "M"} />
              <Tooltip {...estiloTooltip} formatter={(v) => fmtUYU(v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="cartera" name={t("dashboard.chart.serie_cartera")} fill={AZUL} radius={[4, 4, 0, 0]} />
              <Bar dataKey="recupero" name={t("dashboard.chart.serie_recupero_esperado")} fill={VERDE} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>{t("dashboard.chart.distribucion_propension")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={graf.propension} dataKey="cantidad" nameKey="segmento_propension"
                   innerRadius={60} outerRadius={95} paddingAngle={2}>
                {graf.propension.map((p) => (
                  <Cell key={p.segmento_propension}
                        fill={COLOR_PROP[p.segmento_propension] || LIMA} />
                ))}
              </Pie>
              <Tooltip {...estiloTooltip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>{t("dashboard.chart.recupero_por_segmento")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={graf.por_segmento}>
              <CartesianGrid stroke={GRIS} vertical={false} />
              <XAxis dataKey="segmento" stroke={TINTA} fontSize={12} />
              <YAxis stroke={TINTA} fontSize={11}
                     tickFormatter={(v) => (v / 1e6).toFixed(0) + "M"} />
              <Tooltip {...estiloTooltip} formatter={(v) => fmtUYU(v)} />
              <Bar dataKey="valor_esperado_recupero" name={t("dashboard.chart.serie_recupero_esperado")}
                   fill={LIMA} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>{t("dashboard.chart.top_departamentos")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={graf.top_departamentos} layout="vertical"
                      margin={{ left: 30 }}>
              <CartesianGrid stroke={GRIS} horizontal={false} />
              <XAxis type="number" stroke={TINTA} fontSize={11}
                     tickFormatter={(v) => (v / 1e6).toFixed(0) + "M"} />
              <YAxis type="category" dataKey="departamento" stroke={TINTA}
                     fontSize={11} width={90} />
              <Tooltip {...estiloTooltip} formatter={(v) => fmtUYU(v)} />
              <Bar dataKey="monto_deuda" name={t("dashboard.chart.serie_cartera")} fill={AZUL} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
