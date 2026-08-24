// © 2026 Martín Viera. Todos los derechos reservados.

// `checkout.js` crea la preferencia de pago real contra MercadoPago — la
// puerta de entrada de la plata. Antes de este archivo, cero tests.
//
// `checkBotId` corre en modo "solo desarrollo" fuera de la infraestructura de
// Vercel (lo confirma su propio mensaje: "[Dev Only] ... will return HUMAN"),
// así que se usa el paquete real —instalado, no mockeado— y deja pasar. Lo
// que SÍ se mockea es `fetch`, porque llama a la API real de MercadoPago.
const { test, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");

let ipCounter = 0;
function req(body, extra) {
  ipCounter += 1;
  return {
    method: "POST",
    headers: { host: "mvkobranzaia.com", "x-forwarded-for": `10.0.0.${ipCounter}`, ...((extra || {}).headers || {}) },
    body,
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
beforeEach(() => {
  envOriginal = { ...process.env };
  delete require.cache[require.resolve("./checkout")];
  // Sin esto, en una máquina que TENGA la clave de Resend en el entorno, los
  // tests que no mockean `fetch` (405, 400, 503...) dispararían el aviso de
  // intención y saldrían a la API real de Resend. Un test no puede mandar
  // mails de verdad. Los tests del aviso la ponen ellos, explícitamente.
  delete process.env.RESEND_API_KEY;
});
afterEach(() => {
  process.env = envOriginal;
  if (globalThis.__fetchOriginal) { globalThis.fetch = globalThis.__fetchOriginal; delete globalThis.__fetchOriginal; }
});

function mockFetch(fn) {
  globalThis.__fetchOriginal = globalThis.fetch;
  globalThis.fetch = fn;
}

test("rechaza métodos que no son POST", async () => {
  const checkout = require("./checkout");
  const r = res();
  await checkout(Object.assign(req({}), { method: "GET" }), r);
  assert.equal(r.statusCode, 405);
});

test("plan inválido devuelve 400", async () => {
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "no-existe" }), r);
  assert.equal(r.statusCode, 400);
  assert.equal(r.body.error, "plan_invalido");
});

test("sin token de MercadoPago ni link configurado: 503", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  delete process.env.MP_LINK_PRO;
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "pro" }), r);
  assert.equal(r.statusCode, 503);
  assert.equal(r.body.error, "medio_pago_no_configurado");
});

test("sin token pero con link de pago configurado: devuelve ese link", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  process.env.MP_LINK_PRO = "https://mpago.la/algun-link";
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "pro" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.url, "https://mpago.la/algun-link");
});

test("con token: arma la preferencia y convierte el precio a UYU", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.MP_CURRENCY = "UYU";
  process.env.MP_TASA_UYU = "40";
  let cuerpoEnviado = null;
  mockFetch(async (url, opts) => {
    cuerpoEnviado = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ init_point: "https://mp/pagar/xyz" }) };
  });
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "pro" }), r);   // Pro = 349.0
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.url, "https://mp/pagar/xyz");
  assert.equal(cuerpoEnviado.items[0].currency_id, "UYU");
  assert.equal(cuerpoEnviado.items[0].unit_price, Math.round(349.0 * 40));
  assert.equal(cuerpoEnviado.metadata.plan, "pro");
});

test("arma una external_reference aleatoria y la repite en back_urls (así verify-payment puede atar el pago a ESTE checkout)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  let cuerpoEnviado = null;
  mockFetch(async (url, opts) => {
    cuerpoEnviado = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ init_point: "https://mp/pagar/xyz" }) };
  });
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "pro" }), r);
  assert.equal(r.statusCode, 200);
  const ref = cuerpoEnviado.external_reference;
  assert.match(ref, /^[0-9a-f]{32}$/, `la referencia no parece un token aleatorio: ${ref}`);
  assert.ok(cuerpoEnviado.back_urls.success.includes("ref=" + ref),
    "el link de éxito no lleva la misma referencia que se mandó a MercadoPago");
  assert.ok(cuerpoEnviado.back_urls.pending.includes("ref=" + ref),
    "el link de pendiente no lleva la misma referencia");
});

test("manda notification_url al webhook: la licencia no puede depender solo del navegador", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  let cuerpoEnviado = null;
  mockFetch(async (url, opts) => {
    cuerpoEnviado = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ init_point: "https://mp/pagar/xyz" }) };
  });
  const checkout = require("./checkout");
  await checkout(req({ plan: "pro" }), res());
  assert.equal(cuerpoEnviado.notification_url,
    "https://mvkobranzaia.com/api/webhook-mercadopago",
    "sin notification_url, un comprador que cierra la pestaña deja la plata " +
    "adentro sin que nadie se entere de que hay una licencia por entregar");
});

