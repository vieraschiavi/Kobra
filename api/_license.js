// Firma y verificación de licencias MV Kobra AI.
// Prefijo "_" para que Vercel NO la trate como endpoint — es un módulo interno.
//
// FORMATO: JWT HS256, el MISMO que valida la aplicación instalada
// (`backend_venta/licencias.py::validar_licencia`, vía PyJWT).
//
// Antes este módulo emitía un formato propio ("KOBRA1.<body>.<sig>") que la app
// era incapaz de aceptar: distinto formato, distinto secreto y distinta forma de
// payload. Un cliente pagaba, pegaba su licencia y recibía "Licencia inválida".
// Nada en el repo consumía ese formato salvo su propio test. Por eso el cambio es
// una corrección, no una migración: no hay licencias KOBRA1 emitidas a nadie.
//
// Las tres cosas que tienen que coincidir con el lado Python, y por qué:
//   1. Formato  — PyJWT espera header.payload.firma, no un prefijo literal.
//   2. Secreto  — Python lee KOBRA_LICENSE_SECRET; acá se prioriza ese nombre y
//                 se acepta LICENSE_SECRET como alias para no romper el deploy
//                 actual de Vercel, que ya tiene esa variable cargada.
//   3. Payload  — Python espera {sub, plan, edition, cupo_mensual, features,
//                 iat, exp}. Un JWT bien firmado pero con otras claves pasa la
//                 validación y después rompe en el gateway, que es peor.

const crypto = require("crypto");

// Espejo de backend_venta/licencias.py::PLANES. Si cambia allá, cambia acá:
// `tests/test_paridad_planes.py` falla si se desincronizan.
// Firma y verificación de licencias MV Kobra AI (JWT HS256, sin dependencias externas).
// Prefijo "_" para que Vercel NO la trate como endpoint — es un módulo interno.
//
// POR QUÉ JWT Y NO UN FORMATO PROPIO
// ----------------------------------
// Este módulo emite la licencia que recibe quien PAGA; quien la valida es la
// app instalada, en Python (`backend_venta/licencias.py`, PyJWT HS256). Hasta
// la v1.3.3 acá se firmaba un formato propio `KOBRA1.<payload>.<firma>` que
// PyJWT no puede leer: el cliente pagaba, pegaba su licencia y la app le decía
// "Licencia inválida". El puente estaba cortado en tres puntos a la vez:
//
//   1. formato   — `KOBRA1.…` no es un JWT (el 1er segmento de un JWT es el
//                  header codificado, no una etiqueta de versión);
//   2. claims    — el payload no llevaba `exp`, y la app hace `claims["exp"]`
//                  para calcular los días restantes (KeyError → 500);
//   3. secreto   — Vercel expone `LICENSE_SECRET` y la app lee
//                  `KOBRA_LICENSE_SECRET`.
//
// Los tres se arreglan acá: se emite un JWT HS256 estándar, con el MISMO juego
// de claims que `licencias.emitir_licencia`, y `verify` acepta cualquiera de
// los dos nombres de variable. `tests/test_puente_licencia.py` cruza los dos
// lenguajes de verdad (firma con Node, valida con PyJWT) para que esto no se
// vuelva a romper en silencio.

const crypto = require("crypto");

// Espejo de `PLANES` en backend_venta/licencias.py. La app confía en estos
// valores para el cupo y las features del cliente que pagó, así que no pueden
// divergir: `tests/test_puente_licencia.py::test_las_tablas_de_planes_no_divergen`
// falla si alguien toca una de las dos tablas y se olvida de la otra.
const PLANES = {
  trial:      { cupo_mensual: 50,   dias: 3,   features: ["voz", "whatsapp", "copiloto", "erp"] },
  basico:     { cupo_mensual: 300,  dias: 30,  features: ["voz", "whatsapp", "copiloto", "erp"] },
  starter:    { cupo_mensual: 200,  dias: 365, features: ["voz", "whatsapp", "copiloto", "erp"] },
  pro:        { cupo_mensual: 1000, dias: 30,  features: ["voz", "whatsapp", "copiloto", "erp", "excedente"] },
  enterprise: { cupo_mensual: null, dias: 30,  features: ["voz", "whatsapp", "copiloto", "erp", "excedente", "white_label", "sso"] },
};

