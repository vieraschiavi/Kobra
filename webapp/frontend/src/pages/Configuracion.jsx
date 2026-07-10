import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { t } from "../i18n/index.js";

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
    if (!Object.keys(claves).length) { setNota(t("configuracion.nota.ingresar_clave")); return; }
    try {
      const r = await api("/api/config", { metodo: "POST", cuerpo: { claves } });
      setNota(t("configuracion.nota.guardadas_prefijo") + r.guardadas.join(", "));
      setValores({});
      cargar();
    } catch (err) {
      setNota(t("configuracion.nota.error_prefijo") + err.message);
    }
  }

  return (
    <>
      <h1 className="page-title">{t("configuracion.titulo")}</h1>
      <p className="page-sub">{t("configuracion.subtitulo")}</p>
      {error && <div className="empty">{error}</div>}
      {estado && (
        <form onSubmit={guardar} style={{ maxWidth: 720 }}>
          <div className="tablewrap">
            <table style={{ minWidth: 0 }}>
              <thead><tr>
                <th>{t("configuracion.tabla.col_clave")}</th>
                <th>{t("configuracion.tabla.col_estado")}</th>
                <th>{t("configuracion.tabla.col_nuevo_valor")}</th>
              </tr></thead>
              <tbody>
                {Object.entries(estado).map(([clave, on]) => (
                  <tr key={clave} className="norow">
                    <td style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{clave}</td>
                    <td>{on ? t("configuracion.estado.configurada") : t("configuracion.estado.sin_configurar")}</td>
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
            <button className="btn">{t("configuracion.boton_guardar")}</button>
            {nota && <span style={{ color: "var(--muted)", fontSize: 13 }}>{nota}</span>}
          </div>
        </form>
      )}
    </>
  );
}
