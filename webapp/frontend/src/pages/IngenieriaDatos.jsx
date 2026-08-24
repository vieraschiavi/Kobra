// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useRef, useState } from "react";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

// Mismos colores que el resto de las páginas. El color nunca va solo: cada
// estado lleva además su texto, porque quien no distingue los matices tiene
// que poder leerlo igual (WCAG 1.4.1).
const VERDE = "#00c896";
const AMBAR = "#f2b441";
const ROJO = "#ff7675";
const AZUL = "#6c8cd5";
const GRIS = "#64748b";

const COLOR_NIVEL = { publico: GRIS, interno: AZUL, personal: AMBAR, sensible: ROJO };

// El riesgo del join viene del backend como texto que empieza con la palabra
// clave — se colorea por esa palabra, no por posición.
function colorRiesgo(riesgo) {
  const r = String(riesgo || "");
  if (r.startsWith("ALTO")) return ROJO;
  if (r.startsWith("MEDIO")) return AMBAR;
  return VERDE;
}

function Etiqueta({ texto, color }) {
  return (
    <span style={{
      background: `${color}22`, color, border: `1px solid ${color}55`,
      borderRadius: 6, padding: "1px 7px", fontSize: 12, whiteSpace: "nowrap",
    }}>{texto}</span>
  );
}

