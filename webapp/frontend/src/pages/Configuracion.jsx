import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { t } from "../i18n/index.js";

function InformeSemanal() {
  const [prog, setProg] = useState(null);
  const [nota, setNota] = useState("");
  useEffect(() => {
    api("/api/informe/programacion").then(setProg).catch(() => {});
  }, []);
  if (!prog) return null;

  const guardar = async () => {
    setNota("");
    try {
      await api("/api/informe/programacion",
                { metodo: "POST", cuerpo: { activo: prog.activo, destino: prog.destino } });
      setNota(t("informe_email.guardado"));
    } catch (e) { setNota(e.message); }
  };
  const enviarAhora = async () => {
    setNota("…");
    try {
      const r = await api("/api/informe/enviar-ahora", { metodo: "POST", cuerpo: {} });
      setNota(t("informe_email.enviado") + r.destino);
    } catch (e) { setNota(e.message); }
  };

  return (
    <div className="card" style={{ maxWidth: 720, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("informe_email.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("informe_email.subtitulo")}</p>
      {!prog.smtp_configurado && (
        <p style={{ color: "var(--amber)", fontSize: 12.5 }}>{t("informe_email.smtp_falta")}</p>
      )}
      <div className="toolbar">
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13.5 }}>
          <input type="checkbox" checked={prog.activo}
                 onChange={(e) => setProg({ ...prog, activo: e.target.checked })} />
          {t("informe_email.activo")}
        </label>
        <input type="email" style={{ flex: 1, minWidth: 220 }} value={prog.destino}
               placeholder={t("informe_email.destino_placeholder")}
               onChange={(e) => setProg({ ...prog, destino: e.target.value })} />
        <button className="btn" onClick={guardar}>{t("informe_email.guardar")}</button>
        <button className="btn ghost" onClick={enviarAhora}>{t("informe_email.enviar_ahora")}</button>
      </div>
      {nota && <span style={{ color: "var(--muted)", fontSize: 13 }}>{nota}</span>}
    </div>
  );
}

function AltaEmpresa() {
  const [nombre, setNombre] = useState("");
  const [nota, setNota] = useState("");
  const crear = async () => {
    setNota("…");
    try {
      const r = await api("/api/tenant/alta", { metodo: "POST", cuerpo: { empresa: nombre } });
      setNota(r.mensaje);
      setNombre("");
    } catch (e) { setNota(e.message); }
  };
  return (
    <div className="card" style={{ maxWidth: 720, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("alta_tenant.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("alta_tenant.subtitulo")}</p>
      <div className="toolbar">
        <input type="text" style={{ flex: 1, minWidth: 200 }} value={nombre}
               placeholder={t("alta_tenant.placeholder")}
               onChange={(e) => setNombre(e.target.value)} />
        <button className="btn" disabled={nombre.trim().length < 3} onClick={crear}>
          {t("alta_tenant.boton")}
        </button>
      </div>
      {nota && <span style={{ color: "var(--muted)", fontSize: 13 }}>{nota}</span>}
    </div>
  );
}

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
      <InformeSemanal />
      <AltaEmpresa />
    </>
  );
}
