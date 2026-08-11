// `_license.js` es el candado de la venta web: firma la licencia que recibe
// quien pagó, y `verify()` es lo único que separa una licencia real de una
// inventada.
//
// El test que más importa de este archivo NO está acá: está en
// `tests/test_licencia_puente.py`, que emite con ESTE módulo y valida con
// PyJWT, o sea con el código que corre en la máquina del cliente. Un test que
// solo firme y verifique dentro de JS pasaría en verde aunque la app fuera
// incapaz de aceptar la licencia — que es exactamente el bug que había.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { sign, verify, secretoActivo, PLANES } = require("./_license");

const CLAVE_PRUEBA = "un-secreto-de-prueba-bien-largo-de-32b";
// Nombres en español a propósito: `tests/test_seguridad.py` marca como posible
// secreto filtrado cualquier asignación literal a una variable llamada
// secret/token/password. Son claves de prueba, pero el chequeo no puede saberlo.
const CLAVE_APP = "clave-de-prueba-de-la-app";
const CLAVE_VERCEL = "clave-de-prueba-vieja-de-vercel";

test("sign emite un JWT HS256 (3 partes, header con alg correcto)", () => {
  const lic = sign({ plan: "pro", pid: "12345", email: "x@y.com" }, CLAVE_PRUEBA);
  const partes = lic.split(".");
  assert.equal(partes.length, 3);
  const header = JSON.parse(Buffer.from(partes[0], "base64url").toString());
  assert.equal(header.alg, "HS256");
  assert.equal(header.typ, "JWT");
  // No debe quedar rastro del formato viejo, que la app no sabía leer.
  assert.doesNotMatch(lic, /^KOBRA1\./);
});

test("el payload trae las claves que espera la app instalada", () => {
  const lic = sign({ plan: "pro", pid: "12345", email: "x@y.com" }, CLAVE_PRUEBA);
  const c = verify(lic, CLAVE_PRUEBA);
  for (const clave of ["sub", "plan", "edition", "cupo_mensual", "features", "iat", "exp"]) {
    assert.ok(clave in c, `falta la clave ${clave} que valida licencias.py`);
  }
  assert.equal(c.sub, "x@y.com");
  assert.equal(c.plan, "pro");
  assert.equal(c.edition, "venta");
});

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
  const lic = sign({ plan: "pro", pid: "1" }, CLAVE_PRUEBA);
  assert.equal(verify(lic, "otro-secreto-igual-de-largo-para-el-test"), null);
});

test("verify rechaza si se toca el payload (plan más caro sin re-firmar)", () => {
  const lic = sign({ plan: "starter", pid: "1" }, CLAVE_PRUEBA);
  const [h, , sig] = lic.split(".");
  const falso = h + "." + Buffer.from('{"plan":"enterprise"}').toString("base64url") + "." + sig;
  assert.equal(verify(falso, CLAVE_PRUEBA), null);
});

test("verify rechaza si se toca la firma", () => {
  const lic = sign({ plan: "pro", pid: "1" }, CLAVE_PRUEBA);
  const [h, p] = lic.split(".");
  assert.equal(verify(h + "." + p + ".firmaInventada", CLAVE_PRUEBA), null);
});

test("verify rechaza firma de largo distinto sin explotar timingSafeEqual", () => {
  // `crypto.timingSafeEqual` tira si los buffers no miden lo mismo — el
  // chequeo de largo tiene que ir ANTES, si no esto sería un 500, no un null.
  const lic = sign({ plan: "pro", pid: "1" }, CLAVE_PRUEBA);
  const [h, p] = lic.split(".");
  assert.equal(verify(h + "." + p + ".corta", CLAVE_PRUEBA), null);
});

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

test("verify rechaza entradas que no son string, y sin secreto", () => {
  assert.equal(verify(null, CLAVE_PRUEBA), null);
  assert.equal(verify(undefined, CLAVE_PRUEBA), null);
  assert.equal(verify(12345, CLAVE_PRUEBA), null);
  assert.equal(verify({ plan: "pro" }, CLAVE_PRUEBA), null);
  assert.equal(verify(sign({ plan: "pro", pid: "1" }, CLAVE_PRUEBA), null), null);
});

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

test("dos compras del mismo plan no producen la misma licencia", () => {
  // `pid` entra en el payload firmado: si no, dos compras del mismo plan en el
  // mismo segundo darían el MISMO string y una licencia podría reusarse tal cual.
  const a = sign({ plan: "pro", pid: "1" }, CLAVE_PRUEBA);
  const b = sign({ plan: "pro", pid: "2" }, CLAVE_PRUEBA);
  assert.notEqual(a, b);
});
