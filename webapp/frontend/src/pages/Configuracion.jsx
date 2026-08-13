// © 2026 Martín Viera. Todos los derechos reservados.
import React, { useEffect, useState } from "react";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

function ImportarCartera() {
  const [origen, setOrigen] = useState(null);
  const [fuente, setFuente] = useState("archivo");   // "archivo" | "sql"
  const [archivo, setArchivo] = useState(null);
  const [connUrl, setConnUrl] = useState("");
  const [consulta, setConsulta] = useState("");
  const [nota, setNota] = useState("");
  const [cargando, setCargando] = useState(false);
  const cargarOrigen = () => api("/api/cartera/origen").then(setOrigen).catch(() => {});
  useEffect(() => { cargarOrigen(); }, []);

  const trasImportar = (d) => {
    setNota(d.mensaje);
    // Recargar toda la app: KPIs/Cartera/Agenda cachean sus datos al montar,
    // así el dashboard entero refleja la cartera recién importada.
    setTimeout(() => window.location.reload(), 900);
  };

  const subir = async () => {
    if (!archivo) return;
    setCargando(true); setNota("");
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const ses = getSesion();
      const r = await fetch("/api/cartera/importar", {
        method: "POST",
        headers: ses ? { Authorization: `Bearer ${ses.token}` } : {},
        body: fd,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
      setArchivo(null);
      trasImportar(d);
    } catch (e) {
      setNota(e.message);
    } finally {
      setCargando(false);
    }
  };

  const importarSQL = async () => {
    if (!connUrl.trim() || !consulta.trim()) return;
    setCargando(true); setNota("");
    try {
      const d = await api("/api/cartera/importar-sql",
        { metodo: "POST", cuerpo: { conn_url: connUrl, consulta } });
      trasImportar(d);
    } catch (e) {
      setNota(e.message);
    } finally {
      setCargando(false);
    }
  };

  // Botón demo ON/OFF: alterna qué cartera ve TODO el dashboard. ON = datos
  // de demostración (sintéticos); OFF = la cartera real subida. Solo se puede
  // apagar la demo si ya hay una cartera real cargada.
  const cambiarModo = async (modo) => {
    setNota("");
    try {
      await api("/api/cartera/modo", { metodo: "POST", cuerpo: { modo } });
      window.location.reload();
    } catch (e) { setNota(e.message); }
  };

  const demoOn = origen ? origen.modo !== "real" : true;

  return (
    <div className="card" style={{ maxWidth: 720, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("importar_cartera.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("importar_cartera.subtitulo")}</p>

      {/* Botón demo ON/OFF — bien visible */}
      <div className="toolbar" style={{ alignItems: "center", gap: 12,
             padding: "10px 12px", borderRadius: 10,
             background: demoOn ? "rgba(242,180,65,.10)" : "rgba(124,194,66,.12)" }}>
        <b style={{ fontSize: 13 }}>{t("importar_cartera.modo_titulo")}</b>
        <button className={"btn" + (demoOn ? "" : " ghost")}
                onClick={() => cambiarModo("demo")} disabled={demoOn}>
          {t("importar_cartera.demo_on")}
        </button>
        <button className={"btn" + (demoOn ? " ghost" : "")}
                onClick={() => cambiarModo("real")}
                disabled={!demoOn || !(origen && origen.hay_real)}>
          {t("importar_cartera.demo_off")}
        </button>
        {origen && !origen.hay_real && (
          <span style={{ color: "var(--muted)", fontSize: 12 }}>
            {t("importar_cartera.sin_real_aun")}
          </span>
        )}
      </div>

      {origen && (
        <p style={{ fontSize: 12.5, fontWeight: 700,
                    color: origen.modo === "real" ? "var(--green)" : "var(--amber)" }}>
          {origen.modo === "real"
            ? t("importar_cartera.origen_real", { archivo: origen.archivo, deudores: origen.deudores })
            : t("importar_cartera.origen_demo")}
        </p>
      )}
      {/* Selector de fuente: archivo o base de datos (SQL) */}
      <div className="toolbar" style={{ gap: 8, marginBottom: 10 }}>
        <button className={"btn" + (fuente === "archivo" ? "" : " ghost")}
                onClick={() => { setFuente("archivo"); setNota(""); }}>
          {t("importar_cartera.fuente_archivo")}
        </button>
        <button className={"btn" + (fuente === "sql" ? "" : " ghost")}
                onClick={() => { setFuente("sql"); setNota(""); }}>
          {t("importar_cartera.fuente_sql")}
        </button>
      </div>

      {fuente === "archivo" ? (
        <div className="toolbar">
          <input type="file" accept=".csv,.xlsx,.xls"
                 onChange={(e) => setArchivo(e.target.files[0] || null)} />
          <button className="btn" disabled={!archivo || cargando} onClick={subir}>
            {cargando ? t("importar_cartera.subiendo") : t("importar_cartera.boton")}
          </button>
        </div>
      ) : (
        <div>
          <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 0 }}>
            {t("importar_cartera.sql_ayuda")}
          </p>
          <input type="text" value={connUrl} style={{ width: "100%", marginBottom: 8 }}
                 placeholder={t("importar_cartera.sql_url_placeholder")}
                 onChange={(e) => setConnUrl(e.target.value)} />
          <textarea value={consulta} rows={4} style={{ width: "100%", marginBottom: 8,
                        fontFamily: "var(--mono)", fontSize: 12.5 }}
                    placeholder={t("importar_cartera.sql_consulta_placeholder")}
                    onChange={(e) => setConsulta(e.target.value)} />
          <button className="btn" disabled={!connUrl.trim() || !consulta.trim() || cargando}
                  onClick={importarSQL}>
            {cargando ? t("importar_cartera.subiendo") : t("importar_cartera.sql_boton")}
          </button>
        </div>
      )}
      {nota && <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 8 }}>{nota}</div>}
    </div>
  );
}

function ProveedorIA() {
  const [datos, setDatos] = useState(null);
  const [nota, setNota] = useState("");
  const cargar = () => api("/api/config/proveedor_ia").then(setDatos).catch(() => {});
  useEffect(() => { cargar(); }, []);
  if (!datos) return null;

  const elegir = async (proveedor) => {
    setNota("");
    try {
      await api("/api/config/proveedor_ia", { metodo: "POST", cuerpo: { proveedor } });
      setNota(t("proveedor_ia.guardado"));
      cargar();
    } catch (e) { setNota(e.message); }
  };

  return (
    <div className="card" style={{ maxWidth: 720, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{t("proveedor_ia.titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("proveedor_ia.subtitulo")}</p>
      <div className="toolbar" style={{ flexWrap: "wrap", gap: 10 }}>
        {datos.proveedores.map((p) => (
          <label key={p} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13.5 }}>
            <input type="radio" name="proveedor_ia" checked={datos.proveedor === p}
                   onChange={() => elegir(p)} />
            {t(`proveedor_ia.nombre.${p}`)}
            {!datos.claves_configuradas[p] && (
              <span style={{ color: "var(--amber)", fontSize: 11.5 }}>
                {t("proveedor_ia.sin_clave")}
              </span>
            )}
          </label>
        ))}
      </div>
      {nota && <span style={{ color: "var(--muted)", fontSize: 13 }}>{nota}</span>}
    </div>
  );
}

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
      <ImportarCartera />
      <ProveedorIA />
      <InformeSemanal />
      <AltaEmpresa />
    </>
  );
}