test("dos checkouts seguidos arman referencias distintas", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  const refs = [];
  mockFetch(async (url, opts) => {
    refs.push(JSON.parse(opts.body).external_reference);
    return { ok: true, json: async () => ({ init_point: "https://mp/pagar/xyz" }) };
  });
  const checkout = require("./checkout");
  await checkout(req({ plan: "pro" }), res());
  await checkout(req({ plan: "pro" }), res());
  assert.notEqual(refs[0], refs[1], "dos checkouts distintos no pueden compartir referencia");
});

test("MercadoPago responde sin init_point: 502", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  mockFetch(async () => ({ ok: true, json: async () => ({}) }));
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "starter" }), r);
  assert.equal(r.statusCode, 502);
  assert.equal(r.body.error, "mercadopago");
});

test("MercadoPago responde con error HTTP: 502", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  mockFetch(async () => ({ ok: false, json: async () => ({ message: "invalid_token" }) }));
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "starter" }), r);
  assert.equal(r.statusCode, 502);
});

test("si fetch tira una excepción: 500, no un crash sin respuesta", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  mockFetch(async () => { throw new Error("timeout de red"); });
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "starter" }), r);
  assert.equal(r.statusCode, 500);
  assert.equal(r.body.error, "exception");
});

test("body como string JSON (algunos clientes lo mandan así) se parsea igual", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  process.env.MP_LINK_STARTER = "https://mpago.la/starter";
  const checkout = require("./checkout");
  const r = res();
  await checkout(req(JSON.stringify({ plan: "starter" })), r);
  assert.equal(r.statusCode, 200);
});

test("body corrupto (JSON inválido) no revienta el handler", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  delete process.env.MP_LINK_PRO;
  const checkout = require("./checkout");
  const r = res();
  await checkout(req("{esto no es json"), r);
  assert.equal(r.statusCode, 400);   // plan vacío -> plan_invalido, no un 500
});

test("el freno por IP corta después de varios intentos seguidos", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  delete process.env.MP_LINK_PRO;
  const checkout = require("./checkout");
  const misma = { method: "POST", headers: { host: "x", "x-forwarded-for": "55.55.55.55" }, body: { plan: "pro" } };
  const codigos = [];
  for (let i = 0; i < 12; i++) {
    const r = res();
    await checkout(misma, r);
    codigos.push(r.statusCode);
  }
  assert.ok(codigos.includes(429), `nunca frenó: ${codigos}`);
});

// ---------------------------------------------------------------------------
//  Aviso de INTENCIÓN de compra (mail al dueño cuando alguien aprieta Comprar)
//
//  Lo que se protege acá, en orden de lo que más caro sale si se rompe:
//   1. que el aviso NUNCA cueste una venta (sin clave, Resend caído, o lento);
//   2. que un indeciso que toca cinco veces mande UN mail, no cinco — si no,
//      el aviso se vuelve ruido y se archiva sin leer, o sea deja de existir;
//   3. que el aviso salga TAMBIÉN cuando MercadoPago falla, que es justo el
//      caso que hay que enterarse.
// ---------------------------------------------------------------------------

// Un request con IP fija: la idempotencia es por IP, así que el helper `req()`
// —que inventa una IP nueva cada vez, a propósito, para no chocar con el rate
// limit— no sirve para estos casos.
function reqIP(ip, body) {
  return { method: "POST", headers: { host: "mvkobranzaia.com", "x-forwarded-for": ip }, body };
}

/** Mockea fetch separando los envíos a Resend de las llamadas a MercadoPago. */
function mockConResend(respuestaMP) {
  const mails = [];
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend.com")) {
      mails.push(JSON.parse(opts.body));
      return { ok: true, json: async () => ({ id: "re_1" }) };
    }
    return respuestaMP(url, opts);
  });
  return mails;
}

const mpOk = async () => ({ ok: true, json: async () => ({ init_point: "https://mp/pagar/xyz" }) });

test("aviso: sin RESEND_API_KEY no manda nada y el checkout funciona igual", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  delete process.env.RESEND_API_KEY;
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.0.1", { plan: "pro" }), r);
  assert.equal(r.statusCode, 200, "el checkout tiene que andar sin la clave de mail");
  assert.equal(r.body.url, "https://mp/pagar/xyz");
  assert.equal(mails.length, 0, "sin clave no se puede haber mandado ningún mail");
});

