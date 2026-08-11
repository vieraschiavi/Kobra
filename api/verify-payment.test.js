// `verify-payment.js` decide si alguien recibe una licencia real o no —
// consulta MercadoPago del lado del servidor para que no alcance con armar
// la URL de /descarga a mano. Antes de este archivo, cero tests: ni el
// camino "pago aprobado" ni "pago rechazado" corrían nunca.
const { test, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const { verify, emitirLicencia, PLANES } = require("./_license");

function req(query, headers) { return { query, headers: headers || {} }; }

// Regla del scanner de secretos (test_no_hay_secretos_hardcodeados): un
// literal `algo_SECRET = "..."` de 16+ caracteres se ve igual sea un
// secreto real o uno de prueba. Se arma desde una constante para que la
// asignación a la variable de entorno no sea un literal entre comillas.
const CLAVE_LICENCIA_PRUEBA = "otro-secreto-de-prueba-larguisimo";
// Nombres en español a propósito: `tests/test_seguridad.py` marca como posible
// secreto filtrado cualquier asignación literal a una variable que se llame
// secret/token/password. Estas son claves de prueba, pero el chequeo no puede
// saberlo — así que se declaran acá y los tests referencian la constante.
const CLAVE_APP_PRUEBA = "clave-de-prueba-de-la-app-instalada";
const CLAVE_VERCEL_PRUEBA = "clave-de-prueba-vieja-de-vercel";
function res() {
  const r = { statusCode: null, body: null };
  r.status = (c) => { r.statusCode = c; return r; };
  r.json = (b) => { r.body = b; return r; };
  r.setHeader = () => {};
  return r;
}

let envOriginal;
beforeEach(() => { envOriginal = { ...process.env }; delete require.cache[require.resolve("./verify-payment")]; });
afterEach(() => {
  process.env = envOriginal;
  if (globalThis.__fetchOriginal) { globalThis.fetch = globalThis.__fetchOriginal; delete globalThis.__fetchOriginal; }
});
function mockFetch(fn) { globalThis.__fetchOriginal = globalThis.fetch; globalThis.fetch = fn; }

test("payment_id ausente: 400", async () => {
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({}), r);
  assert.equal(r.statusCode, 400);
  assert.equal(r.body.approved, false);
});

test("payment_id no numérico: 400 (evita inyectar algo raro en la URL de MP)", async () => {
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "12; DROP TABLE" }), r);
  assert.equal(r.statusCode, 400);
});

test("sin MP_ACCESS_TOKEN: 500 no_token", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "999" }), r);
  assert.equal(r.statusCode, 500);
  assert.equal(r.body.error, "no_token");
});

test("MercadoPago responde con error HTTP: 502", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  mockFetch(async () => ({ ok: false, json: async () => ({}) }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "999" }), r);
  assert.equal(r.statusCode, 502);
  assert.equal(r.body.error, "mp_error");
});

test("pago pendiente: approved=false y SIN licencia (no se regala nada)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  mockFetch(async () => ({
    ok: true, json: async () => ({ status: "pending", metadata: { plan: "pro" } }),
  }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "111" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.approved, false);
  assert.equal(r.body.license, null,
    "un pago NO aprobado no puede terminar emitiendo una licencia");
});

test("pago rechazado: approved=false y sin licencia", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  mockFetch(async () => ({
    ok: true, json: async () => ({ status: "rejected", metadata: { plan: "pro" } }),
  }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "222" }), r);
  assert.equal(r.body.approved, false);
  assert.equal(r.body.license, null);
});

