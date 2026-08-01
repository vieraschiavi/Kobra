// Freno por IP para las funciones serverless de Vercel (api/*.js).
//
// Es "mejor esfuerzo", no un límite distribuido: cada instancia de la función
// tiene su propia memoria, así que el freno real es "por IP y por instancia
// tibia", no "por IP en todo el fleet". Igual vale la pena — la mayoría del
// abuso real es un mismo cliente golpeando la misma instancia en ráfaga, y
// las instancias tibias de Vercel viven varios minutos entre invocaciones.
//
// Por qué no Edge Config: `api/copiloto.js` ya lo usa para un contador
// GLOBAL (cuántos análisis en total), pero Edge Config está pensado para
// lecturas frecuentes y escrituras esporádicas — escribir en cada request,
// que es lo que necesita un freno por IP de verdad, pega contra los límites
// de la API de administración de Vercel, no contra Edge Config en sí.
//
// Mismo cubo de fichas que `kobra/limitador.py`, reimplementado acá porque
// este archivo corre en el runtime de Node de Vercel, no en el backend Python.

const cubos = new Map(); // clave -> {fichas, visto}

function ipDe(req) {
  const xff = req.headers["x-forwarded-for"];
  if (xff) return String(xff).split(",")[0].trim();
  return req.headers["x-real-ip"] || (req.socket && req.socket.remoteAddress) || "desconocido";
}

function purgar(ahora, ventanaSeg) {
  for (const [k, b] of cubos) {
    if (ahora - b.visto > ventanaSeg * 2) cubos.delete(k);
  }
}

function permitir(clave, permitidos, ventanaSeg) {
  const ahora = Date.now() / 1000;
  if (cubos.size > 4096) purgar(ahora, ventanaSeg);
  const recargaSeg = ventanaSeg / permitidos;
  let b = cubos.get(clave) || { fichas: permitidos, visto: ahora };
  b = { fichas: Math.min(permitidos, b.fichas + (ahora - b.visto) / recargaSeg), visto: ahora };
  if (b.fichas < 1) {
    cubos.set(clave, b);
    return { ok: false, esperaSeg: Math.ceil((1 - b.fichas) * recargaSeg) + 1 };
  }
  b.fichas -= 1;
  cubos.set(clave, b);
  return { ok: true };
}

// Devuelve `true` si puede seguir. Si no, ya respondió el 429 — el caller
// solo tiene que hacer `return`.
function limitar(req, res, accion, permitidos, ventanaSeg) {
  const r = permitir(accion + ":" + ipDe(req), permitidos, ventanaSeg);
  if (!r.ok) {
    res.setHeader("Retry-After", String(r.esperaSeg));
    res.status(429).json({ error: "rate_limit", retry_after: r.esperaSeg });
    return false;
  }
  return true;
}

module.exports = { limitar, ipDe, permitir };
