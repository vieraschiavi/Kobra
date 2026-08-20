// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useCallback, useEffect, useState } from "react";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";
import ModuloNoIncluido, { esFaltaDePlan } from "../components/ModuloNoIncluido.jsx";

const VERDE = "#00c896";
const AMBAR = "#f2b441";
const ROJO = "#ff7675";

const num = (n) => Math.round(n || 0).toLocaleString("es-UY");
const money = (n) => "$ " + num(n);

// Las cinco listas, con las columnas que muestra cada una. El motivo va
// siempre última y ancha: es la columna que hace que la sugerencia se aplique
// en vez de quedar en una lista que nadie mira.
const LISTAS = [
  { clave: "ofertas", cols: ["sku", "nombre", "stock", "dias_stock", "precio",
                             "descuento_pct", "precio_oferta", "capital_inmovilizado"] },
  { clave: "reposicion", cols: ["sku", "nombre", "proveedor", "stock", "dias_stock",
                                "cantidad_sugerida", "inversion", "venta_en_riesgo"] },
  { clave: "precios", cols: ["sku", "nombre", "precio", "precio_sugerido",
                             "suba_pct", "margen_extra_mensual"] },
  { clave: "zonas", cols: ["zona", "clientes", "venta", "potencial"] },
  { clave: "recuperar", cols: ["cliente_id", "cada_dias", "dias_sin_comprar",
                               "venta_mensual_perdida"] },
];

const ETIQUETA = {
  sku: "col_sku", nombre: "col_producto", stock: "col_stock",
  dias_stock: "col_dias_stock", precio: "col_precio",
  descuento_pct: "col_descuento", precio_oferta: "col_precio_oferta",
  capital_inmovilizado: "col_inmovilizado", proveedor: "col_proveedor",
  cantidad_sugerida: "col_cantidad", inversion: "col_inversion",
  venta_en_riesgo: "col_riesgo", precio_sugerido: "col_sugerido",
  suba_pct: "col_suba", margen_extra_mensual: "col_extra",
  zona: "col_zona", clientes: "col_cliente", venta: "col_precio",
  potencial: "col_potencial", cliente_id: "col_cliente",
  cada_dias: "col_sin_comprar", dias_sin_comprar: "col_sin_comprar",
  venta_mensual_perdida: "col_perdido",
};

const MONETARIAS = new Set(["precio", "precio_oferta", "capital_inmovilizado",
                            "inversion", "venta_en_riesgo", "precio_sugerido",
                            "margen_extra_mensual", "venta", "potencial",
                            "venta_mensual_perdida"]);
const PORCENTUALES = new Set(["descuento_pct", "suba_pct"]);

function celda(col, valor) {
  if (valor === null || valor === undefined) return "—";
  if (MONETARIAS.has(col)) return money(valor);
  if (PORCENTUALES.has(col)) return `${valor}%`;
  if (typeof valor === "number") return num(valor);
  return String(valor);
}

// ── Carga de las tablas del módulo ───────────────────────────────────────────
function Cargar({ onListo }) {
  const [estado, setEstado] = useState(null);
  const esAdmin = (getSesion() || {}).rol === "admin";

  const subir = useCallback(async (tabla, archivo) => {
    if (!archivo) return;
    setEstado(`${tabla}…`);
    const cuerpo = new FormData();
    cuerpo.append("archivo", archivo);
    const ses = getSesion() || {};
    const r = await fetch(`/api/modulo/logistica/cargar/${tabla}`, {
      method: "POST", body: cuerpo,
      headers: { Authorization: `Bearer ${ses.token}` },
    });
    const d = await r.json().catch(() => ({}));
    setEstado(r.ok ? `${tabla}: ${d.filas} filas` : (d.detail || "error"));
    if (r.ok) onListo();
  }, [onListo]);

  if (!esAdmin) {
    return <div className="empty">{t("logistica.sin_datos")}</div>;
  }
  return (
    <div className="card" style={{ maxWidth: 620, margin: "40px auto" }}>
      <h3 style={{ marginTop: 0 }}>{t("logistica.sin_datos")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13.5 }}>{t("logistica.sin_datos_sub")}</p>
      {[["productos", "subir_productos"], ["ventas", "subir_ventas"],
        ["clientes", "subir_clientes"]].map(([tabla, clave]) => (
        <div key={tabla} style={{ marginTop: 12 }}>
          <label style={{ fontSize: 13, color: "var(--muted)" }}>{t(`logistica.${clave}`)}</label>
          <input type="file" accept=".csv,.xlsx,.xls" style={{ display: "block", marginTop: 4 }}
                 onChange={(e) => subir(tabla, e.target.files[0])} />
        </div>
      ))}
      {estado ? <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 12 }}>{estado}</p> : null}
    </div>
  );
}

