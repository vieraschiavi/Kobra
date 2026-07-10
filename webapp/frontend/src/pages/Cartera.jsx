import React, { useEffect, useState } from "react";
import { api, fmtPct, fmtUYU, getPais, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

const TRAMOS = ["1-30", "31-60", "61-90", "91-180", "180+"];
// La API (kobra/analitica.py) siempre devuelve estos valores en español —
// son datos, no texto de UI — así que las claves quedan en español; solo
// la etiqueta mostrada se traduce (ver tProp / CLAVE_SEGMENTO abajo).
const SEGMENTOS = ["Corporativo", "Pyme", "Retail"];
const CLAVE_SEGMENTO = {
  "Corporativo": "cartera.filtro.segmento_corporativo",
  "Pyme": "cartera.filtro.segmento_pyme",
  "Retail": "cartera.filtro.segmento_retail",
};
const PROPENSIONES = ["Alta", "Media", "Baja"];
const CLAVE_PROPENSION = {
  "Alta": "common.propension.alta", "Media": "common.propension.media", "Baja": "common.propension.baja",
};
const tProp = (p) => t(CLAVE_PROPENSION[p] || p);

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

export default function Cartera() {
  const [datos, setDatos] = useState(null);
  const [pagina, setPagina] = useState(1);
  const [filtros, setFiltros] = useState({ segmento: "", tramo: "", propension: "", busqueda: "" });
  const [sel, setSel] = useState(null);
  const [error, setError] = useState("");

  const qs = () => {
    const p = new URLSearchParams();
    Object.entries(filtros).forEach(([k, v]) => v && p.set(k, v));
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

  return (
    <>
      <h1 className="page-title">{t("cartera.titulo")}</h1>
      <p className="page-sub">{t("cartera.subtitulo")}</p>

      <div className="toolbar">
        <input type="text" placeholder={t("cartera.toolbar.buscar_placeholder")} value={filtros.busqueda}
               onChange={setF("busqueda")} style={{ width: 150 }} />
        <select value={filtros.segmento} onChange={setF("segmento")}>
          <option value="">{t("cartera.toolbar.segmento_todos")}</option>
          {SEGMENTOS.map((s) => <option key={s} value={s}>{t(CLAVE_SEGMENTO[s])}</option>)}
        </select>
        <select value={filtros.tramo} onChange={setF("tramo")}>
          <option value="">{t("cartera.toolbar.tramo_todos")}</option>
          {TRAMOS.map((tr) => <option key={tr}>{tr}</option>)}
        </select>
        <select value={filtros.propension} onChange={setF("propension")}>
          <option value="">{t("cartera.toolbar.propension_todas")}</option>
          {PROPENSIONES.map((p) => <option key={p} value={p}>{tProp(p)}</option>)}
        </select>
        <button className="btn ghost" onClick={exportar}>{t("cartera.toolbar.exportar_csv")}</button>
      </div>

      {error && <div className="empty">{error}</div>}
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
