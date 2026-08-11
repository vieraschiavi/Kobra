// `_license.js` es el candado de la venta web: firma la licencia que recibe
// quien pagó, y `verify()` es lo único que separa una licencia real de una
// inventada. Antes de este archivo tenía CERO tests — el motivo por el que
// se prioriza acá, primero, dentro del eje de dinero.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { sign, verify, emitirLicencia, PLANES } = require("./_license");
const { sign, verify, secretoActivo, PLANES } = require("./_license");

const CLAVE_PRUEBA = "un-secreto-de-prueba-bien-largo";

const claimsDe = (lic) =>
  JSON.parse(Buffer.from(lic.split(".")[1], "base64url").toString("utf8"));

test("sign + verify: round-trip devuelve el payload original", () => {
  const payload = { plan: "pro", pid: "12345", email: "x@y.com", iat: 1000 };
  const lic = sign(payload, CLAVE_PRUEBA);
  // JWT HS256: el 1er segmento es el header, no una etiqueta de version. Es lo
  // que permite que PyJWT —o sea, la app que valida la compra— lo lea.
  const header = JSON.parse(Buffer.from(lic.split(".")[0], "base64url").toString("utf8"));
  assert.deepEqual(header, { alg: "HS256", typ: "JWT" });
  assert.deepEqual(verify(lic, CLAVE_PRUEBA), payload);
});

test("emitirLicencia arma los claims que la app espera al activar", () => {
  const lic = emitirLicencia({ plan: "pro", pid: "999", email: "a@b.com" }, CLAVE_PRUEBA);
  const c = verify(lic, CLAVE_PRUEBA);
  // `exp` es el que faltaba: sin el, la app reventaba calculando dias restantes.
  for (const k of ["sub", "plan", "edition", "cupo_mensual", "features", "iat", "exp"]) {
    assert.ok(k in c, "falta el claim " + k);
  }
  assert.equal(c.sub, "a@b.com");
  assert.equal(c.exp - c.iat, PLANES.pro.dias * 24 * 3600);
});

test("emitirLicencia sin email usa el id de pago como titular", () => {
  const c = verify(emitirLicencia({ plan: "basico", pid: "777" }, CLAVE_PRUEBA), CLAVE_PRUEBA);
  assert.equal(c.sub, "mp:777");
});

test("emitirLicencia devuelve null si el plan no existe", () => {
  // Mejor no entregar licencia que entregar una que la app rechaza despues.
  assert.equal(emitirLicencia({ plan: "inventado" }, CLAVE_PRUEBA), null);
  assert.equal(emitirLicencia({ plan: null }, CLAVE_PRUEBA), null);
});

test("verify rechaza alg:none (el ataque clasico contra JWT)", () => {
  const lic = emitirLicencia({ plan: "pro" }, CLAVE_PRUEBA);
  const cuerpo = lic.split(".")[1];
  const hNone = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64url");
  // Sin firma, y con firma vacia: las dos formas del ataque.
  assert.equal(verify(`${hNone}.${cuerpo}.`, CLAVE_PRUEBA), null);
  assert.equal(verify(`${hNone}.${cuerpo}.${"x".repeat(43)}`, CLAVE_PRUEBA), null);
});