export default function Logistica() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [sinPlan, setSinPlan] = useState(null);
  const [faltanDatos, setFaltanDatos] = useState(false);
  const [tab, setTab] = useState("ofertas");

  const cargar = useCallback(() => {
    setError(null); setFaltanDatos(false);
    api("/api/logistica/resumen")
      .then((d) => { setDatos(d); })
      .catch((e) => {
        const msg = String(e.message || e);
        if (esFaltaDePlan(e)) setSinPlan(msg);
        // Sin datos cargados todavía no es un error: es el primer día de uso.
        else if (msg.includes("cargaste") || msg.includes("Subila")) setFaltanDatos(true);
        else setError(msg);
      });
  }, []);

  useEffect(cargar, [cargar]);

  if (sinPlan) {
    return <ModuloNoIncluido modulo="logistica" detalle={sinPlan}
                             ventas={["venta_1", "venta_2", "venta_3", "venta_4"]} />;
  }
  if (faltanDatos) return <Cargar onListo={cargar} />;
  if (error) return <div className="empty">{error}</div>;
  if (!datos) return <div className="empty">{t("common.cargando")}</div>;

  const i = datos.indicadores;
  const activa = LISTAS.find((l) => l.clave === tab);
  const filas = datos[tab] || [];

  return (
    <>
      <h2 className="page-title">{t("logistica.titulo")}</h2>
      <p className="page-sub">{t("logistica.subtitulo")}</p>

      <div className="kpi-grid">
        <div className="card kpi">
          <div className="label">{t("logistica.kpi_venta")}</div>
          <div className="value tnum">{money(i.venta_periodo)}</div>
          <div className="delta">{t("logistica.kpi_margen")}: {i.margen_pct.toFixed(1)}%</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("logistica.kpi_stock")}</div>
          <div className="value tnum">{money(i.valor_stock)}</div>
        </div>
        <div className="card kpi" style={{ borderTop: `3px solid ${i.quiebres ? ROJO : VERDE}` }}>
          <div className="label">{t("logistica.kpi_quiebres")}</div>
          <div className="value tnum" style={{ color: i.quiebres ? ROJO : undefined }}>{i.quiebres}</div>
          <div className="delta">{t("logistica.kpi_bajo_minimo")}: {i.bajo_minimo}</div>
        </div>
        <div className="card kpi" style={{ borderTop: `3px solid ${i.sobrestock ? AMBAR : VERDE}` }}>
          <div className="label">{t("logistica.kpi_sobrestock")}</div>
          <div className="value tnum" style={{ color: i.sobrestock ? AMBAR : undefined }}>{i.sobrestock}</div>
        </div>
      </div>

      <div className="toolbar" style={{ marginTop: 16 }}>
        {LISTAS.map((l) => (
          <button key={l.clave}
                  className={`btn ${tab === l.clave ? "" : "ghost"}`}
                  onClick={() => setTab(l.clave)}>
            {t(`logistica.tab_${l.clave}`)} ({(datos[l.clave] || []).length})
          </button>
        ))}
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        {filas.length === 0 ? (
          <div className="empty">{t("logistica.nada_que_sugerir")}</div>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  {activa.cols.filter((c) => c in filas[0]).map((c) => (
                    <th key={c} style={{ textAlign: typeof filas[0][c] === "number" ? "right" : "left" }}>
                      {t(`logistica.${ETIQUETA[c] || "col_producto"}`)}
                    </th>
                  ))}
                  <th>{t("logistica.col_motivo")}</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f, n) => (
                  <tr key={n}>
                    {activa.cols.filter((c) => c in f).map((c) => (
                      <td key={c} className={typeof f[c] === "number" ? "tnum" : ""}
                          style={{ textAlign: typeof f[c] === "number" ? "right" : "left" }}>
                        {celda(c, f[c])}
                      </td>
                    ))}
                    <td style={{ color: "var(--muted)", fontSize: 12.5 }}>{f.motivo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
