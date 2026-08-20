// © 2026 Martín Viera. Todos los derechos reservados.

import React from "react";
import { t } from "../i18n/index.js";

/**
 * Pantalla de "tu plan no incluye este módulo".
 *
 * No es una pantalla de error: es el único momento en que el cliente ve qué se
 * está perdiendo, así que explica y ofrece en vez de disculparse. Por eso
 * recibe `ventas` — las razones concretas para comprarlo — y no solo un
 * mensaje genérico.
 *
 * Estaba copiada en cada pantalla de módulo. Con tres copias todavía se podía
 * discutir; con cinco, cambiar el link de precios o el texto obligaba a tocar
 * cinco archivos y olvidarse de uno era invisible hasta que un cliente lo veía.
 *
 * @param {string} modulo   Prefijo de las claves i18n (ej. "logistica" busca
 *                          `logistica.no_incluido_titulo`).
 * @param {string} detalle  Mensaje que devolvió la API, con el link de compra.
 * @param {string[]} ventas Claves i18n de los puntos de venta a listar.
 */
export default function ModuloNoIncluido({ modulo, detalle, ventas = [] }) {
  return (
    <div className="card" style={{ maxWidth: 640, margin: "40px auto", textAlign: "center" }}>
      <h3 style={{ marginTop: 0 }}>{t(`${modulo}.no_incluido_titulo`)}</h3>
      <p style={{ color: "var(--muted)", fontSize: 14 }}>{t(`${modulo}.no_incluido_sub`)}</p>
      {ventas.length > 0 && (
        <ul style={{ textAlign: "left", color: "var(--muted)", fontSize: 13.5, lineHeight: 1.9 }}>
          {ventas.map((clave) => <li key={clave}>{t(`${modulo}.${clave}`)}</li>)}
        </ul>
      )}
      {detalle ? <p style={{ color: "var(--faint)", fontSize: 12 }}>{detalle}</p> : null}
      <a className="btn" href="https://mvkobranzaia.com/#precios"
         target="_blank" rel="noreferrer">{t(`${modulo}.ver_planes`)}</a>
    </div>
  );
}

/**
 * ¿Este error es "no lo tenés en el plan" o algo realmente roto?
 *
 * El backend responde 403 con el link de compra en el mensaje. Distinguirlo
 * importa: uno es una oportunidad de venta y el otro es un problema que hay
 * que reportar, y mostrarlos igual convierte cada upsell en "el programa falla".
 */
export function esFaltaDePlan(e) {
  const msg = String(e?.message || e || "");
  return msg.includes("mvkobranzaia.com") || msg.toLowerCase().includes("no incluye");
}
