import React, { useEffect, useState } from "react";
import { api, fmtMonto, fmtPct } from "../api.js";
import { t } from "../i18n/index.js";

// Cuentas por cobrar: el análisis de CxC que Kobra no cubría (antigüedad de
// saldos, DSO, efectividad, conciliación de pagos y pagos mal aplicados).
//
// Todo lo que se muestra acá es CÁLCULO sobre la cartera real del cliente
// (kobra/cuentas_por_cobrar.py), no una respuesta generada: los mismos datos
// dan siempre el mismo número, y por eso sirve para cerrar un mes contable.

function Seccion({ titulo, sub, children }) {
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>{titulo}</h3>
      {sub && <p style={{ color: "var(--muted)", fontSize: 13, marginTop: -4 }}>{sub}</p>}
      {children}
    </div>
  );
}

function Antiguedad() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/cxc/antiguedad").then(setD).catch((e) => setError(e.message));
  }, []);
  if (error) return <Seccion titulo={t("cxc.antiguedad.titulo")}><div className="err">{error}</div></Seccion>;
  if (!d) return <Seccion titulo={t("cxc.antiguedad.titulo")}>{t("common.cargando")}</Seccion>;

  const a = d.antiguedad;
  const c = d.concentracion;
  return (
    <Seccion titulo={t("cxc.antiguedad.titulo")} sub={t("cxc.antiguedad.sub")}>
      <div style={{ overflowX: "auto" }}>
        <table className="tabla">
          <thead>
            <tr>
              <th>{t("cxc.antiguedad.tramo")}</th>
              <th className="num">{t("cxc.antiguedad.monto")}</th>
              <th className="num">{t("cxc.antiguedad.deudores")}</th>
              <th className="num">{t("cxc.antiguedad.pct")}</th>
            </tr>
          </thead>
          <tbody>
            {a.tramos.map((f) => (
              <tr key={f.tramo}>
                <td>{f.tramo}</td>
                <td className="num tnum">{fmtMonto(f.monto_uyu)}</td>
                <td className="num tnum">{f.deudores}</td>
                <td className="num tnum">{fmtPct(f.pct_del_total)}</td>
              </tr>
            ))}
            <tr style={{ fontWeight: 800 }}>
              <td>{t("cxc.antiguedad.total")}</td>
              <td className="num tnum">{fmtMonto(a.total_uyu)}</td>
              <td className="num tnum">{a.deudores}</td>
              <td className="num tnum">100%</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p style={{ marginTop: 14, fontSize: 13 }}>
        {t("cxc.concentracion.resumen", {
          n: c.top.length, pct: fmtPct(c.pct_acumulado),
        })}
      </p>
    </Seccion>
  );
}

function Dso() {
  const [ventas, setVentas] = useState(0);
  const [plazo, setPlazo] = useState(30);
  const [dias, setDias] = useState(30);
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  const calcular = async () => {
    setCargando(true); setError(""); setR(null);
    try {
      setR(await api("/api/cxc/dso", {
        metodo: "POST",
        cuerpo: { ventas_credito: ventas, dias_periodo: dias, plazo_estandar: plazo },
      }));
    } catch (e) { setError(e.message); }
    finally { setCargando(false); }
  };

  return (
    <Seccion titulo={t("cxc.dso.titulo")} sub={t("cxc.dso.sub")}>
      <div className="toolbar" style={{ gap: 10, flexWrap: "wrap", alignItems: "end" }}>
        <label style={{ display: "grid", gap: 4 }}>
          <span style={{ color: "var(--muted)", fontSize: 12 }}>{t("cxc.dso.ventas")}</span>
          <input type="number" min="0" value={ventas} style={{ width: 180 }}
                 onChange={(e) => setVentas(Math.max(0, Number(e.target.value) || 0))} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span style={{ color: "var(--muted)", fontSize: 12 }}>{t("cxc.dso.dias")}</span>
          <input type="number" min="1" value={dias} style={{ width: 90 }}
                 onChange={(e) => setDias(Math.max(1, Number(e.target.value) || 1))} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span style={{ color: "var(--muted)", fontSize: 12 }}>{t("cxc.dso.plazo")}</span>
          <input type="number" min="0" value={plazo} style={{ width: 90 }}
                 onChange={(e) => setPlazo(Math.max(0, Number(e.target.value) || 0))} />
        </label>
        <button className="btn" disabled={cargando || ventas <= 0} onClick={calcular}>
          {cargando ? t("common.cargando") : t("cxc.dso.calcular")}
        </button>
      </div>
      {error && <div className="err" style={{ marginTop: 10 }}>{error}</div>}
      {r && r.dso != null && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 34, fontWeight: 800, color: "var(--green-deep)" }}>
            {r.dso} <span style={{ fontSize: 15, color: "var(--muted)" }}>{t("cxc.dso.dias_unidad")}</span>
          </div>
          <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 4 }}>{r.formula}</p>
          {r.lectura && <p style={{ fontWeight: 600, fontSize: 13 }}>{r.lectura}</p>}
        </div>
      )}
      {r && r.dso == null && <div className="err" style={{ marginTop: 10 }}>{r.error}</div>}
    </Seccion>
  );
}

