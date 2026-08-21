// © 2026 Martín Viera. Todos los derechos reservados.

// El webhook es la red de seguridad del cobro: es lo único que se entera de
// un pago cuando el comprador cerró la pestaña. Y es una URL PÚBLICA, así que
// lo primero que hay que fijar es que un aviso inventado no pueda fabricar
// una licencia — la única fuente de verdad es releer el pago contra la API de
// MercadoPago con el access token del vendedor.
const { test, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const { verify } = require("./_license");

const CLAVE_LICENCIA_PRUEBA = "otro-secreto-de-prueba-larguisimo";

let ipCounter = 0;
function req(query, body) {
  ipCounter += 1;
  return {
    method: "POST",
    query: query || {},
    body: body || {},
    headers: { "x-forwarded-for": `10.1.0.${ipCounter % 250}` },
  };
}
function res() {
  const r = { statusCode: null, body: null };
  r.status = (c) => { r.statusCode = c; return r; };
  r.json = (b) => { r.body = b; return r; };
  r.setHeader = () => {};
  return r;
}

let envOriginal;
let erroresLogueados;
let errorOriginal;
beforeEach(() => {
  envOriginal = { ...process.env };
  delete require.cache[require.resolve("./webhook-mercadopago")];
  erroresLogueados = [];
  errorOriginal = console.error;
  console.error = (...a) => erroresLogueados.push(a.map(String).join(" "));
});
afterEach(() => {
  process.env = envOriginal;
  console.error = errorOriginal;
  if (globalThis.__fetchOriginal) { globalThis.fetch = globalThis.__fetchOriginal; delete globalThis.__fetchOriginal; }
});
function mockFetch(fn) { globalThis.__fetchOriginal = globalThis.fetch; globalThis.fetch = fn; }

// --- Lo que NO puede pasar: fabricar una licencia con un aviso inventado ----
test("un aviso inventado que dice 'aprobado' NO emite licencia: se relee el pago de verdad", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  let mailEnviado = false;
  mockFetch(async (url) => {
    if (String(url).includes("resend")) { mailEnviado = true; return { ok: true }; }
    // La API real dice que ese pago está RECHAZADO, sin importar lo que
    // afirme el cuerpo del aviso.
    return { ok: true, json: async () => ({ status: "rejected", metadata: { plan: "pro" } }) };
  });
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "777" },
               { status: "approved", metadata: { plan: "enterprise" },
                 transaction_amount: 999999 }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.license, undefined, "no puede emitir licencia por un pago rechazado");
  assert.equal(r.body.status, "rejected", "el estado sale de la API, no del aviso");
  assert.equal(mailEnviado, false, "no puede mandar una licencia que no debía existir");
});

test("el monto y el plan del cuerpo del aviso se ignoran por completo", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  let licenciaEnviada = null;
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend")) {
      licenciaEnviada = JSON.parse(opts.body).text;
      return { ok: true };
    }
    // El pago REAL es de plan "basico".
    return { ok: true, json: async () => ({
      status: "approved", metadata: { plan: "basico" },
      payer: { email: "comprador@ejemplo.com" } }) };
  });
  process.env.RESEND_API_KEY = "re_prueba";
  const wh = require("./webhook-mercadopago");
  const r = res();
  // El aviso miente y dice "enterprise".
  await wh(req({ type: "payment", "data.id": "778" }, { metadata: { plan: "enterprise" } }), r);
  assert.equal(r.body.license, true);
  assert.ok(licenciaEnviada, "no mandó el mail con la licencia");
  const token = licenciaEnviada.split("\n").find((l) => l.split(".").length === 3);
  const claims = verify(token.trim(), CLAVE_LICENCIA_PRUEBA);
  assert.ok(claims, "la licencia emitida no valida");
  assert.equal(claims.plan, "basico",
    "el plan tiene que salir del pago real, nunca de lo que afirme el aviso");
});

// --- El caso que el webhook existe para cubrir ------------------------------
test("pago aprobado: emite la licencia y se la manda por mail al comprador", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  process.env.RESEND_API_KEY = "re_prueba";
  let mail = null;
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend")) { mail = JSON.parse(opts.body); return { ok: true }; }
    return { ok: true, json: async () => ({
      status: "approved", metadata: { plan: "pro" },
      payer: { email: "cliente@empresa.com" } }) };
  });
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "779" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.license, true);
  assert.equal(r.body.enviado, true);
  assert.ok(mail.to.includes("cliente@empresa.com"), "no le llegó al comprador");
  assert.ok(mail.text.includes("MVKobraAI_Setup.exe"), "el mail no trae la descarga");
});

