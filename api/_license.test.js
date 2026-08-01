// `_license.js` es el candado de la venta web: firma la licencia que recibe
// quien pagó, y `verify()` es lo único que separa una licencia real de una
// inventada. Antes de este archivo tenía CERO tests — el motivo por el que
// se prioriza acá, primero, dentro del eje de dinero.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { sign, verify } = require("./_license");

const CLAVE_PRUEBA = "un-secreto-de-prueba-bien-largo";

test("sign + verify: round-trip devuelve el payload original", () => {
  const payload = { plan: "pro", pid: "12345", email: "x@y.com", iat: 1000 };
  const lic = sign(payload, CLAVE_PRUEBA);
  assert.match(lic, /^KOBRA1\./);
  assert.deepEqual(verify(lic, CLAVE_PRUEBA), payload);
});

test("verify rechaza con el secreto equivocado", () => {
  const lic = sign({ plan: "pro" }, CLAVE_PRUEBA);
  assert.equal(verify(lic, "otro-secreto"), null);
});

test("verify rechaza si se toca el cuerpo (payload falsificado)", () => {
  const lic = sign({ plan: "starter" }, CLAVE_PRUEBA);
  const [pre, body, sig] = lic.split(".");
  // Alguien intenta colarse un plan más caro sin re-firmar.
  const falso = pre + "." + Buffer.from('{"plan":"enterprise"}').toString("base64url") + "." + sig;
  assert.equal(verify(falso, CLAVE_PRUEBA), null);
});

test("verify rechaza si se toca la firma", () => {
  const lic = sign({ plan: "pro" }, CLAVE_PRUEBA);
  const [pre, body] = lic.split(".");
  assert.equal(verify(pre + "." + body + ".firmaInventada", CLAVE_PRUEBA), null);
});

test("verify rechaza una firma de largo distinto sin explotar timingSafeEqual", () => {
  // `crypto.timingSafeEqual` tira si los buffers no miden lo mismo — el
  // chequeo de largo tiene que ir ANTES, si no esto sería un 500, no un null.
  const lic = sign({ plan: "pro" }, CLAVE_PRUEBA);
  const [pre, body] = lic.split(".");
  assert.equal(verify(pre + "." + body + ".corta", CLAVE_PRUEBA), null);
});

test("verify rechaza formato con otra cantidad de partes", () => {
  assert.equal(verify("KOBRA1.soloDosPartes", CLAVE_PRUEBA), null);
  assert.equal(verify("a.b.c.d", CLAVE_PRUEBA), null);
});

test("verify rechaza otro prefijo de versión", () => {
  const lic = sign({ plan: "pro" }, CLAVE_PRUEBA);
  const [, body, sig] = lic.split(".");
  assert.equal(verify("KOBRA2." + body + "." + sig, CLAVE_PRUEBA), null);
});

test("verify rechaza entradas que no son string", () => {
  assert.equal(verify(null, CLAVE_PRUEBA), null);
  assert.equal(verify(undefined, CLAVE_PRUEBA), null);
  assert.equal(verify(12345, CLAVE_PRUEBA), null);
  assert.equal(verify({ plan: "pro" }, CLAVE_PRUEBA), null);
});

test("verify no explota si el cuerpo decodifica a JSON invalido", () => {
  const fake = "not-valid-base64url!!!";
  const sig = require("crypto").createHmac("sha256", CLAVE_PRUEBA).update(fake).digest("base64url");
  assert.equal(verify(`KOBRA1.${fake}.${sig}`, CLAVE_PRUEBA), null);
});

test("dos licencias del mismo plan en momentos distintos no son iguales", () => {
  // `iat` entra en el payload firmado: si no, dos compras del mismo plan
  // producirian el MISMO string y una licencia podria reusarse tal cual.
  const a = sign({ plan: "pro", iat: 1 }, CLAVE_PRUEBA);
  const b = sign({ plan: "pro", iat: 2 }, CLAVE_PRUEBA);
  assert.notEqual(a, b);
});
