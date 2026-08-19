// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";

const VERDE = "#00c896";
const ROJO = "#ff7675";

// Cómo se muestra cada valor. El formato lo elige quien define la medida y
// cambia solo la presentación, nunca el cálculo.
function formatear(valor, formato) {
  if (valor === null || valor === undefined) return "—";
  if (formato === "moneda") return "$U " + Math.round(valor).toLocaleString("es-UY");
  if (formato === "porcentaje") return valor.toFixed(1) + "%";
  return Math.abs(valor) >= 1000
    ? Math.round(valor).toLocaleString("es-UY")
    : valor.toFixed(2).replace(/\.00$/, "");
}

// ── El plan no incluye el módulo ─────────────────────────────────────────────
function NoIncluido({ detalle }) {
  return (
    <div className="card" style={{ maxWidth: 620, margin: "40px auto", textAlign: "center" }}>
      <h3 style={{ marginTop: 0 }}>{t("medidas.no_incluido_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 14 }}>{t("medidas.no_incluido_sub")}</p>
      {detalle ? <p style={{ color: "var(--faint)", fontSize: 12 }}>{detalle}</p> : null}
      <a className="btn" href="https://mvkobranzaia.com/#precios"
         target="_blank" rel="noreferrer">{t("medidas.ver_planes")}</a>
    </div>
  );
}

// ── Tarjeta de una medida ────────────────────────────────────────────────────
// Una medida rota se muestra con su error en vez de desaparecer: si se
// ocultara, quien la definió no se entera de que dejó de andar.
function TarjetaMedida({ v }) {
  const roto = v.error !== null;
  return (
    <div className="card kpi" style={{ margin: 0, borderTop: `3px solid ${roto ? ROJO : VERDE}` }}>
      <div className="label">{v.nombre}</div>
      <div className="value tnum" style={{ color: roto ? ROJO : undefined, fontSize: roto ? 14 : undefined }}>
        {roto ? t("medidas.no_calcula") : formatear(v.valor, v.formato)}
      </div>
      {roto
        ? <div className="delta" style={{ color: ROJO }}>{v.error}</div>
        : v.descripcion
          ? <div className="delta">{v.descripcion}</div>
          : null}
    </div>
  );
}

// ── Editor ───────────────────────────────────────────────────────────────────
function Editor({ medidas, columnas, funciones, onGuardado }) {
  const [filas, setFilas] = useState(medidas);
  const [prueba, setPrueba] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState(null);

  const cambiar = (i, campo, valor) => {
    const copia = filas.map((f, j) => (j === i ? { ...f, [campo]: valor } : f));
    setFilas(copia);
    setPrueba((p) => ({ ...p, [i]: undefined }));   // el resultado viejo ya no vale
  };

  const agregar = () =>
    setFilas([...filas, { nombre: "", formula: "", descripcion: "", formato: "numero" }]);

  const quitar = (i) => setFilas(filas.filter((_, j) => j !== i));

  const probar = async (i) => {
    try {
      const r = await api("/api/medidas/validar", { metodo: "POST", cuerpo: filas[i] });
      setPrueba((p) => ({ ...p, [i]: r }));
    } catch (e) {
      setPrueba((p) => ({ ...p, [i]: { ok: false, error: String(e.message || e) } }));
    }
  };

  const guardar = async () => {
    setGuardando(true);
    setAviso(null);
    try {
      await api("/api/medidas", { metodo: "POST", cuerpo: filas });
      setAviso({ ok: true, texto: t("medidas.guardado") });
      onGuardado();
    } catch (e) {
      setAviso({ ok: false, texto: String(e.message || e) });
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>{t("medidas.editor_titulo")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("medidas.editor_sub")}</p>

      {filas.map((f, i) => {
        const p = prueba[i];
        return (
          <div key={i} className="card" style={{ marginBottom: 12, background: "var(--navy-800)" }}>
            <div className="grid-2" style={{ gap: 10 }}>
              <label>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>{t("medidas.campo_nombre")}</span>
                <input value={f.nombre} onChange={(e) => cambiar(i, "nombre", e.target.value)}
                       placeholder={t("medidas.ph_nombre")} />
              </label>
              <label>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>{t("medidas.campo_formato")}</span>
                <select value={f.formato} onChange={(e) => cambiar(i, "formato", e.target.value)}>
                  <option value="numero">{t("medidas.formato_numero")}</option>
                  <option value="moneda">{t("medidas.formato_moneda")}</option>
                  <option value="porcentaje">{t("medidas.formato_porcentaje")}</option>
                </select>
              </label>
            </div>
            <label style={{ display: "block", marginTop: 8 }}>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>{t("medidas.campo_formula")}</span>
              <input value={f.formula} onChange={(e) => cambiar(i, "formula", e.target.value)}
                     style={{ fontFamily: "ui-monospace, monospace", fontSize: 13 }}
                     placeholder="suma(monto_deuda) / contar()" />
            </label>
            <div className="toolbar" style={{ marginTop: 8 }}>
              <button className="btn ghost" onClick={() => probar(i)}>{t("medidas.probar")}</button>
              <button className="btn ghost" onClick={() => quitar(i)}>{t("medidas.quitar")}</button>
              {p ? (
                <span style={{ fontSize: 12.5, color: p.ok ? VERDE : ROJO }}>
                  {p.ok
                    ? `${t("medidas.da")} ${formatear(p.vista_previa?.valor, f.formato)}`
                    : p.error}
                </span>
              ) : null}
            </div>
          </div>
        );
      })}

      <div className="toolbar">
        <button className="btn ghost" onClick={agregar}>{t("medidas.agregar")}</button>
        <button className="btn" onClick={guardar} disabled={guardando}>
          {guardando ? t("common.cargando") : t("medidas.guardar")}
        </button>
        {aviso ? (
          <span style={{ fontSize: 13, color: aviso.ok ? VERDE : ROJO }}>{aviso.texto}</span>
        ) : null}
      </div>

      {/* Referencia: sin esto, un campo de fórmula en blanco no lo usa nadie */}
      <details style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: 13 }}>
          {t("medidas.ayuda_titulo")}
        </summary>
        <div style={{ marginTop: 10, fontSize: 12.5, color: "var(--muted)", lineHeight: 1.8 }}>
          <p style={{ margin: "0 0 6px" }}><strong>{t("medidas.ayuda_funciones")}</strong></p>
          <code style={{ fontSize: 12 }}>{funciones.join(" · ")}</code>
          <p style={{ margin: "12px 0 6px" }}><strong>{t("medidas.ayuda_columnas")}</strong></p>
          <code style={{ fontSize: 12 }}>{columnas.join(" · ")}</code>
          <p style={{ margin: "12px 0 6px" }}><strong>{t("medidas.ayuda_ejemplos")}</strong></p>
          <code style={{ display: "block", fontSize: 12, whiteSpace: "pre-line" }}>
            {"promedio(monto_deuda)\nsuma(monto_deuda) / contar()\ncontar_si(dias_mora > 90) / contar() * 100"}
          </code>
        </div>
      </details>
    </div>
  );
}

export default function Medidas() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [sinPlan, setSinPlan] = useState(null);
  const esAdmin = (getSesion() || {}).rol === "admin";

  const cargar = () => {
    api("/api/medidas")
      .then(setDatos)
      .catch((e) => {
        const msg = String(e.message || e);
        if (msg.includes("mvkobranzaia.com") || msg.toLowerCase().includes("no incluye")) {
          setSinPlan(msg);
        } else {
          setError(msg);
        }
      });
  };

  useEffect(cargar, []);

  if (sinPlan) return <NoIncluido detalle={sinPlan} />;
  if (error) return <div className="empty">{error}</div>;
  if (!datos) return <div className="empty">{t("common.cargando")}</div>;

  return (
    <>
      <h2 className="page-title">{t("medidas.titulo")}</h2>
      <p className="page-sub">{t("medidas.subtitulo")}</p>

      <div className="kpi-grid">
        {datos.valores.map((v, i) => <TarjetaMedida key={i} v={v} />)}
      </div>

      {esAdmin ? (
        <Editor medidas={datos.medidas} columnas={datos.columnas}
                funciones={datos.funciones} onGuardado={cargar} />
      ) : (
        <p style={{ color: "var(--faint)", fontSize: 12.5, marginTop: 16 }}>
          {t("medidas.solo_admin_edita")}
        </p>
      )}
    </>
  );
}
