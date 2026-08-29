// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { api, descargar, fmtUYU, getPais } from "../api.js";
import { t } from "../i18n/index.js";

const TAMANO = 100;

// Plan de contacto de hoy: el canal lo elige la contactabilidad real de cada
// deudor (dónde se lo contactó o cerró en los últimos 90 días) y, si todavía
// no hay historial, la regla de negocio. El chip de cada fila dice cuál de
// las dos decidió — automático con historial, a criterio del operador sin él.
function PlanContacto() {
  const [d, setD] = useState(null);
  useEffect(() => {
    api("/api/campana/plan?limite=12").then(setD).catch(() => setD({ total: 0, contactos: [] }));
  }, []);
  if (!d || !d.total) return null;
  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("agenda.plan.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>
        {t("agenda.plan.sub", { total: d.total, historial: d.con_historial })}
      </p>
      <div className="tablewrap">
        <table>
          <thead><tr>
            <th>{t("agenda.tabla.col_id_deudor")}</th>
            <th>{t("agenda.plan.col_canal")}</th>
            <th>{t("agenda.plan.col_origen")}</th>
            <th>{t("agenda.plan.col_hora")}</th>
            <th>{t("agenda.plan.col_motivo")}</th>
            <th>{t("agenda.plan.col_monto")}</th>
          </tr></thead>
          <tbody>
            {d.contactos.map((p, i) => (
              <tr key={i} className="norow">
                <td>{p.id_deudor}</td>
                <td>{p.canal}</td>
                <td>
                  <span className={"pill " + (p.canal_origen === "historial" ? "alta" : "media")}>
                    {p.canal_origen === "historial"
                      ? t("agenda.plan.origen_historial")
                      : t("agenda.plan.origen_regla")}
                  </span>
                </td>
                <td className="tnum">{p.hora_preferida != null ? `${p.hora_preferida}:00` : "—"}</td>
                <td>{p.motivo}</td>
                <td className="tnum">{p.monto ? fmtUYU(p.monto) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Agenda() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  const [pagina, setPagina] = useState(1);

  useEffect(() => {
    setError("");
    api(`/api/agenda?pagina=${pagina}&tamano=${TAMANO}`)
      .then(setDatos)
      .catch((e) => setError(e.message));
  }, [pagina]);

  // El Excel trae TODAS las promesas vencidas, no la página que se está
  // viendo: lo que no entra en pantalla tiene que poder salir igual.
  async function exportar() {
    try {
      await descargar("/api/agenda/export.xlsx",
                      "MVKobraAI_Promesas_Vencidas.xlsx");
    } catch (e) {
      setError(e.message);
    }
  }

  const totalPaginas = datos ? (datos.paginas || 1) : 1;
  const locale = getPais().locale;

  return (
    <>
      <h1 className="page-title">{t("agenda.titulo")}</h1>
      {/* HTML propio y estatico: el texto sale del diccionario i18n del
          repo (src/i18n), no de la API ni del usuario. Lleva <b> y <br> a
          proposito. Cualquier dato dinamico va por {…}, nunca por aca. */}
      <p className="page-sub" dangerouslySetInnerHTML={{ __html: t("agenda.subtitulo") }} />
      <PlanContacto />
      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("agenda.cargando")}</div>}
      {datos && datos.total === 0 && (
        <div className="empty">{t("agenda.vacio_sin_pendientes")}</div>
      )}
      {datos && datos.total > 0 && (
        <>
          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <span style={{ color: "var(--muted)", fontSize: 12.5 }}>
              {datos.total.toLocaleString(locale)} {t("agenda.promesas_vencidas")}
            </span>
            <button className="btn ghost" onClick={exportar}>
              ⬇ {t("agenda.exportar_excel")}
            </button>
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>{t("agenda.tabla.col_id_deudor")}</th><th>{t("agenda.tabla.col_resultado")}</th>
                <th>{t("agenda.tabla.col_comprometido")}</th>
                <th>{t("agenda.tabla.col_dias_vencida")}</th><th>{t("agenda.tabla.col_monto_acordado")}</th>
                <th>{t("agenda.tabla.col_canal")}</th><th>{t("agenda.tabla.col_gestor")}</th>
              </tr></thead>
              <tbody>
                {datos.vencidas.map((v, i) => (
                  <tr key={i} className="norow">
                    <td>{v.id_deudor}</td>
                    <td>{v.resultado}</td>
                    <td>{v.fecha_compromiso}</td>
                    <td className="tnum">{v.dias_vencida}</td>
                    <td className="tnum">{v.monto_acordado ? fmtUYU(v.monto_acordado) : "—"}</td>
                    <td>{v.canal}</td>
                    <td>{v.gestor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <button className="btn ghost" disabled={pagina <= 1}
                    onClick={() => setPagina(pagina - 1)}>←</button>
            <span className="tnum">
              {t("cartera.pager.pagina_de", { pagina, total: totalPaginas })}
              {" "}{datos.total.toLocaleString(locale)} {t("agenda.promesas_vencidas")}
            </span>
            <button className="btn ghost" disabled={pagina >= totalPaginas}
                    onClick={() => setPagina(pagina + 1)}>→</button>
          </div>
        </>
      )}
    </>
  );
}
