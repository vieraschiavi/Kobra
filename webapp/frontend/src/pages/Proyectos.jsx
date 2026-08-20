// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useCallback, useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, getSesion } from "../api.js";
import { t } from "../i18n/index.js";
import ModuloNoIncluido, { esFaltaDePlan } from "../components/ModuloNoIncluido.jsx";

const VERDE = "#00c896";
const AMBAR = "#f2b441";
const ROJO = "#ff7675";

const DIMENSIONES = ["alcance", "cronograma", "presupuesto", "riesgo",
                     "dependencias", "equipo"];

// El color del semáforo, y siempre acompañado del texto del estado: quien no
// distingue los matices tiene que poder leerlo igual (WCAG 1.4.1).
const COLOR_ESTADO = { riesgo: ROJO, observacion: AMBAR, saludable: VERDE };

const estiloTooltip = {
  background: "#0e1628", border: "1px solid #24344f",
  borderRadius: 8, color: "#eaf1fb",
};

function Cargar({ onListo }) {
  const [estado, setEstado] = useState(null);
  const esAdmin = (getSesion() || {}).rol === "admin";

  const subir = useCallback(async (tabla, archivo) => {
    if (!archivo) return;
    setEstado(`${tabla}…`);
    const cuerpo = new FormData();
    cuerpo.append("archivo", archivo);
    const ses = getSesion() || {};
    const r = await fetch(`/api/modulo/proyectos/cargar/${tabla}`, {
      method: "POST", body: cuerpo,
      headers: { Authorization: `Bearer ${ses.token}` },
    });
    const d = await r.json().catch(() => ({}));
    setEstado(r.ok ? `${tabla}: ${d.filas} filas` : (d.detail || "error"));
    if (r.ok) onListo();
  }, [onListo]);

  if (!esAdmin) return <div className="empty">{t("proyectos.sin_datos")}</div>;
  return (
    <div className="card" style={{ maxWidth: 620, margin: "40px auto" }}>
      <h3 style={{ marginTop: 0 }}>{t("proyectos.sin_datos")}</h3>
      <p style={{ color: "var(--muted)", fontSize: 13.5 }}>{t("proyectos.sin_datos_sub")}</p>
      {[["proyectos", "subir_proyectos"], ["tareas", "subir_tareas"],
        ["equipo", "subir_equipo"]].map(([tabla, clave]) => (
        <div key={tabla} style={{ marginTop: 12 }}>
          <label style={{ fontSize: 13, color: "var(--muted)" }}>{t(`proyectos.${clave}`)}</label>
          <input type="file" accept=".csv,.xlsx,.xls" style={{ display: "block", marginTop: 4 }}
                 onChange={(e) => subir(tabla, e.target.files[0])} />
        </div>
      ))}
      {estado ? <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 12 }}>{estado}</p> : null}
    </div>
  );
}

