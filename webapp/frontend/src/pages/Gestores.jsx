import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Gestores() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/gestores/resumen").then(setDatos).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="page-title">Gestores &amp; evolución</h1>
      <p className="page-sub">Ranking por calidad de gestión y conversión (datos del registro
        de gestiones — en la demo son sintéticos, con tu operación real pasan a ser evidencia).</p>
      {error && <div className="empty">{error}</div>}
      {datos && !datos.ranking.length && (
        <div className="empty">Todavía no hay gestiones registradas.</div>
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
