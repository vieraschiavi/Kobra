// Tests del freno por IP de las funciones serverless (api/*.js).
//
// `node --test`, sin dependencias: antes de esto no había NINGÚN test JS en
// el repo (ni jest, ni vitest, ni un script "test" en package.json) — la
// puerta de entrada del dinero real (checkout, verificación de pago, firma
// de licencia) tenía 0% de cobertura. Node trae su test runner desde la 18:
// agregar una dependencia nueva para esto sería exactamente el tipo de cosa
// que este proyecto evita a propósito (ver el docstring de
// kobra/limitador.py: "cada dependencia es una cosa más que puede fallar al
// instalar" — el mismo criterio vale para el lado Node).
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { limitar, ipDe, permitir } = require("./_ratelimit");

function req(ip) {
  return { headers: ip ? { "x-forwarded-for": ip } : {} };
}
function res() {
  const r = { statusCode: null, body: null, headers: {} };
  r.status = (c) => { r.statusCode = c; return r; };
  r.json = (b) => { r.body = b; return r; };
  r.setHeader = (k, v) => { r.headers[k] = v; };
  return r;
}

test("deja pasar los primeros y despues corta", () => {
  let ok = 0, bloqueados = 0;
  for (let i = 0; i < 8; i++) {
    if (limitar(req("9.9.9.9"), res(), "accionA", 5, 60)) ok++; else bloqueados++;
  }
  assert.equal(ok, 5);
  assert.equal(bloqueados, 3);
});

test("el limite es por IP: otra IP no se ve afectada", () => {
  for (let i = 0; i < 5; i++) limitar(req("8.8.8.8"), res(), "accionB", 5, 60);
  assert.equal(limitar(req("8.8.8.8"), res(), "accionB", 5, 60), false);
  assert.equal(limitar(req("1.2.3.4"), res(), "accionB", 5, 60), true);
});

test("el limite es por accion: agotar una no frena la otra", () => {
  for (let i = 0; i < 5; i++) limitar(req("7.7.7.7"), res(), "checkout", 5, 60);
  assert.equal(limitar(req("7.7.7.7"), res(), "checkout", 5, 60), false);
  assert.equal(limitar(req("7.7.7.7"), res(), "verify-payment", 5, 60), true);
});

test("cuando corta, responde 429 con Retry-After", () => {
  for (let i = 0; i < 3; i++) limitar(req("6.6.6.6"), res(), "accionC", 3, 60);
  const r = res();
  const paso = limitar(req("6.6.6.6"), r, "accionC", 3, 60);
  assert.equal(paso, false);
  assert.equal(r.statusCode, 429);
  assert.ok(r.headers["Retry-After"], "un 429 sin Retry-After no es accionable");
  assert.ok(Number(r.headers["Retry-After"]) > 0);
});

test("ipDe lee x-forwarded-for y toma el primer eslabon", () => {
  assert.equal(ipDe({ headers: { "x-forwarded-for": "203.0.113.9, 10.0.0.1" } }),
               "203.0.113.9");
});

test("ipDe cae a x-real-ip si no hay x-forwarded-for", () => {
  assert.equal(ipDe({ headers: { "x-real-ip": "203.0.113.7" } }), "203.0.113.7");
});

test("ipDe no explota si req.headers falta", () => {
  // Se cayó en un test de otro endpoint que armaba el req a mano sin
  // `headers`: en Vercel real siempre está, pero que un `req` incompleto
  // tire un TypeError sin responder nada es peor que devolver "desconocido".
  assert.equal(ipDe({}), "desconocido");
});

test("las fichas se recargan con el tiempo", async () => {
  const clave = "recarga-test";
  for (let i = 0; i < 2; i++) permitir(clave, 2, 0.1); // 2 fichas, ventana 100 ms
  assert.equal(permitir(clave, 2, 0.1).ok, false, "sin esperar, tiene que estar cortado");
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(permitir(clave, 2, 0.1).ok, true, "tras esperar la ventana, se recarga");
});