test("si el mail al comprador rebota, el dueño IGUAL recibe la licencia (modo prueba de Resend)", async () => {
  // Con el remitente compartido `onboarding@resend.dev`, Resend entrega solo a
  // la casilla del titular de la cuenta y rechaza cualquier otra con 403. Ese
  // es el estado por defecto hasta verificar un dominio propio, así que es el
  // caso que más va a correr en la vida real: no puede terminar con nadie
  // teniendo la licencia.
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  process.env.RESEND_API_KEY = "re_prueba";
  delete process.env.RESEND_FROM;
  const recibieron = [];
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend")) {
      const para = JSON.parse(opts.body).to[0];
      if (para !== "vieraschiavi@gmail.com") {
        return { ok: false, status: 403,
                 text: async () => "You can only send testing emails to your own email address" };
      }
      recibieron.push(para);
      return { ok: true };
    }
    return { ok: true, json: async () => ({
      status: "approved", metadata: { plan: "pro" },
      payer: { email: "cliente@empresa.com" } }) };
  });
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "781" }), r);
  assert.equal(r.body.license, true);
  assert.equal(r.body.enviado, false, "el mail al comprador rebotó, no se puede decir que se envió");
  assert.equal(r.body.avisado_dueno, true, "el rechazo del comprador no puede llevarse puesta la copia al dueño");
  assert.deepEqual(recibieron, ["vieraschiavi@gmail.com"]);
  const log = erroresLogueados.join("\n");
  assert.ok(log.includes("781"), "el log no permite identificar el pago");
  assert.match(log, /[\w-]+\.[\w-]+\.[\w-]+/, "el log no trae la licencia emitida");
});

test("RESEND_FROM manda el remitente: con dominio propio verificado, el mail sale desde ahí", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  process.env.RESEND_API_KEY = "re_prueba";
  process.env.RESEND_FROM = "MV Kobra AI <licencias@mvkobranzaia.com>";
  const remitentes = [];
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend")) { remitentes.push(JSON.parse(opts.body).from); return { ok: true }; }
    return { ok: true, json: async () => ({
      status: "approved", metadata: { plan: "pro" },
      payer: { email: "cliente@empresa.com" } }) };
  });
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "782" }), r);
  assert.equal(r.body.enviado, true);
  assert.deepEqual(remitentes, ["MV Kobra AI <licencias@mvkobranzaia.com>",
                                "MV Kobra AI <licencias@mvkobranzaia.com>"]);
});

test("sin RESEND_API_KEY la licencia NO se pierde: queda en el log para recuperarla", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  delete process.env.RESEND_API_KEY;
  mockFetch(async () => ({ ok: true, json: async () => ({
    status: "approved", metadata: { plan: "pro" },
    payer: { email: "cliente@empresa.com" } }) }));
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "780" }), r);
  assert.equal(r.body.license, true);
  assert.equal(r.body.enviado, false);
  const log = erroresLogueados.join("\n");
  assert.ok(log.includes("780"), "el log no permite identificar el pago");
  assert.ok(log.includes("cliente@empresa.com"), "el log no dice a quién entregarla");
  assert.match(log, /[\w-]+\.[\w-]+\.[\w-]+/, "el log no trae la licencia emitida");
});

// --- Robustez: el aviso llega de varias formas y muchas veces ---------------
test("acepta las dos formas de aviso de MercadoPago (query y body, IPN y webhooks)", async () => {
  const { idDePago } = require("./webhook-mercadopago");
  assert.equal(idDePago({ query: { type: "payment", "data.id": "111" } }), "111");
  assert.equal(idDePago({ query: { topic: "payment", id: "222" } }), "222");
  assert.equal(idDePago({ query: {}, body: { type: "payment", data: { id: "333" } } }), "333");
  assert.equal(idDePago({ query: {}, body: { topic: "payment", id: "444" } }), "444");
});

