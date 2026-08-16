// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { api, fmtPct, fmtUYU, getPais, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

const CLAVE_PROPENSION = {
  "Alta": "common.propension.alta", "Media": "common.propension.media", "Baja": "common.propension.baja",
};
const tProp = (p) => t(CLAVE_PROPENSION[p] || p);
const MESES = ["", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];

function Drawer({ id, onClose }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api(`/api/deudor/${id}`).then(setD).catch((e) => setError(e.message));
  }, [id]);
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer">
        <button className="btn ghost close" onClick={onClose}>✕</button>
        <h2>{id}</h2>
        {error && <div className="empty">{error}</div>}
        {!d && !error && <div className="empty">{t("common.cargando")}</div>}
        {d && (
          <>
            <span className={"pill " + (d.segmento_propension || "").toLowerCase()}>
              {tProp(d.segmento_propension)} {t("cartera.drawer.propension_sufijo", { pct: fmtPct(d.probpago) })}
            </span>
            <div className="kv">
              <span className="k">{t("cartera.drawer.segmento")}</span><span>{d.segmento} · {d.producto}</span>
              <span className="k">{t("cartera.drawer.departamento")}</span><span>{d.departamento}</span>
              <span className="k">{t("cartera.drawer.mora")}</span><span>{t("cartera.drawer.mora_valor", { dias: d.dias_mora, tramo: d.tramo_mora })}</span>
              <span className="k">{t("cartera.drawer.deuda")}</span><span className="tnum">{fmtUYU(d.monto_deuda)}</span>
              <span className="k">{t("cartera.drawer.recupero_esperado")}</span><span className="tnum">{fmtUYU(d.valor_esperado_recupero)}</span>
              <span className="k">{t("cartera.drawer.estrategia")}</span><span>{d.estrategia}</span>
              <span className="k">{t("cartera.drawer.descuento_sugerido")}</span><span>{d.descuento_recomendado}</span>
              <span className="k">{t("cartera.drawer.canal_recomendado")}</span><span>{d.canal_recomendado}</span>
              <span className="k">{t("cartera.drawer.por_que_probpago")}</span><span>{d.motivo_probpago}</span>
            </div>
            {d.guion && (
              <div className="guion"><b>{t("cartera.drawer.guion_sugerido")}</b>{"\n"}{d.guion}</div>
            )}
          </>
        )}
      </aside>
    </>
  );
}

const VACIO = {
  segmento: "", tramo: "", propension: "", busqueda: "", producto: "",
  departamento: "", monto_min: "", monto_max: "", dias_min: "", dias_max: "",
  anio: "", mes: "",
};

