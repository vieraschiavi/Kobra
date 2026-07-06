// Firma y verificación de licencias MV Kobra AI (HMAC-SHA256, sin dependencias externas).
// Prefijo "_" para que Vercel NO la trate como endpoint — es un módulo interno.

const crypto = require("crypto");

function b64u(buf) {
  return Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64uJson(obj) { return b64u(JSON.stringify(obj)); }

function sign(payload, secret) {
  const body = b64uJson(payload);
  const sig = b64u(crypto.createHmac("sha256", secret).update(body).digest());
  return "KOBRA1." + body + "." + sig;
}

function verify(license, secret) {
  if (typeof license !== "string") return null;
  const parts = license.split(".");
  if (parts.length !== 3 || parts[0] !== "KOBRA1") return null;
  const body = parts[1], sig = parts[2];
  const expected = b64u(crypto.createHmac("sha256", secret).update(body).digest());
  const a = Buffer.from(sig), b = Buffer.from(expected);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  try {
    const json = Buffer.from(body.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
    return JSON.parse(json);
  } catch (e) { return null; }
}

module.exports = { sign, verify };