test("verify rechaza si se cambia el plan a uno mas caro", () => {
  const lic = emitirLicencia({ plan: "basico" }, CLAVE_PRUEBA);
  const [h, , s] = lic.split(".");
  const c = claimsDe(lic);
  c.plan = "enterprise";
  const falso = Buffer.from(JSON.stringify(c)).toString("base64url");
  assert.equal(verify(`${h}.${falso}.${s}`, CLAVE_PRUEBA), null);
test("cupo y features salen del catálogo, no de lo que mande el cliente", () => {
  const c = verify(sign({ plan: "basico", pid: "1" }, CLAVE_PRUEBA), CLAVE_PRUEBA);
  assert.equal(c.cupo_mensual, PLANES.basico.cupo_mensual);
  assert.deepEqual(c.features, PLANES.basico.features);
});

test("sin email, `sub` cae al id de pago: una licencia nunca sale sin dueño", () => {
  const c = verify(sign({ plan: "pro", pid: "999" }, CLAVE_PRUEBA), CLAVE_PRUEBA);
  assert.equal(c.sub, "pago:999");
});

test("un plan fuera del catálogo no se emite", () => {
  assert.throws(() => sign({ plan: "inventado", pid: "1" }, CLAVE_PRUEBA), /plan desconocido/);
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
  assert.equal(verify("soloDosPartes.aca", CLAVE_PRUEBA), null);
  assert.equal(verify("a.b.c.d", CLAVE_PRUEBA), null);
  assert.equal(verify("", CLAVE_PRUEBA), null);
test("verify rechaza un algoritmo que no sea HS256 (alg=none)", () => {
  // Sin este chequeo, alguien manda alg:"none" y se autofirma la licencia.
  const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ plan: "enterprise" })).toString("base64url");
  assert.equal(verify(header + "." + payload + ".", CLAVE_PRUEBA), null);
});

test("verify rechaza una licencia vencida", () => {
  const vencida = sign({ plan: "pro", pid: "1", dias: -1 }, CLAVE_PRUEBA);
  assert.equal(verify(vencida, CLAVE_PRUEBA), null);
});

test("verify rechaza formato con otra cantidad de partes", () => {
  assert.equal(verify("solo.dos", CLAVE_PRUEBA), null);
  assert.equal(verify("a.b.c.d", CLAVE_PRUEBA), null);
});

test("verify rechaza entradas que no son string", () => {
  assert.equal(verify(null, CLAVE_PRUEBA), null);
  assert.equal(verify(undefined, CLAVE_PRUEBA), null);
  assert.equal(verify(12345, CLAVE_PRUEBA), null);
  assert.equal(verify({ plan: "pro" }, CLAVE_PRUEBA), null);
});

test("verify no explota si el cuerpo decodifica a JSON invalido", () => {
  // Cuerpo basura pero CORRECTAMENTE FIRMADO: así se ejerce de verdad el
  // camino del JSON.parse, y no se sale antes por firma inválida.
  const h = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const basura = Buffer.from("esto no es json").toString("base64url");
  const sig = require("crypto")
    .createHmac("sha256", CLAVE_PRUEBA).update(`${h}.${basura}`).digest("base64url");
  assert.equal(verify(`${h}.${basura}.${sig}`, CLAVE_PRUEBA), null);
test("verify no explota si el cuerpo decodifica a JSON inválido", () => {
  const h = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const basura = "no-es-json-valido";
  const sig = require("crypto").createHmac("sha256", CLAVE_PRUEBA)
    .update(h + "." + basura).digest("base64url");
  assert.equal(verify(h + "." + basura + "." + sig, CLAVE_PRUEBA), null);
});

test("secretoActivo prioriza KOBRA_LICENSE_SECRET, el nombre que usa la app", () => {
  const previo = { k: process.env.KOBRA_LICENSE_SECRET, l: process.env.LICENSE_SECRET };
  try {
    process.env.KOBRA_LICENSE_SECRET = CLAVE_APP;
    process.env.LICENSE_SECRET = CLAVE_VERCEL;
    assert.equal(secretoActivo(), CLAVE_APP);

    delete process.env.KOBRA_LICENSE_SECRET;
    assert.equal(secretoActivo(), CLAVE_VERCEL, "debe aceptar el alias para no romper el deploy actual");

    delete process.env.LICENSE_SECRET;
    assert.equal(secretoActivo(), null);
  } finally {
    if (previo.k === undefined) delete process.env.KOBRA_LICENSE_SECRET; else process.env.KOBRA_LICENSE_SECRET = previo.k;
    if (previo.l === undefined) delete process.env.LICENSE_SECRET; else process.env.LICENSE_SECRET = previo.l;
  }
});

test("dos licencias del mismo plan en momentos distintos no son iguales", () => {
  // `iat` entra en el payload firmado: si no, dos compras del mismo plan
  // producirian el MISMO string y una licencia podria reusarse tal cual.
  const a = sign({ plan: "pro", iat: 1 }, CLAVE_PRUEBA);
  const b = sign({ plan: "pro", iat: 2 }, CLAVE_PRUEBA);
  assert.notEqual(a, b);
});