export default function Cartera() {
  const [datos, setDatos] = useState(null);
  const [opciones, setOpciones] = useState(null);   // /api/cartera/filtros (del dataset)
  const [pagina, setPagina] = useState(1);
  const [filtros, setFiltros] = useState(VACIO);
  const [sel, setSel] = useState(null);
  const [error, setError] = useState("");

  // Opciones de filtro REALES del dataset activo (real o demo).
  useEffect(() => { api("/api/cartera/filtros").then(setOpciones).catch(() => {}); }, []);

  const qs = () => {
    const p = new URLSearchParams();
    Object.entries(filtros).forEach(([k, v]) => (v !== "" && v != null) && p.set(k, v));
    return p;
  };

  useEffect(() => {
    const p = qs();
    p.set("pagina", pagina); p.set("tamano", 25);
    api(`/api/cartera?${p}`).then(setDatos).catch((e) => setError(e.message));
  }, [pagina, filtros]);

  async function exportar() {
    const ses = getSesion();
    const r = await fetch(`/api/cartera/export.csv?${qs()}`,
                          { headers: { Authorization: `Bearer ${ses.token}` } });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "cartera_priorizada.csv";
    a.click();
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.total / datos.tamano)) : 1;
  const setF = (k) => (e) => { setPagina(1); setFiltros({ ...filtros, [k]: e.target.value }); };
  const o = opciones || {};
  const hayFiltro = Object.values(filtros).some((v) => v !== "");
  const dm = o.dias_mora || null;

  return (
    <>
      <h1 className="page-title">{t("cartera.titulo")}
        {o.modo && <span className="pill" style={{ marginLeft: 10, fontSize: 12,
          background: (o.modo === "real" ? "#00c89622" : "#f2b44122"),
          color: o.modo === "real" ? "#00c896" : "#f2b441" }}>
          {o.modo === "real" ? "● " + t("cartera.toolbar.modo_real") : "○ " + t("cartera.toolbar.modo_demo")}</span>}
      </h1>
      <p className="page-sub">{t("cartera.subtitulo")}</p>

      <div className="toolbar" style={{ flexWrap: "wrap", gap: 8 }}>
        <input type="text" placeholder={t("cartera.toolbar.buscar_placeholder")} value={filtros.busqueda}
               onChange={setF("busqueda")} style={{ width: 130 }} />
        <select value={filtros.segmento} onChange={setF("segmento")}>
          <option value="">{t("cartera.toolbar.segmento_todos")}</option>
          {(o.segmentos || []).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {(o.productos || []).length > 0 && (
          <select value={filtros.producto} onChange={setF("producto")}>
            <option value="">{t("cartera.toolbar.producto_todos")}</option>
            {o.productos.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>)}
        {(o.departamentos || []).length > 0 && (
          <select value={filtros.departamento} onChange={setF("departamento")}>
            <option value="">{t("cartera.toolbar.depto_todos")}</option>
            {o.departamentos.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>)}
        <select value={filtros.tramo} onChange={setF("tramo")}>
          <option value="">{t("cartera.toolbar.tramo_todos")}</option>
          {(o.tramos || []).map((tr) => <option key={tr}>{tr}</option>)}
        </select>
        <select value={filtros.propension} onChange={setF("propension")}>
          <option value="">{t("cartera.toolbar.propension_todas")}</option>
          {(o.propensiones || []).map((p) => <option key={p} value={p}>{tProp(p)}</option>)}
        </select>
        {o.tiene_fecha && (o.anios || []).length > 0 && (
          <select value={filtros.anio} onChange={setF("anio")}>
            <option value="">{t("cartera.toolbar.anio_todos")}</option>
            {o.anios.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>)}
        {o.tiene_fecha && (
          <select value={filtros.mes} onChange={setF("mes")}>
            <option value="">{t("cartera.toolbar.mes_todos")}</option>
            {MESES.slice(1).map((m) => <option key={m} value={parseInt(m, 10)}>{m}</option>)}
          </select>)}
        <button className="btn ghost" onClick={exportar}>{t("cartera.toolbar.exportar_csv")}</button>
        {hayFiltro && <button className="btn ghost" onClick={() => { setPagina(1); setFiltros(VACIO); }}>
          {t("cartera.toolbar.limpiar")}</button>}
      </div>

      {/* Rangos: monto y slider de días de mora — límites tomados del dataset */}
      {o.monto && (
        <div className="toolbar" style={{ flexWrap: "wrap", gap: 14, marginTop: 4 }}>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>{t("cartera.toolbar.monto")}:</span>
          <input type="number" placeholder={String(o.monto.min)} value={filtros.monto_min}
                 onChange={setF("monto_min")} style={{ width: 110 }} />
          <span style={{ color: "var(--muted)", fontSize: 12 }}>{t("cartera.toolbar.hasta")}</span>
          <input type="number" placeholder={String(o.monto.max)} value={filtros.monto_max}
                 onChange={setF("monto_max")} style={{ width: 110 }} />
          {dm && (
            <>
              <span style={{ color: "var(--muted)", fontSize: 13, marginLeft: 10 }}>
                {t("cartera.toolbar.dias_mora")}: <b>{filtros.dias_min || dm.min}</b>–<b>{filtros.dias_max || dm.max}</b></span>
              <input type="range" min={dm.min} max={dm.max} value={filtros.dias_min || dm.min}
                     aria-label={t("cartera.toolbar.dias_min_aria")}
                     onChange={setF("dias_min")} style={{ width: 120 }} />
              <input type="range" min={dm.min} max={dm.max} value={filtros.dias_max || dm.max}
                     aria-label={t("cartera.toolbar.dias_max_aria")}
                     onChange={setF("dias_max")} style={{ width: 120 }} />
            </>)}
        </div>
      )}

      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("common.cargando")}</div>}
      {datos && datos.total === 0 && <div className="empty">{t("cartera.toolbar.sin_resultados")}</div>}
      {datos && (
        <>
          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>{t("cartera.tabla.col_numero")}</th><th>{t("cartera.tabla.col_id")}</th>
                <th>{t("cartera.tabla.col_segmento")}</th><th>{t("cartera.tabla.col_producto")}</th>
                <th>{t("cartera.tabla.col_depto")}</th>
                <th>{t("cartera.tabla.col_tramo")}</th><th>{t("cartera.tabla.col_monto")}</th>
                <th>{t("cartera.tabla.col_probpago")}</th><th>{t("cartera.tabla.col_prop")}</th>
                <th>{t("cartera.tabla.col_estrategia")}</th><th>{t("cartera.tabla.col_desc")}</th>
                <th>{t("cartera.tabla.col_canal")}</th>
              </tr></thead>
              <tbody>
                {datos.filas.map((f) => (
                  <tr key={f.id_deudor} onClick={() => setSel(f.id_deudor)}>
                    <td className="tnum">{f.prioridad}</td>
                    <td>{f.id_deudor}</td>
                    <td>{f.segmento}</td>
                    <td>{f.producto}</td>
                    <td>{f.departamento}</td>
                    <td>{f.tramo_mora}</td>
                    <td className="tnum">{fmtUYU(f.monto_deuda)}</td>
                    <td className="tnum">{fmtPct(f.probpago, 0)}</td>
                    <td><span className={"pill " + (f.segmento_propension || "").toLowerCase()}>
                      {tProp(f.segmento_propension)}</span></td>
                    <td>{f.estrategia}</td>
                    <td className="tnum">{Math.round((f.descuento_recomendado || 0) * 100)}%</td>
                    <td>{f.canal_recomendado}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <button className="btn ghost" disabled={pagina <= 1}
                    onClick={() => setPagina(pagina - 1)}>←</button>
            <span className="tnum">{t("cartera.pager.pagina_de", { pagina, total: totalPaginas })}
              {" "}{datos.total.toLocaleString(getPais().locale)} {t("cartera.pager.deudores_sufijo")}</span>
            <button className="btn ghost" disabled={pagina >= totalPaginas}
                    onClick={() => setPagina(pagina + 1)}>→</button>
          </div>
        </>
      )}
      {sel && <Drawer id={sel} onClose={() => setSel(null)} />}
    </>
  );
}
