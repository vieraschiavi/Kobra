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
beforeEach(() => { envOriginal = { ...process.env }; delete require.cache[require.resolve("./checkout")]; });
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
// Aviso de intención de compra
// ---------------------------------------------------------------------------
// `webhook-mercadopago.js` ya avisa cuando el pago SE CONCRETA. Esto avisa
// antes: cuando alguien toca Comprar. Sirve para saber que hay demanda real
// sin mirar el panel de MercadoPago, y para decidir cuándo pagar
// infraestructura en vez de pagarla por las dudas.
//
// Lo que se protege acá es sobre todo lo segundo: que el aviso NUNCA pueda
// costar una venta.
function conMercadoPagoOk(enviados, opciones) {
  const o = opciones || {};
  mockFetch(async (url, opts) => {
    if (String(url).includes("resend.com")) {
      if (o.resendRevienta) throw new Error("Resend caído");
      enviados.push(JSON.parse(opts.body));
      return { ok: true, text: async () => "", json: async () => ({}) };
    }
    if (o.mpRechaza) return { ok: false, status: 400, json: async () => ({ message: "no" }) };
    return { ok: true, status: 200, json: async () => ({ init_point: "https://mp/pagar" }) };
  });
}

test("avisa por mail cuando alguien toca Comprar", async () => {
  process.env.MP_ACCESS_TOKEN = "tok-de-prueba";
  process.env.RESEND_API_KEY = "re_prueba";
  const enviados = [];
  conMercadoPagoOk(enviados);
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "pro" }), r);

  assert.equal(r.statusCode, 200);
  assert.equal(r.body.url, "https://mp/pagar");
  assert.equal(enviados.length, 1, "no llegó el aviso de intención");
  assert.match(enviados[0].subject, /Intenci[óo]n/i);
  assert.match(enviados[0].text, /pro/i, "el aviso no dice qué plan");
  // Que quede claro que NO es una venta: confundir las dos cosas es peor que
  // no avisar — lo llevaría a activar infraestructura por un click.
  assert.match(enviados[0].text, /INTENCI[ÓO]N, no una venta/i);
});

test("si el aviso falla, el comprador igual recibe su link de pago", async () => {
  // La regla que importa: perder una venta por no poder mandar un mail sería
  // exactamente al revés de lo que se busca.
  process.env.MP_ACCESS_TOKEN = "tok-de-prueba";
  process.env.RESEND_API_KEY = "re_prueba";
  const errorOriginal = console.error;
  console.error = () => {};
  try {
    conMercadoPagoOk([], { resendRevienta: true });
    const checkout = require("./checkout");
    const r = res();
    await checkout(req({ plan: "pro" }), r);
    assert.equal(r.statusCode, 200, "el checkout se rompió por culpa del aviso");
    assert.equal(r.body.url, "https://mp/pagar");
  } finally {
    console.error = errorOriginal;
  }
});

test("sin RESEND_API_KEY el checkout funciona igual, sin avisar", async () => {
  process.env.MP_ACCESS_TOKEN = "tok-de-prueba";
  delete process.env.RESEND_API_KEY;
  const enviados = [];
  conMercadoPagoOk(enviados);
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "pro" }), r);
  assert.equal(r.statusCode, 200);
  assert.equal(enviados.length, 0);
});

test("un plan inválido no dispara ningún aviso", async () => {
  // Si no, el buzón se llena de ruido de bots tanteando la API.
  process.env.MP_ACCESS_TOKEN = "tok-de-prueba";
  process.env.RESEND_API_KEY = "re_prueba";
  const enviados = [];
  conMercadoPagoOk(enviados);
  const checkout = require("./checkout");
  const r = res();
  await checkout(req({ plan: "no-existe" }), r);
  assert.equal(r.statusCode, 400);
  assert.equal(enviados.length, 0);
});

test("si MercadoPago rechaza la preferencia, tampoco se avisa", async () => {
  // Avisar de un click que terminó en error, y no en una pantalla de pago, es
  // avisar de algo que no pasó.
  process.env.MP_ACCESS_TOKEN = "tok-de-prueba";
  process.env.RESEND_API_KEY = "re_prueba";
  const errorOriginal = console.error;
  console.error = () => {};
  try {
    const enviados = [];
    conMercadoPagoOk(enviados, { mpRechaza: true });
    const checkout = require("./checkout");
    const r = res();
    await checkout(req({ plan: "pro" }), r);
    assert.equal(r.statusCode, 502);
    assert.equal(enviados.length, 0,
      "avisó de una compra que nunca llegó a la pantalla de pago");
  } finally {
    console.error = errorOriginal;
  }
});
