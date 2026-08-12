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
  if (!r.ok) throw new Error(datos.detail || `Error ${r.status}`);
  return datos;
}

// Los endpoints que consumen cupo (Agente IA, análisis de voz, evaluación de
// audios) devuelven el estado del plan ya actualizado. Esto lo levanta a la
// barra lateral sin que la pantalla tenga que conocer al chip ni volver a
// preguntarle al backend por algo que acaba de contestar.
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
