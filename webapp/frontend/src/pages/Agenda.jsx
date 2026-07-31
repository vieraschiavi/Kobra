import React, { useEffect, useState } from "react";
import { api, fmtUYU, getSesion, getPais } from "../api.js";
import { t } from "../i18n/index.js";

const TAMANO = 100;

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
    const ses = getSesion();
    const r = await fetch("/api/agenda/export.xlsx",
                          { headers: { Authorization: `Bearer ${ses.token}` } });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "MVKobraAI_Promesas_Vencidas.xlsx";
    a.click();
    URL.revokeObjectURL(a.href);
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
