// © 2026 Martín Viera. Todos los derechos reservados.
// Traducciones de la webapp (Fase 2 LATAM: español + portugués brasileño).
// El idioma no se elige aparte: viene del país del tenant (getPais().idioma,
// ver ../api.js) — Brasil es el único país de Fase 2 que usa "pt".
import es from "./es.json";
import ptBR from "./pt-BR.json";
import { getPais } from "../api.js";

const DICCIONARIOS = { es, pt: ptBR };

function buscar(dic, ruta) {
  return ruta.split(".").reduce((o, k) => (o == null ? o : o[k]), dic);
}

// t("dashboard.kpi.deudores") · t("originacion.drawer.pp_sufijo", {efecto_pp: 3.2})
export function t(clave, vars) {
  const idioma = getPais().idioma || "es";
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
