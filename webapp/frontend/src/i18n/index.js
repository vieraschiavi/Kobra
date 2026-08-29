// © 2026 Martín Viera. Todos los derechos reservados.

// Traducciones de la webapp: español, portugués brasileño e inglés.
// El idioma arranca en el del país del tenant (Brasil → portugués) pero se
// puede elegir aparte —el equipo que usa el programa no siempre habla el
// idioma del país donde se factura—; `getIdioma()` (../api.js) resuelve esa
// prioridad: elección explícita > país > castellano.
import es from "./es.json";
import ptBR from "./pt-BR.json";
import en from "./en.json";
import { getIdioma } from "../api.js";

const DICCIONARIOS = { es, pt: ptBR, en };

function buscar(dic, ruta) {
  return ruta.split(".").reduce((o, k) => (o == null ? o : o[k]), dic);
}

// t("dashboard.kpi.deudores") · t("originacion.drawer.pp_sufijo", {efecto_pp: 3.2})
export function t(clave, vars) {
  const idioma = getIdioma();
  let valor = buscar(DICCIONARIOS[idioma] || DICCIONARIOS.es, clave);
  if (valor == null) valor = buscar(DICCIONARIOS.es, clave);   // fallback si falta la clave
  if (valor == null) return clave;                              // último fallback: la clave misma
  if (vars) {
    for (const k of Object.keys(vars)) {
      valor = valor.replaceAll(`{{${k}}}`, vars[k]);
    }
  }
  return valor;
}
