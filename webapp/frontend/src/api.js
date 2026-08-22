// © 2026 Martín Viera. Todos los derechos reservados.

// Cliente HTTP mínimo con token JWT en memoria + localStorage.
const KEY = "kobra_token";

export function getSesion() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; }
  catch { return null; }
}
export function setSesion(s) {
  if (s) localStorage.setItem(KEY, JSON.stringify(s));
  else localStorage.removeItem(KEY);
}

export async function api(ruta, { metodo = "GET", cuerpo } = {}) {
  const ses = getSesion();
  const r = await fetch(ruta, {
    method: metodo,
    headers: {
      ...(cuerpo ? { "content-type": "application/json" } : {}),
      ...(ses ? { Authorization: `Bearer ${ses.token}` } : {}),
    },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  if (r.status === 401 && ruta !== "/api/auth/login") {
    setSesion(null);
    window.location.hash = "#/login";
    // Nota: no importa ./i18n/index.js acá (ese módulo importa getPais de
    // este mismo archivo — evitamos el ciclo con un mensaje mínimo inline).
    const idioma = getPais().idioma || "es";
    throw new Error(idioma === "pt"
      ? "Sessão expirada — faça login novamente."
      : "Sesión vencida — iniciá sesión de nuevo.");
  }
  const datos = await r.json().catch(() => ({}));
  // Antes del throw, no después: cuando el cupo se acaba de agotar (402), la
  // MISMA respuesta que rechaza la gestión también trae el plan actualizado
  // (`bloqueado: true`) — justo el momento en que el chip de la barra
  // lateral más necesita refrescarse. Si esto fuera después del `throw`,
  // nunca se ejecutaría en ese caso.
  avisarPlan(datos);
  if (!r.ok) throw new Error(datos.detail || `Error ${r.status}`);
  return datos;
}

/**
 * Descarga un archivo del backend (Excel, CSV, PDF) y se lo da al navegador.
 *
 * Los cuatro exports hacían `await r.blob()` sin mirar `r.ok`. Cuando el
 * backend contesta un error —401 con la sesión vencida, 403 por plan, 402 por
 * cupo, 500 porque falló el armado del Excel— el cuerpo es un JSON de tres
 * líneas, y ese JSON se descargaba igual con nombre `..._Promesas_Vencidas.xlsx`.
 * El cliente terminaba con un archivo que Excel no abre y ningún mensaje: la
 * peor forma de fallar, porque parece que anduvo.
 *
 * Acá se mira la respuesta primero. Y como es un archivo, el error hay que
 * leerlo del cuerpo antes de tirarlo — si no, el mensaje que el backend se
 * tomó el trabajo de escribir se pierde.
 */
export async function descargar(ruta, nombreArchivo) {
  const ses = getSesion();
  const r = await fetch(ruta, {
    headers: ses ? { Authorization: `Bearer ${ses.token}` } : {},
  });

  if (!r.ok) {
    // El cuerpo de un error es JSON aunque la ruta prometa un .xlsx.
    const datos = await r.json().catch(() => ({}));
    avisarPlan(datos);
    if (r.status === 401) {
      setSesion(null);
      window.location.hash = "#/login";
      const idioma = getPais().idioma || "es";
      throw new Error(idioma === "pt"
        ? "Sessão expirada — faça login novamente."
        : "Sesión vencida — iniciá sesión de nuevo.");
    }
    throw new Error(datos.detail || `No se pudo generar el archivo (${r.status}).`);
  }

  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(a.href);
}

// Los endpoints que consumen cupo (Agente IA, análisis de voz, evaluación de
// audios) devuelven el estado del plan ya actualizado, tanto si salieron bien
// como si el cupo se acaba de agotar. `api()` ya lo llama solo; los dos
// endpoints que suben archivos usan `fetch` crudo (FormData) en vez de
// `api()` y tienen que llamarlo a mano — VER de hacerlo antes de cualquier
// `throw` sobre una respuesta no-ok, con el mismo cuidado que acá arriba.
export function avisarPlan(respuesta) {
  if (respuesta && respuesta.plan) {
    window.dispatchEvent(new CustomEvent("kobra:plan", { detail: respuesta.plan }));
  }
  return respuesta;
}

// País del tenant (LATAM) — cambia el símbolo/locale de formateo de moneda
// en toda la webapp, y (Fase 2, Brasil) también el idioma de la interfaz
// vía el diccionario en ./i18n.
const PAIS_KEY = "kobra_pais";
const PAIS_UY = { codigo: "UY", nombre: "Uruguay", moneda: "UYU", simbolo: "$U",
                  locale: "es-UY", idioma: "es" };
let _pais = null;

export function getPais() {
  if (_pais) return _pais;
  try { _pais = JSON.parse(localStorage.getItem(PAIS_KEY)); } catch { _pais = null; }
  // idioma es nuevo (Fase 2): un país cacheado de antes de este cambio no lo
  // tiene — asumí español, que era el único idioma hasta ahora.
  return _pais ? { idioma: "es", ..._pais } : PAIS_UY;
}
export function setPaisCache(p) {
  _pais = p || null;
  if (p) localStorage.setItem(PAIS_KEY, JSON.stringify(p));
  else localStorage.removeItem(PAIS_KEY);
}
export async function cargarPais() {
  const p = await api("/api/tenant/pais");
  setPaisCache(p);
  return p;
}

export const fmtUYU = (n) => {
  const p = getPais();
  return p.simbolo + " " + (n >= 1e6 ? (n / 1e6).toLocaleString(p.locale, { maximumFractionDigits: 1 }) + "M"
                    : Math.round(n).toLocaleString(p.locale));
};
export const fmtPct = (x, d = 1) => (x * 100).toFixed(d) + "%";
// Estándar Bloque 8: montos completos con separador de miles, sin decimales.
export const fmtMonto = (n) => {
  const p = getPais();
  return p.simbolo + Math.round(n || 0).toLocaleString(p.locale);
};
