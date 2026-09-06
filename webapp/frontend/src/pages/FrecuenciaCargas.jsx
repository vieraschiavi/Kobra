// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import { api, getIdioma } from "../api.js";
import { t } from "../i18n/index.js";

// Los miles con el separador del idioma elegido, no con el del navegador: el
// mismo programa mostrando "12,000" en una pantalla en castellano y "12.000"
// en la de al lado se lee como un error de datos.
const LOCALE = { es: "es-UY", pt: "pt-BR", en: "en-US" };
const miles = (n) => n.toLocaleString(LOCALE[getIdioma()] || LOCALE.es);

// ¿Está al día cada tabla que usa el programa?
//
// Un dashboard con datos viejos no se ve roto: se ve igual que uno correcto.
// La mora de ayer y la de hace tres semanas se dibujan con el mismo gráfico
// verde. Esta pantalla es la única que hace visible esa diferencia.
//
// Por eso el titular va arriba de todo y en grande: el 90% de las veces dice
// "todas al día" y con eso alcanza; el 10% restante es justo el día en que
// alguien iba a tomar una decisión sobre datos vencidos.

const COLOR = {
  al_dia: { pill: "alta", texto: "estado_al_dia" },
  atrasada: { pill: "media", texto: "estado_atrasada" },
  sin_datos: { pill: "baja", texto: "estado_sin_datos" },
};

function Tarjeta({ tabla }) {
  const c = COLOR[tabla.estado] || COLOR.sin_datos;
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "flex-start", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: "1.02rem" }}>{tabla.nombre}</h3>
        <span className={"pill " + c.pill}>{t(`frecuencia.${c.texto}`)}</span>
      </div>

      <p style={{ color: "var(--muted)", fontSize: 12.5, margin: "6px 0 10px" }}>
        {tabla.para_que}
      </p>

      {/* Fecha del DATO y fecha de CARGA, siempre las dos y separadas.
          Confundirlas es el error clásico: un proceso que corrió hoy a las
          6 AM pero trajo el cierre de hace tres días está "actualizado" y sus
          datos están viejos. */}
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr",
                    gap: "3px 10px", fontSize: 13 }}>
        <b>{t("frecuencia.fecha_dato")}:</b>
        <span className="tnum">{tabla.fecha_dato || "—"}</span>

        <b>{t("frecuencia.fecha_carga")}:</b>
        <span className="tnum">
          {tabla.carga || "—"}
          {tabla.dia_carga && ` (${tabla.dia_carga})`}
        </span>

        <b>{t("frecuencia.registros")}:</b>
        <span className="tnum">
          {tabla.filas != null ? miles(tabla.filas) : "—"}
        </span>

        {/* La cadencia esperada la manda el backend ya traducida (viaja por
            Accept-Language, como el resto del texto que genera el motor). */}
        <b>{t("frecuencia.esperada")}:</b>
        <span>{tabla.esperada}</span>
      </div>

      {tabla.motivo && (
        <p style={{ marginTop: 10, marginBottom: 0, fontSize: 12.5,
                    color: tabla.estado === "atrasada"
                      ? "var(--warn-deep, #7a4a1e)" : "var(--muted)" }}>
          {tabla.motivo}
        </p>
      )}
    </div>
  );
}

export default function FrecuenciaCargas() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");

  function cargar() {
    setError("");
    api("/api/frecuencia-cargas").then(setDatos).catch((e) => setError(e.message));
  }
  useEffect(cargar, []);

  const hayProblema = datos && (datos.resumen.atrasadas > 0 ||
                                datos.resumen.sin_datos > 0);

  return (
    <>
      <h1 className="page-title">{t("frecuencia.titulo")}</h1>
      <p className="page-sub">{t("frecuencia.subtitulo")}</p>

      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("frecuencia.cargando")}</div>}

      {datos && (
        <>
          {/* El titular ya redactado: es lo que se lee de un vistazo y lo que
              se copia en un mail cuando algo está mal. */}
          <div className="card" style={{ marginBottom: 16,
                borderLeft: `4px solid var(${hayProblema
                  ? "--warn, #d08a2a" : "--green-deep, #2e7d51"})` }}>
            <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "1.05rem", fontWeight: 600 }}>
                  {datos.titular}
                </div>
                <div style={{ color: "var(--muted)", fontSize: 12.5,
                              marginTop: 3 }}>
                  {t("frecuencia.actualizado", { cuando: datos.generado })}
                </div>
              </div>
              <button className="btn ghost" onClick={cargar}>
                ↻ {t("frecuencia.revisar")}
              </button>
            </div>
          </div>

          <div className="toolbar" style={{ gap: 14, fontSize: 13 }}>
            <span><b className="tnum">{datos.resumen.al_dia}</b>{" "}
              {t("frecuencia.res_al_dia")}</span>
            <span><b className="tnum">{datos.resumen.atrasadas}</b>{" "}
              {t("frecuencia.res_atrasadas")}</span>
            <span><b className="tnum">{datos.resumen.sin_datos}</b>{" "}
              {t("frecuencia.res_sin_datos")}</span>
          </div>

          {datos.tablas.map((tabla) => (
            <Tarjeta key={tabla.id} tabla={tabla} />
          ))}
        </>
      )}
    </>
  );
}
