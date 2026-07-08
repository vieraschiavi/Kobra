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
    throw new Error("Sesión vencida — iniciá sesión de nuevo.");
  }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.detail || `Error ${r.status}`);
  return datos;
}

export const fmtUYU = (n) =>
  "$U " + (n >= 1e6 ? (n / 1e6).toLocaleString("es-UY", { maximumFractionDigits: 1 }) + "M"
                    : Math.round(n).toLocaleString("es-UY"));
export const fmtPct = (x, d = 1) => (x * 100).toFixed(d) + "%";
// Estándar Bloque 8: montos completos con separador de miles, sin decimales.
export const fmtMonto = (n) => "$" + Math.round(n || 0).toLocaleString("es-UY");