function Efectividad() {
  const [d, setD] = useState(null);
  useEffect(() => { api("/api/cxc/efectividad").then(setD).catch(() => setD({ error: true })); }, []);
  if (!d) return <Seccion titulo={t("cxc.efectividad.titulo")}>{t("common.cargando")}</Seccion>;
  if (d.efectividad == null) {
    return (
      <Seccion titulo={t("cxc.efectividad.titulo")}>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>{d.error || t("cxc.efectividad.sin_datos")}</p>
      </Seccion>
    );
  }
  return (
    <Seccion titulo={t("cxc.efectividad.titulo")} sub={t("cxc.efectividad.sub")}>
      <div style={{ fontSize: 34, fontWeight: 800, color: "var(--green-deep)" }}>
        {fmtPct(d.efectividad)}
      </div>
      <div className="kv" style={{ marginTop: 10 }}>
        <span className="k">{t("cxc.efectividad.mes")}</span><span>{d.mes}</span>
        <span className="k">{t("cxc.efectividad.gestionado")}</span>
        <span className="tnum">{fmtMonto(d.gestionado_uyu)}</span>
        <span className="k">{t("cxc.efectividad.cobrado")}</span>
        <span className="tnum">{fmtMonto(d.cobrado_uyu)}</span>
      </div>
      {d.comparacion && d.comparacion.variacion_pp != null && (
        <p style={{ marginTop: 10, fontSize: 13 }}>
          {t("cxc.efectividad.variacion", {
            pp: (d.comparacion.variacion_pp > 0 ? "+" : "") + d.comparacion.variacion_pp,
            mes: d.comparacion.mes,
          })}
        </p>
      )}
    </Seccion>
  );
}

