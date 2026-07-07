import React, { useEffect, useState } from "react";
import { api, fmtUYU } from "../api.js";

export default function Agenda() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/agenda").then(setDatos).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <h1 className="page-title">Agenda de hoy</h1>
      <p className="page-sub">Promesas y arreglos de pago <b>vencidos sin pago registrado</b>
        — los casos que ya perdieron una fecha comprometida y conviene retomar primero.
        El contacto real sigue pasando por el chequeo de cumplimiento.</p>
      {error && <div className="empty">{error}</div>}
      {datos && datos.total === 0 && (
        <div className="empty">🎉 No hay promesas vencidas pendientes.</div>
      )}
      {datos && datos.total > 0 && (
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th>ID deudor</th><th>Resultado</th><th>Comprometido para</th>
              <th>Días vencida</th><th>Monto acordado</th><th>Canal</th><th>Gestor</th>
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