// ── Una tabla analizada ──────────────────────────────────────────────────────
function Tabla({ nombre, perfil, claves, ddl, dbt, features, tipado }) {
  const [ver, setVer] = useState("columnas");
  const pestanas = ["columnas", "claves", "features", "ddl", "dbt"];

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>{nombre}</h3>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>
          {perfil.filas.toLocaleString()} {t("ingdatos.filas")} · {perfil.columnas} {t("ingdatos.columnas")}
        </span>
      </div>

      {tipado?.length > 0 && (
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 8 }}>
          {t("ingdatos.tipado_aviso")}{" "}
          {tipado.map((c) => `${c.columna} (${c.de} → ${c.a})`).join(", ")}
        </p>
      )}

      <div style={{ display: "flex", gap: 6, margin: "12px 0", flexWrap: "wrap" }}>
        {pestanas.map((p) => (
          <button key={p} className={ver === p ? "btn" : "btn ghost"}
                  style={{ padding: "4px 10px", fontSize: 13 }}
                  onClick={() => setVer(p)}>
            {t(`ingdatos.tab_${p}`)}
          </button>
        ))}
      </div>

      {ver === "columnas" && (
        <div style={{ overflowX: "auto" }}>
          <table className="tabla">
            <thead>
              <tr>
                <th>{t("ingdatos.col_columna")}</th>
                <th>{t("ingdatos.col_rol")}</th>
                <th>{t("ingdatos.col_sensibilidad")}</th>
                <th className="tnum">{t("ingdatos.col_nulos")}</th>
                <th className="tnum">{t("ingdatos.col_unicos")}</th>
              </tr>
            </thead>
            <tbody>
              {perfil.detalle.map((c) => (
                <tr key={c.columna}>
                  <td>{c.columna}</td>
                  <td style={{ color: "var(--muted)" }}>{t(`ingdatos.rol.${c.rol}`)}</td>
                  <td>
                    <Etiqueta texto={t(`ingdatos.nivel.${c.sensibilidad}`)}
                              color={COLOR_NIVEL[c.sensibilidad] || GRIS} />
                  </td>
                  <td className="tnum">{c.nulos_pct}%</td>
                  <td className="tnum">{c.unicos.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {ver === "claves" && (
        <div>
          <h4 style={{ marginTop: 0 }}>{t("ingdatos.pk")}</h4>
          {claves.pk.length === 0
            ? <p style={{ color: "var(--muted)" }}>{t("ingdatos.sin_pk")}</p>
            : (
              <ul>
                {claves.pk.map((k) => (
                  <li key={k.columna}>
                    <strong>{k.columna}</strong> — {k.tipo}{" "}
                    <Etiqueta texto={k.confianza}
                              color={k.confianza === "alta" ? VERDE : AMBAR} />
                  </li>
                ))}
              </ul>
            )}
          <h4>{t("ingdatos.fk")}</h4>
          {claves.fk_candidatas.length === 0
            ? <p style={{ color: "var(--muted)" }}>{t("ingdatos.sin_fk")}</p>
            : <p>{claves.fk_candidatas.join(", ")}</p>}
        </div>
      )}

      {ver === "features" && (
        <div style={{ overflowX: "auto" }}>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("ingdatos.features_intro")}</p>
          <table className="tabla">
            <thead>
              <tr>
                <th>{t("ingdatos.col_feature")}</th>
                <th>{t("ingdatos.col_origen")}</th>
                <th>{t("ingdatos.col_formula")}</th>
              </tr>
            </thead>
            <tbody>
              {(features || []).map((f) => (
                <tr key={f.feature}>
                  <td>{f.feature}</td>
                  <td style={{ color: "var(--muted)" }}>{f.origen}</td>
                  <td>
                    {f.formula}
                    {f.aviso && (
                      <>
                        {" "}
                        <Etiqueta texto={t("ingdatos.fuga")} color={AMBAR} />
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(ver === "ddl" || ver === "dbt") && (
        <pre style={{
          background: "#0b1220", border: "1px solid #24344f", borderRadius: 8,
          padding: 12, overflowX: "auto", fontSize: 12, lineHeight: 1.5,
        }}>{ver === "ddl" ? ddl : dbt}</pre>
      )}
    </div>
  );
}

// ── Mapa de joins entre tablas ───────────────────────────────────────────────
function Joins({ joins }) {
  if (!joins || joins.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>{t("ingdatos.joins_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("ingdatos.joins_intro")}</p>
      <div style={{ overflowX: "auto" }}>
        <table className="tabla">
          <thead>
            <tr>
              <th>{t("ingdatos.col_union")}</th>
              <th className="tnum">{t("ingdatos.col_solape")}</th>
              <th>{t("ingdatos.col_cardinalidad")}</th>
              <th>{t("ingdatos.col_riesgo")}</th>
            </tr>
          </thead>
          <tbody>
            {joins.map((j, i) => (
              <tr key={i}>
                <td>
                  <code style={{ fontSize: 12 }}>
                    {j.izquierda}.{j.columna_izquierda} = {j.derecha}.{j.columna_derecha}
                  </code>
                  {!j.mismo_nombre && (
                    <>
                      {" "}
                      <Etiqueta texto={t("ingdatos.distinto_nombre")} color={AZUL} />
                    </>
                  )}
                </td>
                <td className="tnum">{j.solape_pct}%</td>
                <td>{j.cardinalidad}</td>
                <td><Etiqueta texto={j.riesgo} color={colorRiesgo(j.riesgo)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function IngenieriaDatos() {
  const [origen, setOrigen] = useState("archivo");
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [url, setUrl] = useState("");
  const [tabla, setTabla] = useState("");
  const [consulta, setConsulta] = useState("");
  const archivoRef = useRef(null);

  async function analizarArchivo(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    setCargando(true); setError(null); setDatos(null);
    try {
      const fd = new FormData();
      fd.append("archivo", f);
      const ses = getSesion();
      const r = await fetch("/api/datos/analizar-archivo", {
        method: "POST",
        headers: ses ? { Authorization: `Bearer ${ses.token}` } : {},
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || `Error ${r.status}`);
      setDatos(j);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setCargando(false);
      if (archivoRef.current) archivoRef.current.value = "";
    }
  }

  async function analizarBase() {
    setCargando(true); setError(null); setDatos(null);
    try {
      // La URL lleva la contraseña: va en el CUERPO, nunca en la query string
      // (una URL termina en el log del servidor y en el historial del navegador).
      setDatos(await api("/api/datos/analizar-base", {
        metodo: "POST",
        cuerpo: {
          url,
          tabla: tabla || null,
          consulta: consulta || null,
        },
      }));
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setCargando(false);
    }
  }

  return (
    <div>
      <h2 className="page-title">{t("ingdatos.titulo")}</h2>
      <p className="page-sub">{t("ingdatos.subtitulo")}</p>

      <div className="card">
        <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          <button className={origen === "archivo" ? "btn" : "btn ghost"}
                  onClick={() => setOrigen("archivo")}>
            {t("ingdatos.origen_archivo")}
          </button>
          <button className={origen === "base" ? "btn" : "btn ghost"}
                  onClick={() => setOrigen("base")}>
            {t("ingdatos.origen_base")}
          </button>
        </div>

        {origen === "archivo" ? (
          <div>
            <label htmlFor="ing-archivo" style={{ display: "block", marginBottom: 6 }}>
              {t("ingdatos.subir")}
            </label>
            <input id="ing-archivo" ref={archivoRef} type="file"
                   accept=".csv,.xlsx,.xls"
                   aria-label={t("ingdatos.subir")}
                   onChange={analizarArchivo} disabled={cargando} />
          </div>
        ) : (
          <div style={{ display: "grid", gap: 10, maxWidth: 720 }}>
            <div>
              <label htmlFor="ing-url" style={{ display: "block", marginBottom: 4 }}>
                {t("ingdatos.url")}
              </label>
              <input id="ing-url" type="password" className="input"
                     autoComplete="off"
                     aria-label={t("ingdatos.url")}
                     placeholder="postgresql+psycopg2://usuario:clave@host:5432/base"
                     value={url} onChange={(e) => setUrl(e.target.value)} />
              <small style={{ color: "var(--muted)" }}>{t("ingdatos.url_ayuda")}</small>
            </div>
            <div>
              <label htmlFor="ing-tabla" style={{ display: "block", marginBottom: 4 }}>
                {t("ingdatos.tabla")}
              </label>
              <input id="ing-tabla" className="input" autoComplete="off"
                     aria-label={t("ingdatos.tabla")}
                     placeholder={t("ingdatos.tabla_ph")}
                     value={tabla} onChange={(e) => setTabla(e.target.value)} />
            </div>
            <div>
              <label htmlFor="ing-consulta" style={{ display: "block", marginBottom: 4 }}>
                {t("ingdatos.consulta")}
              </label>
              <textarea id="ing-consulta" className="input" rows={3}
                        aria-label={t("ingdatos.consulta")}
                        placeholder="SELECT * FROM clientes"
                        value={consulta} onChange={(e) => setConsulta(e.target.value)} />
              <small style={{ color: "var(--muted)" }}>{t("ingdatos.consulta_ayuda")}</small>
            </div>
            <div>
              <button className="btn" onClick={analizarBase} disabled={cargando || !url}>
                {cargando ? t("ingdatos.analizando") : t("ingdatos.analizar")}
              </button>
            </div>
          </div>
        )}

        {cargando && <p style={{ color: "var(--muted)" }}>{t("ingdatos.analizando")}</p>}
        {error && <p style={{ color: ROJO }} role="alert">{error}</p>}
      </div>

      {datos && (
        <>
          <Joins joins={datos.joins} />
          {datos.tablas.map((n) => (
            <Tabla key={n} nombre={n}
                   perfil={datos.perfiles[n]}
                   claves={datos.claves[n]}
                   ddl={datos.ddl[n]}
                   dbt={datos.dbt[n]}
                   features={datos.features?.[n]}
                   tipado={datos.tipado?.[n]} />
          ))}
        </>
      )}
    </div>
  );
}