test("aviso: con la clave manda UN mail al dueño, con plan y monto", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  process.env.MP_CURRENCY = "UYU";
  process.env.MP_TASA_UYU = "40";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.1.1", { plan: "pro" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(mails.length, 1);
  assert.deepEqual(mails[0].to, ["vieraschiavi@gmail.com"], "el aviso va al dueño, no al cliente");
  assert.match(mails[0].subject, /Intenci/i);
  assert.match(mails[0].text, /Plan:\s+pro/, "el mail tiene que decir QUÉ plan");
  assert.match(mails[0].text, /349/, "el mail tiene que decir el precio en USD");
  assert.match(mails[0].text, new RegExp(String(Math.round(349 * 40))),
    "y también lo que se cobra de verdad, en pesos");
});

test("aviso: el mismo indeciso tocando cinco veces manda UN solo mail", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  for (let i = 0; i < 5; i++) await checkout(reqIP("10.9.2.1", { plan: "pro" }), res());
  assert.equal(mails.length, 1, `mandó ${mails.length} mails por una sola intención`);
});

test("aviso: otra persona SÍ genera su propio mail", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  await checkout(reqIP("10.9.3.1", { plan: "pro" }), res());
  await checkout(reqIP("10.9.3.2", { plan: "pro" }), res());
  assert.equal(mails.length, 2, "el freno es por persona, no global: si no, el segundo cliente es invisible");
});

test("aviso: el mismo que compara DOS planes distintos avisa de los dos", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  await checkout(reqIP("10.9.4.1", { plan: "pro" }), res());
  await checkout(reqIP("10.9.4.1", { plan: "basico" }), res());
  assert.equal(mails.length, 2, "cambiar de plan es información distinta, no una repetición");
});

test("aviso: si Resend falla, la venta sigue viva", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  mockFetch(async (url) => {
    if (String(url).includes("resend.com")) throw new Error("Resend caído");
    return mpOk();
  });
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.5.1", { plan: "pro" }), r);
  assert.equal(r.statusCode, 200, "un mail que falla NO puede tumbar el checkout");
  assert.equal(r.body.url, "https://mp/pagar/xyz");
});

test("aviso: sale TAMBIÉN cuando MercadoPago rechaza — es el caso que más importa saber", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  const mails = mockConResend(async () => ({ ok: false, status: 400, json: async () => ({ error: "bad" }) }));
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.6.1", { plan: "pro" }), r);
  assert.equal(r.statusCode, 502, "MercadoPago rechazó: el checkout devuelve error");
  assert.equal(mails.length, 1, "alguien quiso comprar y el sistema no lo dejó: eso hay que saberlo");
});

test("aviso: sin medio de pago configurado igual avisa (si no, esa venta perdida es invisible)", async () => {
  delete process.env.MP_ACCESS_TOKEN;
  delete process.env.MP_LINK_PRO;
  process.env.RESEND_API_KEY = "re_test";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.7.1", { plan: "pro" }), r);
  assert.equal(r.statusCode, 503);
  assert.equal(mails.length, 1);
});

test("aviso: un plan inválido no dispara mail (es ruido, no una venta)", async () => {
  process.env.RESEND_API_KEY = "re_test";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.8.1", { plan: "no-existe" }), r);
  assert.equal(r.statusCode, 400);
  assert.equal(mails.length, 0);
});

test("aviso: AVISO_INTENCION=0 lo apaga SIN apagar los mails de licencia", async () => {
  // El interruptor tiene que ser propio: RESEND_API_KEY no sirve, porque es la
  // misma clave con la que el webhook le manda la licencia al comprador.
  // Apagarla para no recibir avisos dejaría a los clientes sin licencia.
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  process.env.AVISO_INTENCION = "0";
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  const r = res();
  await checkout(reqIP("10.9.9.1", { plan: "pro" }), r);
  assert.equal(r.statusCode, 200, "apagar el aviso no puede tocar el checkout");
  assert.equal(mails.length, 0, "con AVISO_INTENCION=0 no se manda el aviso");
  assert.ok(process.env.RESEND_API_KEY, "y la clave de Resend sigue puesta para las licencias");
});

test("aviso: encendido por defecto (no hace falta configurar nada para tenerlo)", async () => {
  process.env.MP_ACCESS_TOKEN = "TEST-token";
  process.env.RESEND_API_KEY = "re_test";
  delete process.env.AVISO_INTENCION;
  const mails = mockConResend(mpOk);
  const checkout = require("./checkout");
  await checkout(reqIP("10.9.10.1", { plan: "pro" }), res());
  assert.equal(mails.length, 1);
});
