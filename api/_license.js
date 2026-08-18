// © 2026 Martín Viera. Todos los derechos reservados.

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
// `tests/test_licencia_puente.py` falla si se desincronizan.
const PLANES = {
  trial:      { cupo_mensual: 50,   dias: 3,   features: ["voz", "whatsapp", "copiloto", "erp"] },
  basico:     { cupo_mensual: 300,  dias: 30,  features: ["voz", "whatsapp", "copiloto", "erp"] },
  // Sin tope a propósito: el consumo lo paga el cliente con sus propias APIs
  // (ver el comentario largo en backend_venta/licencias.py::PLANES).
  starter:    { cupo_mensual: null, dias: 365, features: ["voz", "whatsapp", "copiloto", "erp"] },
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

/** Clave privada de firma (PEM). Solo existe en el servidor de ventas. */
function clavePrivada() {
  const k = process.env.KOBRA_LICENSE_PRIVATE_KEY;
  // Vercel guarda los saltos de línea como `\n` literales en algunas
  // interfaces de carga; sin desescaparlos, el PEM no parsea y la firma
  // explota justo en el peor momento: cuando alguien acaba de pagar.
  return k ? k.replace(/\\n/g, "\n") : null;
}

function firmarRS256(headerB64, payloadB64, privada) {
  return b64u(crypto.createSign("RSA-SHA256")
    .update(headerB64 + "." + payloadB64)
    .sign(privada));
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

  // RS256 si hay clave privada; si no, el HS256 de siempre.
  //
  // Por qué se prefiere la asimétrica: con HS256 la clave que VERIFICA es la
  // misma que FIRMA, así que la copia instalada necesitaba el secreto del
  // servidor para validar. Nunca lo recibía —el instalador de clientes se arma
  // sin `edicion.json`—, cada máquina se generaba uno al azar, y una licencia
  // comprada moría con "Signature verification failed". Repartir el secreto
  // dentro del .exe lo arreglaba y abría otro agujero: quien lo extrajera se
  // emitía las licencias que quisiera.
  //
  // Con RS256 la privada vive solo acá y la pública viaja en el programa
  // (backend_venta/licencia_clave.py). Publicarla no habilita nada.
  const privada = clavePrivada();
  if (privada) {
    const headerB64 = b64uJson({ alg: "RS256", typ: "JWT" });
    const payloadB64 = b64uJson(payload);
    return headerB64 + "." + payloadB64 + "." + firmarRS256(headerB64, payloadB64, privada);
  }
  const headerB64 = b64uJson({ alg: "HS256", typ: "JWT" });
  const payloadB64 = b64uJson(payload);
  return headerB64 + "." + payloadB64 + "." + firmar(headerB64, payloadB64, secret);
}

/**
 * Verifica una licencia y devuelve sus claims, o null si es inválida/expirada.
 * Equivalente en JS de `licencias.validar_licencia`.
 */
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
