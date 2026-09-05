// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { api, descargar } from "../api.js";
import { t } from "../i18n/index.js";

// Qué hace el programa, en orden, contado dos veces.
//
// El problema que resuelve esta pantalla: en una demo, el gerente pregunta
// "¿y esto qué hace?" y el técnico de sistemas pregunta "¿con qué modelo?".
// Contestar las dos con el mismo texto deja a los dos a medias. Acá cada
// etapa trae los dos registros completos y el lector elige — por eso el
// selector de arriba cambia qué se muestra, y "Los dos" es el default: en una
// reunión están las dos personas sentadas a la misma mesa.
const VISTAS = ["ambos", "criollo", "tecnico"];

function Etapa({ e, vista, total }) {
  const [abierta, setAbierta] = useState(false);
  const verTec = vista === "ambos" || vista === "tecnico";
  const verCri = vista === "ambos" || vista === "criollo";

  return (
    <article className="card" style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className="pill media tnum" style={{ flexShrink: 0 }}>
          {e.orden}/{total}
        </span>
        <h3 style={{ margin: 0, flex: 1 }}>{e.titulo}</h3>
      </div>

      {verTec && (
        <div style={{ marginTop: 10 }}>
          <div className="etiqueta-bloque">{t("memoria.tecnico")}</div>
          <p style={{ margin: "3px 0 0" }}>{e.tecnico}</p>
        </div>
      )}
      {verCri && (
        <div style={{ marginTop: 10, background: "var(--surface-2, #f4f8fc)",
                      borderLeft: "3px solid var(--brand, #2f6fb0)",
                      padding: "8px 11px", borderRadius: "0 4px 4px 0" }}>
          <div className="etiqueta-bloque">{t("memoria.criollo")}</div>
          <p style={{ margin: "3px 0 0" }}>{e.criollo}</p>
        </div>
      )}

      {/* El detalle va plegado: en una demo se recorren 13 etapas de un
          vistazo, y quien quiere el fondo lo abre. Desplegado todo de entrada,
          la pantalla mide cuatro metros y nadie la lee. */}
      <button className="btn ghost" style={{ marginTop: 10, fontSize: 12.5 }}
              onClick={() => setAbierta(!abierta)}>
        {abierta ? t("memoria.ver_menos") : t("memoria.ver_mas")}
      </button>

      {abierta && (
        <div style={{ marginTop: 8, fontSize: 13.5 }}>
          <div className="etiqueta-bloque">{t("memoria.por_que")}</div>
          <p style={{ margin: "3px 0 10px" }}>{e.por_que}</p>

          <div className="etiqueta-bloque">{t("memoria.repercusion")}</div>
          <p style={{ margin: "3px 0 10px" }}>{e.repercusion}</p>

          {e.limites && (
            <>
              <div className="etiqueta-bloque">{t("memoria.limites")}</div>
              <p style={{ margin: "3px 0 10px", color: "var(--warn-deep, #7a4a1e)" }}>
                {e.limites}
              </p>
            </>
          )}

          <div style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 8 }}>
            <div><b>{t("memoria.entra")}:</b> {e.entradas}</div>
            <div><b>{t("memoria.sale")}:</b> {e.salidas}</div>
            <div style={{ marginTop: 4 }}>
              <b>{t("memoria.donde_vive")}:</b>{" "}
              {e.modulos.map((m) => (
                <code key={m} style={{ marginRight: 6 }}>{m}</code>
              ))}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

export default function MemoriaTecnica() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  const [vista, setVista] = useState("ambos");
  const [bajando, setBajando] = useState("");

  useEffect(() => {
    api("/api/memoria-tecnica").then(setDatos).catch((e) => setError(e.message));
  }, []);

  async function exportar(formato) {
    setBajando(formato);
    setError("");
    try {
      await descargar(`/api/memoria-tecnica/export.${formato}`,
                      `MVKobraAI_Memoria_Tecnica.${formato}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBajando("");
    }
  }

  return (
    <>
      <h1 className="page-title">{t("memoria.titulo")}</h1>
      <p className="page-sub">{t("memoria.subtitulo")}</p>

      <div className="toolbar" style={{ justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {VISTAS.map((v) => (
            <button key={v} className={"btn " + (vista === v ? "" : "ghost")}
                    onClick={() => setVista(v)}>
              {t(`memoria.vista_${v}`)}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["html", "docx", "pdf"].map((f) => (
            <button key={f} className="btn ghost" disabled={!!bajando}
                    onClick={() => exportar(f)}>
              ⬇ {bajando === f ? t("memoria.bajando") : f.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("memoria.cargando")}</div>}

      {datos && (
        <>
          {datos.datos_demo && (
            <div className="card" style={{ marginBottom: 14, fontSize: 13 }}>
              {t("memoria.aviso_demo")}
            </div>
          )}
          {datos.etapas.map((e) => (
            <Etapa key={e.id} e={e} vista={vista} total={datos.etapas.length} />
          ))}
        </>
      )}
    </>
  );
}