test("ignora los avisos que no son de un pago (merchant_order trae otro id)", async () => {
  const { idDePago } = require("./webhook-mercadopago");
  // El id de una orden no sirve contra /v1/payments: consultarlo daría 404.
  assert.equal(idDePago({ query: { topic: "merchant_order", id: "555" } }), null);
  assert.equal(idDePago({ query: { type: "payment", "data.id": "no-numerico" } }), null);
  assert.equal(idDePago({ query: {} }), null);
});

test("un aviso sin id de pago se responde 200 sin llamar a MercadoPago", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  let llamoAMP = false;
  mockFetch(async () => { llamoAMP = true; return { ok: true, json: async () => ({}) }; });
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ topic: "merchant_order", id: "999" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.ignorado, true);
  assert.equal(llamoAMP, false);
});

test("pago pendiente: responde 200 y no emite nada (ya llegará otro aviso)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  mockFetch(async () => ({ ok: true, json: async () => ({ status: "pending", metadata: { plan: "pro" } }) }));
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "781" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.status, "pending");
  assert.equal(r.body.license, undefined);
});

test("si MercadoPago falla, se devuelve 5xx para que REINTENTE (no se pierde el pago)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  mockFetch(async () => ({ ok: false, json: async () => ({ message: "service unavailable" }) }));
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "782" }), r);
  assert.equal(r.statusCode, 502,
    "con 200 MercadoPago no reintentaría y el pago quedaría sin licencia");
});

test("sin MP_ACCESS_TOKEN devuelve 5xx para que reintente cuando esté configurado", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "783" }), r);
  assert.equal(r.statusCode, 500);
  assert.equal(r.body.error, "no_token");
});

test("un plan aprobado fuera del catálogo no emite una licencia rota, y avisa fuerte", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  mockFetch(async () => ({ ok: true, json: async () => ({
    status: "approved", metadata: { plan: "plan_que_no_existe" },
    payer: { email: "x@y.com" } }) }));
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "784" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.license, false);
  assert.equal(r.body.motivo, "plan_no_licenciable");
  assert.ok(erroresLogueados.join("\n").includes("784"));
});

test("dos avisos del mismo pago emiten la MISMA licencia (MercadoPago reintenta)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  process.env.RESEND_API_KEY = "re_prueba";
  const mails = [];
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend")) { mails.push(JSON.parse(opts.body).text); return { ok: true }; }
    return { ok: true, json: async () => ({
      status: "approved", metadata: { plan: "basico" },
      payer: { email: "cliente@empresa.com" } }) };
  });
  const wh = require("./webhook-mercadopago");
  await wh(req({ type: "payment", "data.id": "785" }), res());
  await wh(req({ type: "payment", "data.id": "785" }), res());
  // Dos avisos × dos envíos por aviso (dueño y comprador van por separado).
  assert.equal(mails.length, 4);
  const tok = (t) => t.split("\n").find((l) => l.split(".").length === 3).trim();
  const a = verify(tok(mails[0]), CLAVE_LICENCIA_PRUEBA);
  const b = verify(tok(mails[3]), CLAVE_LICENCIA_PRUEBA);
  // La licencia es determinística a partir del pago: reenviarla es inofensivo
  // (el cliente recibe la misma), no crea una licencia extra ni un cupo doble.
  assert.equal(a.sub, b.sub);
  assert.equal(a.plan, b.plan);
  assert.equal(a.pid, b.pid);
  assert.equal(a.pid, "785");
});

test("el freno por IP corta una ráfaga contra la URL pública", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  const wh = require("./webhook-mercadopago");
  const misma = { method: "POST", query: { type: "payment", "data.id": "1" },
                  body: {}, headers: { "x-forwarded-for": "77.77.77.77" } };
  const codigos = [];
  for (let i = 0; i < 140; i++) {
    const r = res();
    await wh(misma, r);
    codigos.push(r.statusCode);
  }
  assert.ok(codigos.includes(429), "nunca frenó una ráfaga a una URL pública");
});

