import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Configuracion() {
  const [estado, setEstado] = useState(null);
  const [valores, setValores] = useState({});
  const [nota, setNota] = useState("");
  const [error, setError] = useState("");

  const cargar = () =>
    api("/api/config/estado").then(setEstado).catch((e) => setError(e.message));
  useEffect(() => { cargar(); }, []);

  async function guardar(e) {
    e.preventDefault();
    const claves = Object.fromEntries(
      Object.entries(valores).filter(([, v]) => v && v.trim()));
    if (!Object.keys(claves).length) { setNota("Ingresá al menos una clave."); return; }
    try {
      const r = await api("/api/config", { metodo: "POST", cuerpo: { claves } });
      setNota("✅ Guardadas: " + r.guardadas.join(", "));
      setValores({});
      cargar();
    } catch (err) {
      setNota("Error: " + err.message);
    }
  }

  return (
    <>
      <h1 className="page-title">Configuración</h1>
      <p className="page-sub">Las claves se guardan cifradas en el servidor (keyring del
        sistema o archivo cifrado, igual que en el dashboard clásico) y se cargan solas en
        cada arranque. Dejá vacío lo que no quieras cambiar.</p>
      {error && <div className="empty">{error}</div>}
      {estado && (
        <form onSubmit={guardar} style={{ maxWidth: 720 }}>
          <div className="tablewrap">
            <table style={{ minWidth: 0 }}>
              <thead><tr><th>Clave</th><th>Estado</th><th>Nuevo valor</th></tr></thead>
              <tbody>
                {Object.entries(estado).map(([clave, on]) => (
                  <tr key={clave} className="norow">
                    <td style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{clave}</td>
                    <td>{on ? "🟢 configurada" : "⚪ sin configurar"}</td>
                    <td>
                      <input type="password" value={valores[clave] || ""}
                             style={{ width: "100%", minWidth: 180 }}
                             onChange={(e) =>
                               setValores({ ...valores, [clave]: e.target.value })} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="toolbar" style={{ marginTop: 14 }}>
            <button className="btn">💾 Guardar claves</button>
            {nota && <span style={{ color: "var(--muted)", fontSize: 13 }}>{nota}</span>}
          </div>
        </form>
      )}
    </>
  );
}