export default function Proyectos() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [sinPlan, setSinPlan] = useState(null);
  const [faltanDatos, setFaltanDatos] = useState(false);
  const [foco, setFoco] = useState(null);

  const cargar = useCallback(() => {
    setError(null); setFaltanDatos(false);
    api("/api/proyectos/resumen")
      .then(setDatos)
      .catch((e) => {
        const msg = String(e.message || e);
        if (esFaltaDePlan(e)) setSinPlan(msg);
        else if (msg.includes("cargaste") || msg.includes("Subila")) setFaltanDatos(true);
        else setError(msg);
      });
  }, []);

  useEffect(cargar, [cargar]);

  if (sinPlan) {
    return <ModuloNoIncluido modulo="proyectos" detalle={sinPlan}
                             ventas={["venta_1", "venta_2", "venta_3", "venta_4"]} />;
  }
  if (faltanDatos) return <Cargar onListo={cargar} />;
  if (error) return <div className="empty">{error}</div>;
  if (!datos) return <div className="empty">{t("common.cargando")}</div>;

  const elegido = foco
    ? datos.salud.find((p) => p.proyecto_id === foco)
    : datos.salud[0];
  const radar = elegido
    ? DIMENSIONES.map((d) => ({ dim: t(`proyectos.dim.${d}`), valor: elegido[`dim_${d}`] }))
    : [];

  return (
    <>
      <h2 className="page-title">{t("proyectos.titulo")}</h2>
      <p className="page-sub">{t("proyectos.subtitulo")}</p>

      <div className="kpi-grid">
        <div className="card kpi" style={{
          borderTop: `3px solid ${datos.indice_general >= 75 ? VERDE
                                  : datos.indice_general >= 55 ? AMBAR : ROJO}` }}>
          <div className="label">{t("proyectos.kpi_indice")}</div>
          <div className="value tnum">{datos.indice_general}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("proyectos.kpi_proyectos")}</div>
          <div className="value tnum">{datos.proyectos}</div>
        </div>
        <div className="card kpi" style={{ borderTop: `3px solid ${datos.en_riesgo ? ROJO : VERDE}` }}>
          <div className="label">{t("proyectos.kpi_riesgo")}</div>
          <div className="value tnum" style={{ color: datos.en_riesgo ? ROJO : undefined }}>
            {datos.en_riesgo}
          </div>
          <div className="delta">{t("proyectos.kpi_observacion")}: {datos.en_observacion}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("proyectos.kpi_pendientes")}</div>
          <div className="value tnum">{datos.tareas_pendientes}</div>
        </div>
      </div>

      <div className="charts-grid" style={{ marginTop: 16 }}>
        {/* Salud por proyecto */}
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("proyectos.salud_titulo")}</h3>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("proyectos.salud_sub")}</p>
          <div className="tablewrap" style={{ maxHeight: 300, overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>{t("proyectos.col_proyecto")}</th>
                  <th style={{ textAlign: "right" }}>{t("proyectos.col_indice")}</th>
                  <th>{t("proyectos.col_estado")}</th>
                </tr>
              </thead>
              <tbody>
                {datos.salud.map((p) => (
                  <tr key={p.proyecto_id}
                      onClick={() => setFoco(p.proyecto_id)}
                      style={{ cursor: "pointer",
                               background: (elegido && p.proyecto_id === elegido.proyecto_id)
                                 ? "var(--navy-800)" : undefined }}>
                    <td>{p.nombre}</td>
                    <td className="tnum" style={{ textAlign: "right" }}>{p.indice}</td>
                    <td>
                      <span className="pill" style={{ borderColor: COLOR_ESTADO[p.estado],
                                                      color: COLOR_ESTADO[p.estado] }}>
                        {t(`proyectos.estado.${p.estado}`)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Desglose del proyecto elegido */}
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{elegido ? elegido.nombre : ""}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={radar} layout="vertical" margin={{ left: 20, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
              <XAxis type="number" domain={[0, 100]} tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <YAxis type="category" dataKey="dim" width={110}
                     tick={{ fill: "#93a5c0", fontSize: 11 }} />
              <Tooltip contentStyle={estiloTooltip} />
              <Bar dataKey="valor" radius={[0, 3, 3, 0]}>
                {radar.map((d, n) => (
                  <Cell key={n} fill={d.valor >= 75 ? VERDE : d.valor >= 55 ? AMBAR : ROJO} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Backlog */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("proyectos.backlog_titulo")}</h3>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("proyectos.backlog_sub")}</p>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>{t("proyectos.col_tarea")}</th>
                <th>{t("proyectos.col_responsable")}</th>
                <th style={{ textAlign: "right" }}>{t("proyectos.col_valor")}</th>
                <th style={{ textAlign: "right" }}>{t("proyectos.col_impactadas")}</th>
                <th style={{ textAlign: "right" }}>{t("proyectos.col_dias")}</th>
              </tr>
            </thead>
            <tbody>
              {datos.backlog.map((tarea, n) => (
                <tr key={n}>
                  <td>{tarea.titulo || tarea.tarea_id}</td>
                  <td>{tarea.responsable || "—"}</td>
                  <td className="tnum" style={{ textAlign: "right" }}>{tarea.valor_esperado}</td>
                  <td className="tnum" style={{ textAlign: "right" }}>{tarea.tareas_impactadas}</td>
                  <td className="tnum" style={{ textAlign: "right",
                                                color: tarea.dias_restantes < 0 ? ROJO : undefined }}>
                    {tarea.dias_restantes < 0
                      ? t("proyectos.vencida")
                      : tarea.dias_restantes}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
