// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { api, fmtMonto } from "../api.js";
import { t } from "../i18n/index.js";

const VERDE = "#00c896";
const AMBAR = "#f2b441";
const ROJO = "#ff7675";
const GRIS = "#64748b";

// La severidad se comunica por color Y por etiqueta: quien no distingue los
// matices tiene que poder leerla igual (WCAG 1.4.1).
const SEVERIDAD = {
  alta: { color: ROJO, clave: "tablero.sev_alta" },
  media: { color: AMBAR, clave: "tablero.sev_media" },
};

// ── Buscador conversacional ──────────────────────────────────────────────────
function Preguntar({ sugeridas, iaDisponible }) {
  const [pregunta, setPregunta] = useState("");
  const [respuesta, setRespuesta] = useState(null);
  const [error, setError] = useState(null);
  const [pensando, setPensando] = useState(false);

  const enviar = async (texto) => {
    const q = (texto ?? pregunta).trim();
    if (!q) return;
    setPregunta(q);
    setPensando(true); setError(null); setRespuesta(null);
    try {
      setRespuesta(await api("/api/tablero/preguntar",
                             { metodo: "POST", cuerpo: { pregunta: q } }));
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setPensando(false);
    }
  };

  return (
    <div className="card" style={{ borderTop: `3px solid ${VERDE}` }}>
      <h3 style={{ marginTop: 0 }}>{t("tablero.preguntar_titulo")}</h3>

      <div className="toolbar" style={{ gap: 8 }}>
        <input
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") enviar(); }}
          placeholder={t("tablero.preguntar_ph")}
          style={{ flex: 1, minWidth: 220 }}
          disabled={!iaDisponible}
        />
        <button className="btn" onClick={() => enviar()}
                disabled={pensando || !iaDisponible || !pregunta.trim()}>
          {pensando ? t("tablero.pensando") : t("tablero.analizar")}
        </button>
      </div>

      {!iaDisponible && (
        <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 0 }}>
          {t("tablero.sin_ia")}
        </p>
      )}

      {iaDisponible && sugeridas.length > 0 && !respuesta && (
        <div className="toolbar" style={{ marginTop: 10, gap: 8, flexWrap: "wrap" }}>
          {sugeridas.map((s, i) => (
            <button key={i} className="btn ghost" style={{ fontSize: 12.5 }}
                    onClick={() => enviar(s)}>{s}</button>
          ))}
        </div>
      )}

      {error && <p style={{ color: ROJO, fontSize: 13 }}>{error}</p>}

      {respuesta && (
        <div style={{ marginTop: 14 }}>
          <p style={{ fontSize: 15, lineHeight: 1.7, margin: 0 }}>
            {respuesta.respuesta}
          </p>
          {/* Los números salen de una cuenta, no del modelo. Quien lee tiene
              que poder verificarlos sin creernos. */}
          <details style={{ marginTop: 10 }}>
            <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: 12.5 }}>
              {t("tablero.ver_datos")}
            </summary>
            <pre style={{
              fontSize: 11.5, color: "var(--muted)", overflowX: "auto",
              background: "var(--navy-800)", padding: 12, borderRadius: 8,
              marginTop: 8,
            }}>
              {JSON.stringify(respuesta.hechos_usados, null, 1)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

// ── Lista de advertencias / sugerencias / acciones ───────────────────────────
function Lista({ titulo, items, vacio, color }) {
  return (
    <div className="card" style={{ margin: 0, borderTop: `3px solid ${color}` }}>
      <h3 style={{ marginTop: 0, fontSize: 14, textTransform: "uppercase",
                   letterSpacing: ".06em", color: "var(--muted)" }}>
        {titulo}
      </h3>
      {items.length === 0 ? (
        <p style={{ color: "var(--faint)", fontSize: 13, margin: 0 }}>{vacio}</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((x, i) => {
            const sev = SEVERIDAD[x.severidad];
            return (
              <li key={i} style={{ padding: "10px 0",
                                   borderBottom: i < items.length - 1
                                     ? "1px solid var(--line)" : "none" }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                  {x.titulo}
                  {sev ? (
                    <span className="pill" style={{ marginLeft: 8, borderColor: sev.color,
                                                    color: sev.color, fontSize: 10.5 }}>
                      {t(sev.clave)}
                    </span>
                  ) : null}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 3 }}>
                  {x.detalle}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function Tablero() {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("/api/tablero").then(setD).catch((e) => setError(String(e.message || e)));
  }, []);

  if (error) return <div className="empty">{error}</div>;
  if (!d) return <div className="empty">{t("common.cargando")}</div>;

  const h = d.hechos;
  const kpis = [
    h.deuda_total !== undefined && {
      label: t("tablero.kpi_deuda"), valor: fmtMonto(h.deuda_total) },
    h.deudores !== undefined && {
      label: t("tablero.kpi_deudores"), valor: h.deudores.toLocaleString("es-UY") },
    h.pct_mora_alta !== undefined && {
      label: t("tablero.kpi_mora_alta"), valor: `${h.pct_mora_alta}%`,
      color: h.pct_mora_alta >= 40 ? ROJO : h.pct_mora_alta >= 25 ? AMBAR : undefined,
      sub: t("tablero.kpi_mora_alta_sub") },
    h.deuda_recuperable_alta_propension !== undefined && {
      label: t("tablero.kpi_recuperable"),
      valor: fmtMonto(h.deuda_recuperable_alta_propension),
      color: VERDE, sub: t("tablero.kpi_recuperable_sub") },
  ].filter(Boolean);

  return (
    <>
      <h2 className="page-title">{t("tablero.titulo")}</h2>
      <p className="page-sub">{t("tablero.subtitulo")}</p>

      <Preguntar sugeridas={d.preguntas_sugeridas} iaDisponible={d.ia_disponible} />

      <div className="kpi-grid" style={{ marginTop: 16 }}>
        {kpis.map((k, i) => (
          <div key={i} className="card kpi"
               style={k.color ? { borderTop: `3px solid ${k.color}` } : undefined}>
            <div className="label">{k.label}</div>
            <div className="value tnum" style={k.color ? { color: k.color } : undefined}>
              {k.valor}
            </div>
            {k.sub ? <div className="delta">{k.sub}</div> : null}
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gap: 14, marginTop: 16,
                    gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
        <Lista titulo={t("tablero.advertencias")} items={d.advertencias}
               vacio={t("tablero.sin_advertencias")} color={ROJO} />
        <Lista titulo={t("tablero.sugerencias")} items={d.sugerencias}
               vacio={t("tablero.sin_sugerencias")} color={AMBAR} />
        <Lista titulo={t("tablero.acciones")} items={d.acciones}
               vacio={t("tablero.sin_acciones")} color={VERDE} />
      </div>

      <p style={{ color: "var(--faint)", fontSize: 11.5, marginTop: 18 }}>
        {t("tablero.nota_calculo")}
      </p>
    </>
  );
}
