import React, { useEffect, useState } from "react";
import { api, fmtUYU } from "../api.js";
import { t } from "../i18n/index.js";

export default function Agenda() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/agenda").then(setDatos).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="page-title">{t("agenda.titulo")}</h1>
      <p className="page-sub" dangerouslySetInnerHTML={{ __html: t("agenda.subtitulo") }} />
      {error && <div className="empty">{error}</div>}
      {datos && datos.total === 0 && (
        <div className="empty">{t("agenda.vacio_sin_pendientes")}</div>
      )}
      {datos && datos.total > 0 && (
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
      )}
    </>
  );
}
