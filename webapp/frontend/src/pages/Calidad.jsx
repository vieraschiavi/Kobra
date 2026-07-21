import React, { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api.js";
import { t } from "../i18n/index.js";

const COL_IA = "#00c896";
const COL_HUM = "#2f74c0";
const colorTipo = (tipo) => (tipo === "IA" ? COL_IA : COL_HUM);

// ── Comparativa Gestor IA vs Gestor Humano ──────────────────────────────────
function Comparativa() {
  const [data, setData] = useState(null);
  const [canal, setCanal] = useState("");
  const [error, setError] = useState("");

  const cargar = (cn) =>
    api("/api/calidad/comparativa" + (cn ? `?canal=${encodeURIComponent(cn)}` : ""))
      .then(setData).catch((e) => setError(e.message));
  useEffect(() => { cargar(canal); /* eslint-disable-next-line */ }, [canal]);

  if (error) return <div className="empty">{error}</div>;
  if (!data) return <div className="empty">{t("calidad.cargando")}</div>;

  const money = (n) => "$U " + Math.round(n).toLocaleString("es-UY");
  const chartData = data.por_tipo.map((x) => ({
    tipo: x.tipo === "IA" ? t("calidad.gestor_ia") : t("calidad.gestor_humano"),
    tipoRaw: x.tipo, Calidad: x.calidad_prom, Conversión: x.tasa_conversion,
  }));

  return (
    <>
      <div className="toolbar" style={{ gap: 10, marginBottom: 14 }}>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.filtro_canal")}:</span>
        <select value={canal} onChange={(e) => setCanal(e.target.value)}>
          <option value="">{t("calidad.todos_canales")}</option>
          {(data.canales || []).map((cn) => <option key={cn} value={cn}>{cn}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 12.5 }}>
          {data.total_gestiones.toLocaleString("es-UY")} {t("calidad.gestiones")}
        </span>
      </div>

      {/* KPIs por tipo */}
      <div className="kpi-row" style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 14 }}>
        {data.por_tipo.map((x) => (
          <div key={x.tipo} className="card kpi" style={{ borderTop: `3px solid ${colorTipo(x.tipo)}` }}>
            <div className="label">{x.tipo === "IA" ? t("calidad.gestor_ia") : t("calidad.gestor_humano")}
              · {x.gestiones.toLocaleString("es-UY")} {t("calidad.gestiones")}</div>
            <div className="value" style={{ color: colorTipo(x.tipo) }}>{x.calidad_prom}<span style={{ fontSize: 14 }}>/100</span></div>
            <div className="delta">{t("calidad.conversion")}: <b>{x.tasa_conversion}%</b> · {t("calidad.recupero")}: {money(x.recupero_total)}</div>
          </div>
        ))}
      </div>

      {/* Gráfico comparativo */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("calidad.titulo_grafico")}</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
            <XAxis dataKey="tipo" tick={{ fill: "#93a5c0", fontSize: 12 }} />
            <YAxis tick={{ fill: "#93a5c0", fontSize: 12 }} />
            <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #2f74c0" }} />
            <Legend />
            <Bar dataKey="Calidad" radius={[4, 4, 0, 0]}>
              {chartData.map((d, i) => <Cell key={i} fill={colorTipo(d.tipoRaw)} />)}
            </Bar>
            <Bar dataKey="Conversión" radius={[4, 4, 0, 0]} fill="#f2b441" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Ranking por gestor */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("calidad.ranking")}</h3>
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>#</th><th>{t("calidad.gestor")}</th><th>{t("calidad.tipo")}</th>
              <th>{t("calidad.gestiones")}</th><th>{t("calidad.calidad")}</th>
              <th>{t("calidad.conversion")}</th><th>{t("calidad.recupero")}</th>
            </tr></thead>
            <tbody>
              {data.ranking.map((r, i) => (
                <tr key={r.gestor_id} className="norow">
                  <td className="tnum">{i + 1}</td>
                  <td>{r.gestor}</td>
                  <td><span className="pill" style={{ background: colorTipo(r.tipo) + "22", color: colorTipo(r.tipo) }}>
                    {r.tipo === "IA" ? t("calidad.gestor_ia") : t("calidad.gestor_humano")}</span></td>
                  <td className="tnum">{r.gestiones.toLocaleString("es-UY")}</td>
                  <td className="tnum"><b>{r.calidad_prom}</b></td>
                  <td className="tnum">{r.tasa_conversion}%</td>
                  <td className="tnum">{money(r.recupero_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ── Evaluador de una gestión ────────────────────────────────────────────────
function Evaluador() {
  const [texto, setTexto] = useState("");
  const [canal, setCanal] = useState("Llamada");
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  const evaluar = async () => {
    setCargando(true); setError(""); setRes(null);
    try {
      setRes(await api("/api/calidad/evaluar", { metodo: "POST", cuerpo: { transcripcion: texto, canal } }));
    } catch (e) { setError(e.message.replace(/^\d+:\s*/, "")); }
    finally { setCargando(false); }
  };

  const color = (c) => c.cumplido ? "var(--green-deep)" : c.parcial ? "var(--amber)" : "var(--red)";

  return (
    <div className="card" style={{ marginTop: 16, maxWidth: 900 }}>
      <h3 style={{ marginTop: 0 }}>{t("calidad.evaluar_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.evaluar_sub")}</p>
      <div className="toolbar" style={{ gap: 8 }}>
        <select value={canal} onChange={(e) => setCanal(e.target.value)}>
          <option value="Llamada">📞 {t("calidad.canal_llamada")}</option>
          <option value="WhatsApp">💬 WhatsApp</option>
        </select>
      </div>
      <textarea rows={7} value={texto} onChange={(e) => setTexto(e.target.value)}
                style={{ width: "100%", fontSize: 13 }}
                placeholder={t("calidad.evaluar_placeholder")} />
      <div className="toolbar" style={{ marginTop: 8 }}>
        <button className="btn" disabled={cargando || texto.trim().length < 15} onClick={evaluar}>
          {cargando ? t("calidad.evaluando") : t("calidad.evaluar_boton")}
        </button>
        {error && <span style={{ color: "var(--red)", fontSize: 13 }}>{error}</span>}
      </div>

      {res && (
        <div style={{ marginTop: 14 }}>
          <div className="toolbar" style={{ gap: 16, alignItems: "baseline" }}>
            <span style={{ fontSize: 30, fontWeight: 800, color: color({ cumplido: res.puntaje_total >= 80, parcial: res.puntaje_total >= 60 }) }}>
              {res.puntaje_total}<span style={{ fontSize: 16 }}>/100</span></span>
            <span style={{ fontSize: 15, fontWeight: 700 }}>{res.categoria}</span>
            <span style={{ color: "var(--muted)", fontSize: 12 }}>
              {t("calidad.ref_humano")}: {res.referencia_humano} · {res.modo === "ia" ? "IA" : t("calidad.modo_local")}</span>
          </div>
          <div className="tablewrap" style={{ marginTop: 10 }}>
            <table style={{ minWidth: 0 }}>
              <thead><tr><th>{t("calidad.criterio")}</th><th>{t("calidad.puntaje")}</th><th></th></tr></thead>
              <tbody>
                {res.criterios.map((c) => (
                  <tr key={c.id} className="norow">
                    <td>{c.nombre}{c.critico && <span style={{ color: "var(--amber)", fontSize: 10 }}> ★</span>}</td>
                    <td className="tnum">{c.puntaje}/{c.max}</td>
                    <td style={{ width: 120 }}>
                      <div style={{ height: 7, borderRadius: 4, background: "rgba(255,255,255,.08)" }}>
                        <div style={{ height: "100%", borderRadius: 4, width: `${(c.puntaje / c.max) * 100}%`, background: color(c) }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {res.oportunidades.length > 0 && (
            <p style={{ fontSize: 13, marginTop: 10 }}>
              <b>{t("calidad.oportunidades")}:</b> {res.oportunidades.join(" · ")}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function Calidad() {
  return (
    <>
      <h1 className="page-title">{t("calidad.titulo")}</h1>
      <p className="page-sub">{t("calidad.subtitulo")}</p>
      <Comparativa />
      <Evaluador />
    </>
  );
}