function b64u(buf) {
  return Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64uJson(obj) { return b64u(JSON.stringify(obj)); }
function fromB64u(s) {
  return Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
}

/** Secreto activo. Prioriza el nombre que usa la app instalada. */
function secretoActivo() {
  return process.env.KOBRA_LICENSE_SECRET || process.env.LICENSE_SECRET || null;
}

function firmar(headerB64, payloadB64, secret) {
  return b64u(crypto.createHmac("sha256", secret).update(headerB64 + "." + payloadB64).digest());
}

/**
 * Emite una licencia JWT HS256 con la forma que espera la app.
 *
 * @param {object} datos           - { plan, email|sub, pid, edition?, dias?, cupo_mensual?, features? }
 * @param {string} secret          - secreto HS256 compartido con la app
 * @returns {string} JWT
 */
function sign(datos, secret) {
  const plan = datos.plan;
  if (!PLANES[plan]) {
    throw new Error("plan desconocido: " + JSON.stringify(plan) + " (válidos: " + Object.keys(PLANES).join(", ") + ")");
  }
  const cfg = PLANES[plan];
  const ahora = Math.floor(Date.now() / 1000);
  const dias = datos.dias != null ? datos.dias : cfg.dias;

  const payload = {
    // `sub` identifica al cliente: el email del pagador, y si no vino, el id de
    // pago — que siempre existe y es único, así una licencia nunca sale sin dueño.
    sub: datos.sub || datos.email || ("pago:" + datos.pid),
    plan: plan,
    edition: datos.edition || "venta",
    cupo_mensual: datos.cupo_mensual !== undefined ? datos.cupo_mensual : cfg.cupo_mensual,
    features: datos.features || cfg.features,
    iat: ahora,
    exp: ahora + dias * 24 * 3600,
  };
  // `pid` no va en el payload que valida PyJWT como claim estándar, pero se
  // conserva para poder rastrear qué pago originó cada licencia en soporte.
  if (datos.pid) payload.pid = String(datos.pid);

  const headerB64 = b64uJson({ alg: "HS256", typ: "JWT" });
  const payloadB64 = b64uJson(payload);
  return headerB64 + "." + payloadB64 + "." + firmar(headerB64, payloadB64, secret);
}

/**
 * Verifica una licencia y devuelve sus claims, o null si es inválida/expirada.
 * Equivalente en JS de `licencias.validar_licencia`.
 */
const HEADER = { alg: "HS256", typ: "JWT" };

function b64u(buf) { return Buffer.from(buf).toString("base64url"); }
function b64uJson(obj) { return b64u(JSON.stringify(obj)); }
function hmac(data, secret) {
  return crypto.createHmac("sha256", secret).update(data).digest("base64url");
}

/** Firma un JWT HS256. `payload` va tal cual — quien arma los claims de una
 *  licencia de venta es `emitirLicencia`. */
function sign(payload, secret) {
  const body = b64uJson(HEADER) + "." + b64uJson(payload);
  return body + "." + hmac(body, secret);
}

/** Verifica y devuelve los claims, o `null` si el token no es de fiar.
 *  Nunca lanza: quien llama distingue por `null`, no por excepción. */
function verify(license, secret) {
  if (typeof license !== "string" || !secret) return null;
  const parts = license.split(".");
  if (parts.length !== 3) return null;
  const [headerB64, payloadB64, sig] = parts;

  let header;
  try { header = JSON.parse(fromB64u(headerB64)); } catch (e) { return null; }
  if (!header || header.alg !== "HS256") return null;

  const esperada = firmar(headerB64, payloadB64, secret);
  const a = Buffer.from(sig), b = Buffer.from(esperada);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;

  let claims;
  try { claims = JSON.parse(fromB64u(payloadB64)); } catch (e) { return null; }
  // Vencimiento: mismo criterio que PyJWT, que rechaza exp pasado por defecto.
  if (claims && typeof claims.exp === "number" && claims.exp < Math.floor(Date.now() / 1000)) return null;
  return claims;
}

module.exports = { sign, verify, secretoActivo, PLANES };
  const [h, p, sig] = parts;

  const esperada = hmac(h + "." + p, secret);
  const a = Buffer.from(sig), b = Buffer.from(esperada);
  // El chequeo de largo va ANTES: `timingSafeEqual` tira si difieren.
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;

  try {
    // `alg: none` es el ataque clásico contra JWT: un token sin firma que
    // algunos verificadores aceptan. Acá la firma ya se validó, pero igual se
    // exige HS256 explícito para no depender de eso.
    const header = JSON.parse(Buffer.from(h, "base64url").toString("utf8"));
    if (!header || header.alg !== "HS256") return null;
    return JSON.parse(Buffer.from(p, "base64url").toString("utf8"));
  } catch (e) { return null; }
}

/**
 * Arma y firma la licencia de una compra, con el mismo juego de claims que
 * `backend_venta/licencias.py::emitir_licencia` — que es lo que la app espera
 * encontrar al activar (`sub`, `plan`, `edition`, `cupo_mensual`, `features`,
 * `iat`, `exp`).
 *
 * Devuelve `null` si el plan no existe: es preferible no entregar licencia a
 * entregar una que la app va a rechazar después, delante del cliente.
 */
function emitirLicencia({ plan, pid, email }, secret, ahora) {
  const cfg = PLANES[plan];
  if (!cfg) return null;
  const iat = Number.isFinite(ahora) ? ahora : Math.floor(Date.now() / 1000);
  return sign({
    sub: email || (pid ? "mp:" + pid : "desconocido"),
    plan: plan,
    edition: "venta",
    cupo_mensual: cfg.cupo_mensual,
    features: cfg.features,
    pid: pid || null,
    email: email || null,
    iat: iat,
    exp: iat + cfg.dias * 24 * 3600,
  }, secret);
}

/** El secreto de firma, con los DOS nombres en uso: `LICENSE_SECRET` es el que
 *  está cargado en Vercel y `KOBRA_LICENSE_SECRET` el que lee la app. Tienen
 *  que valer lo mismo; aceptar ambos evita que la venta dependa de cuál se
 *  configuró. */
function secretoLicencia(env) {
  const e = env || process.env;
  return e.LICENSE_SECRET || e.KOBRA_LICENSE_SECRET || null;
}

module.exports = { sign, verify, emitirLicencia, secretoLicencia, PLANES };
