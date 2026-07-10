import React, { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, fmtPct, fmtUYU, getPais } from "../api.js";

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
  if (!kpis || !graf) return <div className="empty">Cargando…</div>;

  return (
    <>
      <h1 className="page-title">Visión general</h1>
      <p className="page-sub">Tu cartera completa, priorizada por el modelo ProbPago — los
        mismos números que el pipeline, en tiempo real.</p>

      <div className="kpi-grid">
        <Kpi label="Deudores" value={kpis.deudores.toLocaleString(getPais().locale)} />
        <Kpi label={`Cartera (${getPais().moneda})`} value={fmtUYU(kpis.cartera_uyu)} />
        <Kpi label="Recupero esperado" value={fmtUYU(kpis.recupero_esperado_uyu)}
             delta={fmtPct(kpis.recupero_pct) + " de la cartera"} />
        <Kpi label="ProbPago promedio" value={fmtPct(kpis.probpago_promedio)} />
        <Kpi label="Mora promedio" value={Math.round(kpis.mora_promedio_dias) + " días"} />
        <Kpi label="Cartera en riesgo" value={fmtUYU(kpis.cartera_riesgo_uyu)}
             delta={"↑ " + fmtPct(kpis.riesgo_pct)} bad />
      </div>

      <div className="charts-grid">
        <div className="card">
          <h3>Cartera vs. recupero esperado por tramo de mora</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={graf.por_tramo}>
              <CartesianGrid stroke={GRIS} vertical={false} />
              <XAxis dataKey="tramo_mora" stroke={TINTA} fontSize={12} />
              <YAxis stroke={TINTA} fontSize={11}
                     tickFormatter={(v) => (v / 1e6).toFixed(0) + "M"} />
              <Tooltip {...estiloTooltip} formatter={(v) => fmtUYU(v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="cartera" name="Cartera" fill={AZUL} radius={[4, 4, 0, 0]} />
              <Bar dataKey="recupero" name="Recupero esperado" fill={VERDE} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>Distribución por propensión de pago</h3>
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
          <h3>Recupero esperado por segmento</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={graf.por_segmento}>
              <CartesianGrid stroke={GRIS} vertical={false} />
              <XAxis dataKey="segmento" stroke={TINTA} fontSize={12} />
              <YAxis stroke={TINTA} fontSize={11}
                     tickFormatter={(v) => (v / 1e6).toFixed(0) + "M"} />
              <Tooltip {...estiloTooltip} formatter={(v) => fmtUYU(v)} />
              <Bar dataKey="valor_esperado_recupero" name="Recupero esperado"
                   fill={LIMA} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>Top 10 departamentos por cartera</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={graf.top_departamentos} layout="vertical"
                      margin={{ left: 30 }}>
              <CartesianGrid stroke={GRIS} horizontal={false} />
              <XAxis type="number" stroke={TINTA} fontSize={11}
                     tickFormatter={(v) => (v / 1e6).toFixed(0) + "M"} />
              <YAxis type="category" dataKey="departamento" stroke={TINTA}
                     fontSize={11} width={90} />
              <Tooltip {...estiloTooltip} formatter={(v) => fmtUYU(v)} />
              <Bar dataKey="monto_deuda" name="Cartera" fill={AZUL} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}
