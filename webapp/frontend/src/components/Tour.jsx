// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useState } from "react";
import { t } from "../i18n/index.js";

const CLAVES_PASOS = ["paso1", "paso2", "paso3", "paso4"];

export default function Tour() {
  const [paso, setPaso] = useState(
    localStorage.getItem("kobra_tour_visto") ? -1 : 0);
  if (paso < 0) return null;

  const cerrar = () => { localStorage.setItem("kobra_tour_visto", "1"); setPaso(-1); };
  const clave = CLAVES_PASOS[paso];

  return (
    <div className="tour-backdrop">
      <div className="card tour-card">
        <h2>{t(`tour.${clave}.titulo`)}</h2>
        <p>{t(`tour.${clave}.texto`)}</p>
        <div className="tour-dots">
          {CLAVES_PASOS.map((_, i) => <i key={i} className={i === paso ? "on" : ""} />)}
        </div>
        <div className="tour-actions">
          <button className="btn ghost" onClick={cerrar}>{t("tour.boton_saltar")}</button>
          {paso < CLAVES_PASOS.length - 1
            ? <button className="btn" onClick={() => setPaso(paso + 1)}>{t("tour.boton_siguiente")}</button>
            : <button className="btn" onClick={cerrar}>{t("tour.boton_empezar")}</button>}
        </div>
      </div>
    </div>
  );
}