// ---------------------------------------------------------------------------
// Mismo defecto que en verify-payment: el webhook preguntaba por el secreto
// HS256 antes de firmar, pero `sign()` usa RS256 cuando hay clave privada y
// ni mira el secreto. En el deploy recomendado —privada sola— el webhook
// respondía `sin_secreto` y nadie recibía su licencia, con la plata cobrada.
// ---------------------------------------------------------------------------
test("solo RS256 configurado: el webhook emite y manda la licencia igual", async () => {
  const { generateKeyPairSync } = require("node:crypto");
  const { privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
    publicKeyEncoding: { type: "spki", format: "pem" },
  });
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.KOBRA_LICENSE_PRIVATE_KEY = privateKey;
  delete process.env.KOBRA_LICENSE_SECRET;
  delete process.env.LICENSE_SECRET;

  let licenciaEnviada = null;
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend")) {
      licenciaEnviada = JSON.parse(opts.body).text;
      return { ok: true };
    }
    return { ok: true, json: async () => ({
      status: "approved", metadata: { plan: "basico" },
      payer: { email: "comprador@ejemplo.com" } }) };
  });
  process.env.RESEND_API_KEY = "re_prueba";
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "9200" }), r);

  assert.equal(r.body.license, true,
    "pago cobrado y sin licencia emitida: es el peor resultado posible");
  assert.notEqual(r.body.motivo, "sin_secreto");
  assert.ok(licenciaEnviada, "no salió el mail con la licencia");
  const token = licenciaEnviada.split("\n").find((l) => l.split(".").length === 3).trim();
  const alg = JSON.parse(Buffer.from(token.split(".")[0], "base64url").toString()).alg;
  assert.equal(alg, "RS256");
});

test("sin privada Y sin secreto: avisa en vez de emitir", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  delete process.env.KOBRA_LICENSE_PRIVATE_KEY;
  delete process.env.KOBRA_LICENSE_SECRET;
  delete process.env.LICENSE_SECRET;
  mockFetch(async () => ({ ok: true, json: async () => ({
    status: "approved", metadata: { plan: "basico" },
    payer: { email: "x@y.com" } }) }));
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "9201" }), r);
  assert.equal(r.body.license, false);
  assert.equal(r.body.motivo, "sin_secreto");
  assert.ok(erroresLogueados.join("\n").includes("9201"),
    "si no se puede emitir, el payment_id tiene que quedar en el log para resolverlo a mano");
});

// ---------------------------------------------------------------------------
// Plata que se va DESPUÉS de haber entregado la licencia.
//
// `refunded` y `charged_back` caían en el mismo `else` que `pending` y se
// respondía 200 sin hacer nada. Un cliente compraba Starter (365 días), pedía
// contracargo a los 20, y seguía usando el producto 345 días más con la plata
// devuelta. Revocar de verdad exige una lista de revocación y chequeo online
// —otra arquitectura—, pero el dueño tiene que enterarse.
// ---------------------------------------------------------------------------
for (const estado of ["refunded", "charged_back", "cancelled"]) {
  test(`${estado}: avisa al dueño en vez de responder 200 en silencio`, async () => {
    process.env.MP_ACCESS_TOKEN = "TEST-token";
    process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
    process.env.RESEND_API_KEY = "re_prueba";
    let avisoAlDueno = null;
    mockFetch(async (url, opts) => {
      if (String(url).includes("resend")) {
        avisoAlDueno = JSON.parse(opts.body);
        return { ok: true };
      }
      return { ok: true, json: async () => ({
        status: estado, transaction_amount: 690,
        metadata: { plan: "starter" },
        payer: { email: "comprador@ejemplo.com" } }) };
    });
    const wh = require("./webhook-mercadopago");
    const r = res();
    await wh(req({ type: "payment", "data.id": "9300" }), r);

    assert.equal(r.statusCode, 200);
    assert.equal(r.body.avisado, true, "no avisó a nadie");
    assert.ok(avisoAlDueno, "no salió el mail al dueño");
    assert.ok(avisoAlDueno.subject.includes("9300"),
      "el aviso no dice de qué pago se trata");
    assert.ok(erroresLogueados.join("\n").includes("9300"),
      "no queda rastro en el log para resolverlo a mano");
  });
}

test("un refund NO emite una licencia nueva", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.LICENSE_SECRET = CLAVE_LICENCIA_PRUEBA;
  delete process.env.RESEND_API_KEY;
  mockFetch(async () => ({ ok: true, json: async () => ({
    status: "refunded", metadata: { plan: "starter" },
    payer: { email: "x@y.com" } }) }));
  const wh = require("./webhook-mercadopago");
  const r = res();
  await wh(req({ type: "payment", "data.id": "9301" }), r);
  assert.notEqual(r.body.license, true,
    "un pago devuelto no puede entregar producto");
});
