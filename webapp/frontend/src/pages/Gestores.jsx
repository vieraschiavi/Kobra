import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { t } from "../i18n/index.js";

export default function Gestores() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/gestores/resumen").then(setDatos).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="page-title">{t("gestores.titulo")}</h1>
      <p className="page-sub">{t("gestores.subtitulo")}</p>
      {error && <div className="empty">{error}</div>}
      {datos && !datos.ranking.length && (
        <div className="empty">{t("gestores.vacio_sin_gestiones")}</div>
      )}
      {datos && datos.ranking.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead><tr>
              {Object.keys(datos.ranking[0]).map((k) => <th key={k}>{k.replace(/_/g, " ")}</th>)}
            </tr></thead>
            <tbody>
              {datos.ranking.map((r, i) => (
                <tr key={i} className="norow">
                  {Object.values(r).map((v, j) => (
                    <td key={j} className="tnum">
                      {typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : String(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