function Conciliar() {
  const [monto, setMonto] = useState(0);
  const [texto, setTexto] = useState("");
  const [r, setR] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  // "F-4501 30000" por línea — el formato en que la gente ya tiene sus
  // facturas abiertas, sin obligar a armar un JSON.
  const parsear = (s) => s.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const partes = l.split(/[\s,;\t]+/).filter(Boolean);
    const montoStr = partes[partes.length - 1].replace(/[^\d.-]/g, "");
    return { id: partes.slice(0, -1).join(" ") || partes[0], monto: Number(montoStr) || 0 };
  }).filter((f) => f.monto > 0);

  const conciliar = async () => {
    setCargando(true); setError(""); setR(null);
    try {
      setR(await api("/api/cxc/conciliar", {
        metodo: "POST", cuerpo: { monto, facturas: parsear(texto) },
      }));
    } catch (e) { setError(e.message); }
    finally { setCargando(false); }
  };

  return (
    <Seccion titulo={t("cxc.conciliar.titulo")} sub={t("cxc.conciliar.sub")}>
      <div className="toolbar" style={{ gap: 10, alignItems: "end", flexWrap: "wrap" }}>
        <label style={{ display: "grid", gap: 4 }}>
          <span style={{ color: "var(--muted)", fontSize: 12 }}>{t("cxc.conciliar.monto")}</span>
          <input type="number" min="0" value={monto} style={{ width: 180 }}
                 onChange={(e) => setMonto(Math.max(0, Number(e.target.value) || 0))} />
        </label>
        <button className="btn" disabled={cargando || monto <= 0 || !texto.trim()}
                onClick={conciliar}>
          {cargando ? t("common.cargando") : t("cxc.conciliar.buscar")}
        </button>
      </div>
      <textarea rows={5} value={texto} onChange={(e) => setTexto(e.target.value)}
                placeholder={t("cxc.conciliar.placeholder")}
                style={{ width: "100%", marginTop: 10, fontFamily: "ui-monospace, monospace",
                         fontSize: 13 }} />
      {error && <div className="err" style={{ marginTop: 10 }}>{error}</div>}
      {r && (
        <div style={{ marginTop: 12 }}>
          {r.error && <div className="err">{r.error}</div>}
          {r.match && (
            <p style={{ fontWeight: 700, color: "var(--green-deep)" }}>
              {t("cxc.conciliar.match", { facturas: r.match.facturas.join(" + ") })}
            </p>
          )}
          {r.ambiguo && (
            // El caso que más importa mostrar bien: hay más de una respuesta
            // válida y el sistema NO elige. Aplicar "la que parece" deja un
            // saldo mal imputado que reaparece como un descuadre.
            <div>
              <p style={{ fontWeight: 700, color: "var(--amber)" }}>{t("cxc.conciliar.ambiguo")}</p>
              <ul style={{ fontSize: 13 }}>
                {r.candidatos.map((c, i) => <li key={i}>{c.facturas.join(" + ")}</li>)}
              </ul>
            </div>
          )}
          {r.sin_match && (
            <div>
              <p style={{ fontWeight: 700, color: "var(--muted)" }}>{t("cxc.conciliar.sin_match")}</p>
              <ul style={{ fontSize: 13 }}>
                {r.mas_cercanas.map((c) => (
                  <li key={c.id}>{c.id} · {fmtMonto(c.monto)} ({c.diferencia > 0 ? "+" : ""}{fmtMonto(c.diferencia)})</li>
                ))}
              </ul>
            </div>
          )}
          {r.aviso && <p style={{ color: "var(--amber)", fontSize: 12.5 }}>{r.aviso}</p>}
        </div>
      )}
    </Seccion>
  );
}

function Anomalias() {
  const [d, setD] = useState(null);
  useEffect(() => { api("/api/cxc/anomalias").then(setD).catch(() => setD({ hallazgos: [] })); }, []);
  if (!d) return <Seccion titulo={t("cxc.anomalias.titulo")}>{t("common.cargando")}</Seccion>;
  return (
    <Seccion titulo={t("cxc.anomalias.titulo")} sub={t("cxc.anomalias.sub")}>
      {d.total_hallazgos === 0 ? (
        <p style={{ color: "var(--muted)", fontSize: 13 }}>
          {t("cxc.anomalias.limpio", { n: d.revisados || 0 })}
        </p>
      ) : (
        <ul style={{ fontSize: 13.5 }}>
          {d.hallazgos.map((h, i) => (
            <li key={i} style={{ marginBottom: 6 }}>
              <b>{t("cxc.anomalias.tipo_" + h.tipo)}</b> — {h.detalle}
              <span style={{ color: "var(--muted)" }}> ({h.referencias.join(", ")})</span>
            </li>
          ))}
        </ul>
      )}
    </Seccion>
  );
}

export default function CuentasPorCobrar() {
  return (
    <div>
      <h2>{t("cxc.titulo")}</h2>
      <p style={{ color: "var(--muted)", fontSize: 13.5, maxWidth: 780 }}>{t("cxc.subtitulo")}</p>
      <Antiguedad />
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 320 }}><Dso /></div>
        <div style={{ flex: 1, minWidth: 320 }}><Efectividad /></div>
      </div>
      <Conciliar />
      <Anomalias />
    </div>
  );
}
