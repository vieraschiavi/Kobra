// MV Kobra AI · Escritorio — manejo de licencia local
//
// La build "owner" nunca guarda ni pide nada: siempre corre con acceso
// completo. La build "cliente" persiste la licencia activada (el JWT que
// ya emite backend_venta/licencias.py al confirmarse el pago) en el
// perfil de usuario del sistema operativo, y arranca en modo demo hasta
// que haya una licencia válida guardada.

const fs = require("fs");
const path = require("path");

const OWNER_CLAIMS = {
  sub: "owner",
  plan: "enterprise",
  edition: "owner",
  cupo_mensual: null,
  features: ["voz", "whatsapp", "copiloto", "erp", "excedente", "white_label", "sso"],
};

function archivoLicencia(app) {
  return path.join(app.getPath("userData"), "licencia.json");
}

function esOwner(app) {
  try {
    const cfgPath = app.isPackaged
      ? path.join(process.resourcesPath, "build-config.json")
      : path.join(__dirname, "build-config.dev.json");
    return require(cfgPath).edition === "owner";
  } catch {
    return false;
  }
}

function leerLicencia(app) {
  if (esOwner(app)) {
    return { ok: true, modo: "owner", claims: OWNER_CLAIMS };
  }
  const f = archivoLicencia(app);
  if (!fs.existsSync(f)) {
    return { ok: false, modo: "demo" };
  }
  try {
    const data = JSON.parse(fs.readFileSync(f, "utf-8"));
    const vencida = data.claims && data.claims.exp && data.claims.exp * 1000 < Date.now();
    if (vencida) return { ok: false, modo: "demo", vencida: true };
    return { ok: true, modo: "cliente", claims: data.claims, token: data.token };
  } catch {
    return { ok: false, modo: "demo" };
  }
}

function guardarLicencia(app, { token, claims }) {
  const f = archivoLicencia(app);
  fs.writeFileSync(f, JSON.stringify({ token, claims }, null, 2), { mode: 0o600 });
  return { ok: true };
}

module.exports = { leerLicencia, guardarLicencia, esOwner };
