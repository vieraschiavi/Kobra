// © 2026 Martín Viera. Todos los derechos reservados.
import React, { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, avisarPlan, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

const COL_IA = "#00c896";
const COL_HUM = "#2f74c0";
const colorTipo = (tipo) => (tipo === "IA" ? COL_IA : COL_HUM);
const money = (n) => "$U " + Math.round(n || 0).toLocaleString("es-UY");

// ── Panel: cómo mejoraría la cobranza mejorando la calidad ───────────────────
function PanelMejora({ m }) {
  if (!m) return null;
  const cards = [
    { l: t("calidad.mejora_calidad"), v: `+${m.brecha_calidad}`, sub: `${m.calidad_ia} vs ${m.calidad_humano}`, col: COL_IA },
    { l: t("calidad.mejora_conversion"), v: `+${m.brecha_conversion}%`, sub: `${m.conversion_ia}% vs ${m.conversion_humano}%`, col: "#f2b441" },
    { l: t("calidad.mejora_recupero_prom"), v: money(m.recupero_prom_ia), sub: `vs ${money(m.recupero_prom_humano)}`, col: COL_HUM },
    { l: t("calidad.mejora_recupero_adicional"), v: money(m.recupero_adicional_estimado), sub: `${m.gestiones_humanas.toLocaleString("es-UY")} ${t("calidad.gestiones")}`, col: "#e0567a" },
  ];
  return (
    <div className="card" style={{ marginTop: 16, borderTop: `3px solid ${COL_IA}` }}>
      <h3 style={{ marginTop: 0 }}>{t("calidad.mejora_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.mejora_sub")}</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
        {cards.map((c, i) => (
          <div key={i} className="card kpi" style={{ margin: 0, borderTop: `3px solid ${c.col}` }}>
            <div className="label">{c.l}</div>
            <div className="value" style={{ color: c.col, fontSize: 24 }}>{c.v}</div>
            <div className="delta">{c.sub}</div>
          </div>
        ))}
      </div>
      <p style={{ color: "var(--muted)", fontSize: 11.5, marginTop: 10, marginBottom: 0 }}>{t("calidad.mejora_nota")}</p>
    </div>
  );
}

// ── Panel: perfil por criterio (ítem de negociación) IA vs Humano ────────────
function PanelPerfil({ perfil }) {
  if (!perfil || !perfil.items || !perfil.items.length) return null;
  const data = perfil.items.map((x) => ({ criterio: x.criterio, IA: x.ia, Humano: x.humano }));
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>{t("calidad.perfil_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.perfil_sub")}</p>
      <ResponsiveContainer width="100%" height={Math.max(320, data.length * 26)}>
        <BarChart data={data} layout="vertical" margin={{ left: 40, right: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
          <XAxis type="number" domain={[0, 100]} tick={{ fill: "#93a5c0", fontSize: 11 }} />
          <YAxis type="category" dataKey="criterio" width={150} tick={{ fill: "#93a5c0", fontSize: 10.5 }} />
          <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #2f74c0" }} formatter={(v) => `${v}%`} />
          <Legend />
          <Bar dataKey="IA" fill={COL_IA} radius={[0, 3, 3, 0]} />
          <Bar dataKey="Humano" fill={COL_HUM} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12, marginTop: 8 }}>
        <div>
          <b style={{ color: COL_IA, fontSize: 13 }}>✔ {t("calidad.fortalezas_ia")}</b>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
            {perfil.fortalezas_ia.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
        <div>
          <b style={{ color: "#f2b441", fontSize: 13 }}>▲ {t("calidad.oportunidades_humano")}</b>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
            {perfil.oportunidades_humano.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      </div>
    </div>
  );
}

// ── Panel: evolución de la calidad en el tiempo ──────────────────────────────
function PanelEvolucion({ evo }) {
  if (!evo || !evo.meses || !evo.meses.length) return null;
  const data = evo.meses.map((m, i) => {
    const fila = { mes: m };
    evo.series.forEach((s) => { fila[s.tipo] = s.valores[i]; });
    return fila;
  });
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>{t("calidad.evolucion_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.evolucion_sub")}</p>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
          <XAxis dataKey="mes" tick={{ fill: "#93a5c0", fontSize: 11 }} />
          <YAxis domain={[40, 100]} tick={{ fill: "#93a5c0", fontSize: 11 }} />
          <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #2f74c0" }} />
          <Legend />
          {evo.series.map((s) => (
            <Line key={s.tipo} type="monotone" dataKey={s.tipo}
                  name={s.tipo === "IA" ? t("calidad.gestor_ia") : t("calidad.gestor_humano")}
                  stroke={colorTipo(s.tipo)} strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Tablero comparativo (con filtros canal/mes/gestor) ───────────────────────
function Comparativa() {
  const [data, setData] = useState(null);
  const [canal, setCanal] = useState("");
  const [mes, setMes] = useState("");
  const [gestor, setGestor] = useState("");
  const [error, setError] = useState("");

  const cargar = () => {
    const q = new URLSearchParams();
    if (canal) q.set("canal", canal);
    if (mes) q.set("mes", mes);
    if (gestor) q.set("gestor", gestor);
    const qs = q.toString();
    api("/api/calidad/comparativa" + (qs ? `?${qs}` : ""))
      .then(setData).catch((e) => setError(e.message));
  };
  useEffect(() => { cargar(); /* eslint-disable-next-line */ }, [canal, mes, gestor]);

  if (error) return <div className="empty">{error}</div>;
  if (!data) return <div className="empty">{t("calidad.cargando")}</div>;

  const chartData = data.por_tipo.map((x) => ({
    tipo: x.tipo === "IA" ? t("calidad.gestor_ia") : t("calidad.gestor_humano"),
    tipoRaw: x.tipo, Calidad: x.calidad_prom, Conversión: x.tasa_conversion,
  }));

  return (
    <>
      <div className="toolbar" style={{ gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.filtro_canal")}:</span>
        <select value={canal} onChange={(e) => setCanal(e.target.value)}>
          <option value="">{t("calidad.todos_canales")}</option>
          {(data.canales || []).map((cn) => <option key={cn} value={cn}>{cn}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.filtro_mes")}:</span>
        <select value={mes} onChange={(e) => setMes(e.target.value)}>
          <option value="">{t("calidad.todos_meses")}</option>
          {(data.meses || []).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.filtro_gestor")}:</span>
        <select value={gestor} onChange={(e) => setGestor(e.target.value)}>
          <option value="">{t("calidad.todos_gestores")}</option>
          {(data.gestores || []).map((g) => <option key={g} value={g}>{g}</option>)}
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

      {/* Cómo mejoraría la cobranza */}
      <PanelMejora m={data.mejora} />

      {/* Gráfico comparativo calidad/conversión */}
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

      {/* Perfil por ítem de negociación */}
      <PanelPerfil perfil={data.perfil} />

      {/* Evolución en el tiempo */}
      <PanelEvolucion evo={data.evolucion} />

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

// ── Detalle de una evaluación (barras por criterio) ──────────────────────────
function DetalleEvaluacion({ res }) {
  const color = (c) => c.cumplido ? "var(--green-deep)" : c.parcial ? "var(--amber)" : "var(--red)";
  return (
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
  );
}

// ── Evaluador por texto ──────────────────────────────────────────────────────
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

  return (
    <div className="card" style={{ marginTop: 16, maxWidth: 900 }}>
      <h3 style={{ marginTop: 0 }}>{t("calidad.evaluar_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.evaluar_sub")}</p>
      <div className="toolbar" style={{ gap: 8 }}>
        <select value={canal} onChange={(e) => setCanal(e.target.value)}>
          <option value="Llamada">{t("calidad.canal_llamada")}</option>
          <option value="WhatsApp">WhatsApp</option>
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
      {res && <DetalleEvaluacion res={res} />}
    </div>
  );
}

// ── Fuentes de grabaciones (manual + Avaya) ──────────────────────────────────
function Fuentes() {
  const [f, setF] = useState(null);
  useEffect(() => { api("/api/calidad/fuentes").then(setF).catch(() => {}); }, []);
  if (!f) return null;
  const Chip = ({ ok }) => (
    <span className="pill" style={{ background: (ok ? COL_IA : "#f2b441") + "22", color: ok ? COL_IA : "#f2b441" }}>
      {ok ? "● " + t("calidad.estado_activo") : "○ " + t("calidad.estado_sin_config")}</span>
  );
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>{t("calidad.fuentes_titulo")}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12 }}>
        <div className="card" style={{ margin: 0 }}>
          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <b>{t("calidad.fuente_manual")}</b><Chip ok={f.manual.activo} />
          </div>
          <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 0 }}>
            WAV · MP3 · {f.manual.transcripcion === "whisper" ? "Whisper" : "Whisper (OPENAI_API_KEY)"}
          </p>
        </div>
        <div className="card" style={{ margin: 0 }}>
          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <b>{t("calidad.fuente_avaya")}</b><Chip ok={f.avaya.activo} />
          </div>
          <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 0 }}>
            {f.avaya.activo ? t("calidad.avaya_conectado") : t("calidad.avaya_sin_config")}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Cargar y evaluar audio (MP3/WAV) ─────────────────────────────────────────
function EvaluadorAudio({ onGuardado }) {
  const [archivo, setArchivo] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [canal, setCanal] = useState("Llamada");
  const [gestor, setGestor] = useState("");
  const [fecha, setFecha] = useState("");
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  const elegir = (file) => {
    setArchivo(file || null); setRes(null); setError("");
    setPreviewUrl(file ? URL.createObjectURL(file) : null);
  };

  const procesar = async () => {
    if (!archivo) return;
    setCargando(true); setError(""); setRes(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const ses = getSesion();
      const q = new URLSearchParams({ canal });
      if (gestor.trim()) q.set("gestor", gestor.trim());
      if (fecha) q.set("fecha", fecha);
      const r = await fetch("/api/calidad/evaluar-audio?" + q.toString(), {
        method: "POST",
        headers: ses ? { Authorization: `Bearer ${ses.token}` } : {},
        body: fd,
      });
      const d = await r.json().catch(() => ({}));
      // Antes del throw: si el cupo se agotó (402), la MISMA respuesta trae
      // el plan actualizado — es el momento en que el chip más lo necesita.
      avisarPlan(d);
      if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
      setRes(d);
      if (d.guardado && onGuardado) onGuardado();
    } catch (e) { setError(e.message.replace(/^\d+:\s*/, "")); }
    finally { setCargando(false); }
  };

  return (
    <>
      <Fuentes />
      <div className="card" style={{ marginTop: 16, maxWidth: 900 }}>
        <h3 style={{ marginTop: 0 }}>{t("calidad.audio_titulo")}</h3>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("calidad.audio_sub")}</p>
        <div className="toolbar" style={{ gap: 8, flexWrap: "wrap" }}>
          <select value={canal} onChange={(e) => setCanal(e.target.value)}>
            <option value="Llamada">{t("calidad.canal_llamada")}</option>
            <option value="WhatsApp">WhatsApp</option>
          </select>
          <input type="text" placeholder={t("calidad.audio_gestor_ph")} value={gestor}
                 onChange={(e) => setGestor(e.target.value)} style={{ width: 200 }} />
          <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          <input type="file" accept=".wav,.mp3,audio/wav,audio/mpeg"
                 onChange={(e) => elegir(e.target.files[0] || null)} />
          <button className="btn" disabled={!archivo || cargando} onClick={procesar}>
            {cargando ? t("calidad.audio_procesando") : t("calidad.audio_boton")}
          </button>
        </div>
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>{t("calidad.audio_guardar_hint")}</p>
        {previewUrl && (
          <div style={{ marginTop: 10 }}>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 4 }}>{t("calidad.audio_escuchar")}:</div>
            <audio controls src={previewUrl} style={{ width: "100%" }} />
          </div>
        )}
        {error && <p style={{ color: "var(--red)", fontSize: 13, marginTop: 8 }}>{error}</p>}

        {res && res.guardado && (
          <p style={{ color: COL_IA, fontSize: 13, marginTop: 10 }}>
            {t("calidad.audio_guardado")} <b>{res.guardado.gestor}</b> ({res.guardado.fecha})</p>
        )}
        {res && res.evaluacion && <DetalleEvaluacion res={res.evaluacion} />}
        {res && !res.evaluacion && (
          <p style={{ color: "var(--amber)", fontSize: 13, marginTop: 12 }}>{res.aviso || t("calidad.audio_sin_texto")}</p>
        )}
        {res && res.transcripcion && (
          <div style={{ marginTop: 12 }}>
            <b style={{ fontSize: 13 }}>{t("calidad.audio_transcripcion")}:</b>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12.5, background: "rgba(255,255,255,.04)",
                          padding: 10, borderRadius: 6, marginTop: 6, maxHeight: 260, overflow: "auto" }}>
              {res.transcripcion}</pre>
          </div>
        )}
      </div>
    </>
  );
}

// ── Fichas de gestores (audios evaluados y acumulados) ───────────────────────
function Fichas({ recargar }) {
  const [data, setData] = useState(null);
  const [gestor, setGestor] = useState("");
  const [mes, setMes] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const q = new URLSearchParams();
    if (gestor) q.set("gestor", gestor);
    if (mes) q.set("mes", mes);
    api("/api/calidad/evaluaciones" + (q.toString() ? `?${q}` : ""))
      .then(setData).catch((e) => setError(e.message));
  }, [gestor, mes, recargar]);

  if (error) return <div className="empty">{error}</div>;
  if (!data) return <div className="empty">{t("calidad.cargando")}</div>;
  if (data.total === 0 && !gestor && !mes)
    return <div className="empty">{t("calidad.fichas_vacio")}</div>;

  const evoData = data.evolucion.meses.map((m, i) => {
    const fila = { mes: m };
    data.evolucion.series.forEach((s) => { fila[s.gestor] = s.valores[i]; });
    return fila;
  });
  const palette = ["#00c896", "#2f74c0", "#f2b441", "#e0567a", "#9b6cf0", "#3cc7c0"];

  return (
    <>
      <div className="toolbar" style={{ gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <select value={gestor} onChange={(e) => setGestor(e.target.value)}>
          <option value="">{t("calidad.fichas_todos_gestores")}</option>
          {(data.gestores || []).map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
        <select value={mes} onChange={(e) => setMes(e.target.value)}>
          <option value="">{t("calidad.fichas_todos_meses")}</option>
          {(data.meses || []).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <span style={{ color: "var(--muted)", fontSize: 12.5 }}>
          {data.total} {t("calidad.fichas_audios")}</span>
      </div>

      {/* KPIs por gestor */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 12 }}>
        {data.por_gestor.map((g, i) => (
          <div key={g.gestor} className="card kpi" style={{ margin: 0, borderTop: `3px solid ${palette[i % palette.length]}` }}>
            <div className="label">{g.gestor} · {g.audios} {t("calidad.fichas_audios")}</div>
            <div className="value" style={{ color: palette[i % palette.length] }}>
              {g.calidad_prom}<span style={{ fontSize: 13 }}>/100</span></div>
            <div className="delta">{t("calidad.fichas_ultima")}: {g.ultima}</div>
          </div>
        ))}
      </div>

      {/* Evolución de la nota por gestor */}
      {evoData.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>{t("calidad.fichas_evolucion")}</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={evoData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
              <XAxis dataKey="mes" tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #2f74c0" }} />
              <Legend />
              {data.evolucion.series.map((s, i) => (
                <Line key={s.gestor} type="monotone" dataKey={s.gestor} stroke={palette[i % palette.length]}
                      strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Promedio por criterio */}
      {data.criterios_promedio.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>{t("calidad.fichas_criterios")}</h3>
          <ResponsiveContainer width="100%" height={Math.max(300, data.criterios_promedio.length * 24)}>
            <BarChart data={data.criterios_promedio.map((c) => ({ criterio: c.criterio, "%": c.pct }))}
                      layout="vertical" margin={{ left: 40, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <YAxis type="category" dataKey="criterio" width={150} tick={{ fill: "#93a5c0", fontSize: 10.5 }} />
              <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #2f74c0" }} formatter={(v) => `${v}%`} />
              <Bar dataKey="%" fill={COL_IA} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Detalle */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("calidad.fichas_detalle")}</h3>
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>{t("calidad.fichas_col_fecha")}</th><th>{t("calidad.fichas_col_gestor")}</th>
              <th>{t("calidad.fichas_col_canal")}</th><th>{t("calidad.fichas_col_nota")}</th>
              <th>{t("calidad.fichas_col_cat")}</th><th>{t("calidad.fichas_col_archivo")}</th>
            </tr></thead>
            <tbody>
              {data.evaluaciones.map((e) => (
                <tr key={e.id} className="norow">
                  <td>{e.fecha}</td><td>{e.gestor}</td><td>{e.canal}</td>
                  <td className="tnum"><b>{e.puntaje_total}</b></td>
                  <td>{e.categoria}</td><td style={{ color: "var(--muted)", fontSize: 12 }}>{e.archivo}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ── Panel de calidad: gestor · mes · año · aspecto vs. la media ──────────────
// Lo que hace útil al tablero no es la nota sino la COMPARACIÓN: saber que un
// gestor tiene 58 no dice qué entrenarle; saber que está 40 puntos por debajo
// de la media del equipo en "Negociación deuda total", sí.
function BarraComparada({ c }) {
  const brecha = c.brecha;
  const color = brecha == null ? "var(--muted)"
              : brecha >= 5 ? "var(--green)"
              : brecha <= -5 ? "var(--red)" : "var(--yellow)";
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    fontSize: 12.5, marginBottom: 3 }}>
        <span>{c.criterio}{c.critico && <span title={t("calidad.panel.critico")}
              style={{ color: "var(--red)", marginLeft: 4 }}>*</span>}</span>
        <span className="tnum" style={{ color, fontWeight: 700 }}>
          {c.pct == null ? "—" : `${c.pct}%`}
          {brecha != null && ` (${brecha > 0 ? "+" : ""}${brecha})`}
        </span>
      </div>
      <div style={{ position: "relative", height: 8, borderRadius: 4,
                    background: "rgba(255,255,255,.07)" }}>
        <div style={{ width: `${Math.max(0, Math.min(100, c.pct || 0))}%`,
                      height: "100%", borderRadius: 4, background: color }} />
        {/* Marca de la media del equipo: la referencia contra la que se lee. */}
        {c.media_equipo_pct != null && (
          <div title={t("calidad.panel.media_equipo")}
               style={{ position: "absolute", top: -2, bottom: -2,
                        left: `${Math.min(100, c.media_equipo_pct)}%`,
                        width: 2, background: "var(--txt)", opacity: .65 }} />
        )}
      </div>
    </div>
  );
}

function PanelCalidad() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [gestor, setGestor] = useState("");
  const [anio, setAnio] = useState("");
  const [mes, setMes] = useState("");

  const qs = () => {
    const p = new URLSearchParams();
    if (gestor) p.set("gestor", gestor);
    if (anio) p.set("anio", anio);
    if (mes) p.set("mes", mes);
    return p.toString();
  };

  useEffect(() => {
    setError("");
    api(`/api/calidad/panel?${qs()}`).then(setD).catch((e) => setError(e.message));
  }, [gestor, anio, mes]);

  async function exportar() {
    const ses = getSesion();
    const r = await fetch(`/api/calidad/export.xlsx?${qs()}`,
                          { headers: { Authorization: `Bearer ${ses.token}` } });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "MVKobraAI_Calidad.xlsx";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  if (error) return <div className="empty">{error}</div>;
  if (!d) return <div className="empty">{t("calidad.cargando")}</div>;

  const k = d.kpis || {};
  const sinDatos = !d.total;

  return (
    <>
      <div className="toolbar" style={{ flexWrap: "wrap", gap: 8 }}>
        <select value={gestor} onChange={(e) => setGestor(e.target.value)}>
          <option value="">{t("calidad.panel.todos_gestores")}</option>
          {(d.gestores || []).map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
        <select value={anio} onChange={(e) => { setAnio(e.target.value); setMes(""); }}>
          <option value="">{t("calidad.panel.todos_anios")}</option>
          {(d.anios || []).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={mes} onChange={(e) => setMes(e.target.value)}>
          <option value="">{t("calidad.panel.todos_meses")}</option>
          {(d.meses || []).filter((m) => !anio || m.startsWith(anio))
            .map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <button className="btn ghost" onClick={exportar}>⬇ {t("calidad.panel.exportar")}</button>
        {d.origen && (
          <span className={`badge-origen ${d.origen.es_real ? "real" : "demo"}`}
                title={d.origen.detalle}>● {d.origen.etiqueta}</span>
        )}
      </div>

      {sinDatos ? (
        <div className="empty">{t("calidad.panel.vacio")}</div>
      ) : (
        <>
          <div className="kpis">
            <div className="kpi"><div className="v">{k.audios}</div>
              <div className="l">{t("calidad.panel.kpi_audios")}</div></div>
            <div className="kpi"><div className="v">{k.calidad_prom ?? "—"}</div>
              <div className="l">{t("calidad.panel.kpi_calidad")}</div></div>
            <div className="kpi"><div className="v">{k.media_equipo ?? "—"}</div>
              <div className="l">{t("calidad.panel.kpi_media")}</div></div>
            <div className="kpi">
              <div className="v" style={{ color: (k.vs_media ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                {k.vs_media == null ? "—" : `${k.vs_media > 0 ? "+" : ""}${k.vs_media}`}
              </div>
              <div className="l">{t("calidad.panel.kpi_vs_media")}</div></div>
            <div className="kpi"><div className="v">{k.gestores_evaluados}</div>
              <div className="l">{t("calidad.panel.kpi_gestores")}</div></div>
            <div className="kpi">
              <div className="v" style={{ color: k.criticos_bajos ? "var(--red)" : "var(--green)" }}>
                {k.criticos_bajos}</div>
              <div className="l">{t("calidad.panel.kpi_criticos")}</div></div>
          </div>

          <div className="grid2">
            <div className="card">
              <h3 style={{ marginTop: 0 }}>{t("calidad.panel.por_aspecto")}</h3>
              <p style={{ color: "var(--muted)", fontSize: 12, marginTop: -4 }}>
                {t("calidad.panel.por_aspecto_sub")}
              </p>
              {(d.por_criterio || []).map((c) => <BarraComparada key={c.id} c={c} />)}
            </div>
            <div>
              <div className="card">
                <h3 style={{ marginTop: 0 }}>{t("calidad.panel.oportunidades")}</h3>
                {(d.oportunidades || []).map((c) => (
                  <div key={c.id} style={{ fontSize: 13, marginBottom: 6 }}>
                    <b>{c.criterio}</b>{" "}
                    <span style={{ color: "var(--red)" }}>{c.brecha}</span>{" "}
                    <span style={{ color: "var(--muted)" }}>{t("calidad.panel.vs_media_txt")}</span>
                  </div>
                ))}
              </div>
              <div className="card" style={{ marginTop: 12 }}>
                <h3 style={{ marginTop: 0 }}>{t("calidad.panel.fortalezas")}</h3>
                {(d.fortalezas || []).map((c) => (
                  <div key={c.id} style={{ fontSize: 13, marginBottom: 6 }}>
                    <b>{c.criterio}</b>{" "}
                    <span style={{ color: "var(--green)" }}>+{c.brecha}</span>{" "}
                    <span style={{ color: "var(--muted)" }}>{t("calidad.panel.vs_media_txt")}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid2">
            <div className="card">
              <h3 style={{ marginTop: 0 }}>{t("calidad.panel.evolucion")}</h3>
              <div className="tablewrap"><table>
                <thead><tr><th>{t("calidad.panel.col_mes")}</th>
                  <th>{gestor || t("calidad.panel.col_foco")}</th>
                  <th>{t("calidad.panel.col_equipo")}</th></tr></thead>
                <tbody>{(d.evolucion || []).map((e) => (
                  <tr key={e.mes} className="norow"><td>{e.mes}</td>
                    <td className="tnum">{e.gestor ?? "—"}</td>
                    <td className="tnum">{e.equipo ?? "—"}</td></tr>
                ))}</tbody>
              </table></div>
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>{t("calidad.panel.ranking")}</h3>
              <div className="tablewrap"><table>
                <thead><tr><th>{t("calidad.panel.col_gestor")}</th>
                  <th>{t("calidad.panel.col_audios")}</th>
                  <th>{t("calidad.panel.col_calidad")}</th>
                  <th>{t("calidad.panel.col_vs")}</th></tr></thead>
                <tbody>{(d.ranking || []).map((r) => (
                  <tr key={r.gestor} className="norow"><td>{r.gestor}</td>
                    <td className="tnum">{r.audios}</td>
                    <td className="tnum">{r.calidad_prom}</td>
                    <td className="tnum" style={{ color: (r.vs_media ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                      {r.vs_media == null ? "—" : `${r.vs_media > 0 ? "+" : ""}${r.vs_media}`}</td></tr>
                ))}</tbody>
              </table></div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>{t("calidad.panel.distribucion")}</h3>
            <div className="tablewrap"><table>
              <thead><tr>{(d.distribucion || []).map((x) => <th key={x.tramo}>{x.tramo}</th>)}</tr></thead>
              <tbody><tr className="norow">
                {(d.distribucion || []).map((x) => <td key={x.tramo} className="tnum">{x.audios}</td>)}
              </tr></tbody>
            </table></div>
          </div>
        </>
      )}
    </>
  );
}

// ── Página con pestañas ──────────────────────────────────────────────────────
export default function Calidad() {
  const [tab, setTab] = useState("panel");
  const [recargarFichas, setRecargarFichas] = useState(0);
  const tabs = [
    { id: "panel", label: t("calidad.tab_panel") },
    { id: "dashboard", label: t("calidad.tab_dashboard") },
    { id: "audio", label: t("calidad.tab_audio") },
    { id: "fichas", label: t("calidad.tab_fichas") },
    { id: "evaluar", label: t("calidad.tab_evaluar") },
  ];
  return (
    <>
      <h1 className="page-title">{t("calidad.titulo")}</h1>
      <p className="page-sub">{t("calidad.subtitulo")}</p>
      <div className="toolbar" style={{ gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
        {tabs.map((x) => (
          <button key={x.id} className={"btn" + (tab === x.id ? "" : " ghost")}
                  onClick={() => setTab(x.id)}>{x.label}</button>
        ))}
      </div>
      {tab === "panel" && <PanelCalidad />}
      {tab === "dashboard" && <Comparativa />}
      {tab === "audio" && <EvaluadorAudio onGuardado={() => setRecargarFichas((n) => n + 1)} />}
      {tab === "fichas" && (
        <>
          <h2 style={{ margin: "6px 0 2px", fontSize: 18 }}>{t("calidad.fichas_titulo")}</h2>
          <p className="page-sub" style={{ marginTop: 0 }}>{t("calidad.fichas_sub")}</p>
          <Fichas recargar={recargarFichas} />
        </>
      )}
      {tab === "evaluar" && <Evaluador />}
    </>
  );
}