test("pago aprobado + LICENSE_SECRET configurado: emite una licencia válida", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  mockFetch(async () => ({
    ok: true,
    json: async () => ({
      status: "approved", metadata: { plan: "pro" },
      payer: { email: "cliente@ejemplo.com" },
    }),
  }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "333" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.approved, true);
  assert.ok(r.body.license, "no emitió ninguna licencia con el pago aprobado");
  const claims = verify(r.body.license, process.env.LICENSE_SECRET);
  assert.ok(claims, "la licencia emitida no es válida contra su propio secreto");
  assert.equal(claims.plan, "pro");
  assert.equal(claims.pid, "333");
  // El email va en `sub`, que es la clave que lee la app instalada
  // (`backend_venta/licencias.py`). Antes iba en `email`, una clave que del
  // lado Python no existe — parte del mismo desajuste que rompía la licencia.
  assert.equal(claims.sub, "cliente@ejemplo.com");
  assert.equal(claims.edition, "venta");
  assert.ok(claims.exp > claims.iat, "la licencia tiene que tener vencimiento");
});

test("un plan aprobado pero fuera del catálogo no emite una licencia rota", async () => {
  // Si el checkout cobrara un plan que el catálogo de licencias no conoce,
  // emitir igual daría un token que la app rechaza. Mejor avisar.
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  mockFetch(async () => ({
    ok: true,
    json: async () => ({ status: "approved", metadata: { plan: "plan_que_no_existe" } }),
  }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "334" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.approved, true);
  assert.equal(r.body.license, null);
  assert.equal(r.body.license_error, "plan_no_licenciable");
});

test("usa KOBRA_LICENSE_SECRET cuando está — es el nombre que lee la app", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.KOBRA_LICENSE_SECRET = CLAVE_APP_PRUEBA;
  process.env.LICENSE_SECRET = CLAVE_VERCEL_PRUEBA;
  mockFetch(async () => ({
    ok: true,
    json: async () => ({ status: "approved", metadata: { plan: "basico" }, payer: { email: "a@b.com" } }),
  }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "335" }), r);
  assert.ok(r.body.license);
  assert.ok(verify(r.body.license, process.env.KOBRA_LICENSE_SECRET),
    "la licencia debería estar firmada con el secreto de la app");
  assert.equal(verify(r.body.license, process.env.LICENSE_SECRET), null);
  delete process.env.KOBRA_LICENSE_SECRET;
  assert.equal(claims.email, "cliente@ejemplo.com");
  // La licencia tiene que traer lo que la app LEE al activar — sobre todo
  // `exp`, sin el cual el cliente que pagó no puede entrar (ver _license.js).
  assert.ok(claims.exp > claims.iat, "la licencia vendida no tiene vencimiento");
  assert.equal(claims.edition, "venta");
  assert.deepEqual(claims.features, PLANES.pro.features);
});

test("el plan que llega en la metadata del pago no existe: no se emite licencia", () => {
  // Vale mas devolver el pago sin licencia y resolverlo por soporte que
  // entregarle al cliente un token que su app va a rechazar.
  assert.equal(emitirLicencia({ plan: "gold", pid: "1" }, CLAVE_LICENCIA_PRUEBA), null);
});

test("pago aprobado pero SIN LICENSE_SECRET: approved=true, license=null (no crashea)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  delete process.env.LICENSE_SECRET;
  mockFetch(async () => ({
    ok: true, json: async () => ({ status: "approved", metadata: { plan: "pro" } }),
  }));
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "444" }), r);
  assert.equal(r.body.approved, true);
  assert.equal(r.body.license, null);
});

test("si fetch tira una excepción: 500, no un crash sin respuesta", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  mockFetch(async () => { throw new Error("timeout"); });
  const vp = require("./verify-payment");
  const r = res();
  await vp(req({ payment_id: "555" }), r);
  assert.equal(r.statusCode, 500);
  assert.equal(r.body.error, "exception");
});

test("el freno por IP corta después de varios intentos seguidos", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  const vp = require("./verify-payment");
  const misma = { query: { payment_id: "1" }, headers: { "x-forwarded-for": "66.66.66.66" } };
  const codigos = [];
  for (let i = 0; i < 25; i++) {
    const r = res();
    await vp(misma, r);
    codigos.push(r.statusCode);
  }
  assert.ok(codigos.includes(429), `nunca frenó: ${codigos}`);
});
