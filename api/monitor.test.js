// © 2026 Martín Viera. Todos los derechos reservados.

// El monitor del negocio y la credencial que lo protege.
//
// Dos cosas que se rompen en silencio y acá se atan:
//
//   * la sal y el hash del dueño están duplicados en Python y en JS. Si se
//     rotan de un lado y no del otro, el monitor deja de abrir (o peor: sigue
//     abriendo con el código viejo);
//   * el resumen suma plata. Un error de signo o un campo mal leído no rompe
//     nada, solo muestra un número equivocado — que es el peor resultado
//     posible en la pantalla que dice cuánto ganaste.
const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

const auth = require("./_owner_auth");
const { resumir } = require("./monitor");

const RAIZ = path.join(__dirname, "..");

// ---------------------------------------------------------------------------
// La credencial no puede desincronizarse entre lenguajes
// ---------------------------------------------------------------------------
test("la sal, el hash y los parámetros son los mismos que en kobra/owner.py",
  () => {
    const salida = execFileSync("python3", ["-c", `
from kobra import owner as ko
import json
print(json.dumps({"sal": ko._SAL.hex(), "hash": ko._HASH.hex(),
                  "N": ko._N, "r": ko._R, "p": ko._P,
                  "dklen": ko._DKLEN, "maxmem": ko._MAXMEM,
                  "email": ko.EMAIL}))
`], { cwd: RAIZ, encoding: "utf8" });
    const py = JSON.parse(salida);

    assert.equal(auth.SAL.toString("hex"), py.sal,
      "la sal de _owner_auth.js quedó vieja respecto de kobra/owner.py");
    assert.equal(auth.HASH.toString("hex"), py.hash,
      "el hash de _owner_auth.js quedó viejo: el código rotó y acá no");
    assert.equal(auth.EMAIL, py.email);
    assert.equal(auth.PARAMS.N, py.N);
    assert.equal(auth.PARAMS.r, py.r);
    assert.equal(auth.PARAMS.p, py.p);
    assert.equal(auth.PARAMS.maxmem, py.maxmem);
    assert.equal(auth.DKLEN, py.dklen);
  });

test("scrypt da lo mismo en Node que en Python", () => {
  // Si esto falla, la credencial del dueño abre en un lenguaje y no en el
  // otro, aunque la sal y el hash coincidan.
  const codigo = "PRUEBACRUZADAABCDEFGH2345";
  const salida = execFileSync("python3", ["-c", `
import hashlib
from kobra import owner as ko
print(hashlib.scrypt(${JSON.stringify(codigo)}.encode(), salt=ko._SAL,
                     n=ko._N, r=ko._R, p=ko._P, dklen=ko._DKLEN,
                     maxmem=ko._MAXMEM).hex())
`], { cwd: RAIZ, encoding: "utf8" }).trim();
  const crypto = require("crypto");
  const enNode = crypto.scryptSync(codigo, auth.SAL, auth.DKLEN, auth.PARAMS)
    .toString("hex");
  assert.equal(enNode, salida);
});

test("una credencial mal formada no entra", () => {
  for (const malo of ["", "sinseparador", "|solocodigo", "solomail|",
                      null, undefined, 42, {}]) {
    assert.equal(auth.esOwner(malo), false, `entró con ${JSON.stringify(malo)}`);
  }
});

test("el mail correcto con código equivocado no entra", () => {
  assert.equal(auth.esOwner(`${auth.EMAIL}|ABCDEFGHJKLMNPQRSTUVWXY23`), false);
});

test("el monitor responde 401 sin credencial", async () => {
  const handler = require("./monitor");
  let codigo = null, cuerpo = null;
  const res = { status(c) { codigo = c; return this; },
                json(b) { cuerpo = b; return this; } };
  await handler({ headers: {}, query: {} }, res);
  assert.equal(codigo, 401);
  assert.equal(cuerpo.error, "credencial_invalida");
});

// ---------------------------------------------------------------------------
// Las cuentas
// ---------------------------------------------------------------------------
const pago = (over = {}) => ({
  id: 1, transaction_amount: 690, currency_id: "UYU",
  date_approved: "2026-03-15T10:00:00Z",
  metadata: { plan: "starter" },
  payer: { email: "a@b.com" },
  transaction_details: { net_received_amount: 655.5 },
  ...over,
});

test("suma bruto, neto y comisión sin inventar la comisión", () => {
  const r = resumir([pago(), pago({ id: 2, transaction_amount: 99,
                                    metadata: { plan: "basico" },
                                    payer: { email: "c@d.com" },
                                    transaction_details: { net_received_amount: 94 } })]);
  assert.equal(r.ventas, 2);
  assert.equal(r.bruto, 789);
  assert.equal(r.neto, 749.5);
  // La comisión es bruto − neto acreditado por MercadoPago, no un porcentaje
  // estimado por nosotros.
  assert.equal(r.comision, 39.5);
});

test("cuenta clientes únicos, no pagos", () => {
  // El mismo comprador que compra dos veces es UN cliente. Contar pagos acá
  // inflaría el número de clientes justo en la pantalla que se mira para
  // decidir si el negocio crece.
  const r = resumir([pago(), pago({ id: 2 })]);
  assert.equal(r.ventas, 2);
  assert.equal(r.clientes, 1);
});

test("agrupa por plan y por mes", () => {
  const r = resumir([
    pago(),
    pago({ id: 2, metadata: { plan: "logistica" }, transaction_amount: 79,
           date_approved: "2026-04-02T10:00:00Z",
           transaction_details: { net_received_amount: 75 } }),
  ]);
  assert.deepEqual(r.por_plan.map((p) => p.plan), ["starter", "logistica"]);
  assert.deepEqual(r.por_mes.map((m) => m.mes), ["2026-03", "2026-04"]);
});

test("un pago sin plan en la metadata no se pierde", () => {
  // Los links MP_LINK_* no llevan metadata. Ese dinero entró igual y tiene
  // que aparecer, no desaparecer del total.
  const r = resumir([pago({ metadata: null })]);
  assert.equal(r.bruto, 690);
  assert.equal(r.por_plan[0].plan, "sin_plan");
});

test("si MercadoPago no informa el neto, no se inventa una comisión", () => {
  const r = resumir([pago({ transaction_details: undefined })]);
  assert.equal(r.bruto, 690);
  assert.equal(r.neto, 690);
  assert.equal(r.comision, 0, "se inventó una comisión que MP no informó");
});

test("sin ventas devuelve ceros y no rompe", () => {
  const r = resumir([]);
  assert.equal(r.ventas, 0);
  assert.equal(r.clientes, 0);
  assert.equal(r.bruto, 0);
  assert.equal(r.moneda, null);
  assert.deepEqual(r.por_plan, []);
});

// ---------------------------------------------------------------------------
// Los pedidos de demo
// ---------------------------------------------------------------------------
const ECFG = { EDGE_CONFIG_ID: "ecfg_prueba", VC_API_TOKEN: "vt_prueba",
               VC_TEAM_ID: "team_prueba" };

function cargarMonitor(almacen) {
  for (const k of Object.keys(ECFG)) {
    if (almacen) process.env[k] = ECFG[k];
    else delete process.env[k];
  }
  delete require.cache[require.resolve("./monitor")];
  delete require.cache[require.resolve("./_pedidos")];
  return require("./monitor");
}

test("sin Edge Config la lista dice 'no disponible', no 'nadie pidió nada'",
  async () => {
    // Confundir las dos cosas hace leer una lista vacía como si el formulario
    // no captara a nadie, cuando lo que falta es dónde guardar.
    const m = cargarMonitor(false);
    const d = await m.demosPedidas();
    assert.equal(d.disponible, false);
    assert.equal(d.total, 0);
    assert.ok(d.motivo, "no explica por qué está vacía");
  });

test("lista los pedidos de demo del más nuevo al más viejo", async () => {
  const m = cargarMonitor(true);
  const anterior = global.fetch;
  global.fetch = async () => ({ ok: true, json: async () => ({ value: [
    { id: "a1", fecha: "2026-01-01T00:00:00.000Z", email: "vieja@a.com" },
    { id: "b2", fecha: "2026-09-01T00:00:00.000Z", email: "nueva@a.com" },
  ] }) });
  try {
    const d = await m.demosPedidas();
    assert.equal(d.disponible, true);
    assert.equal(d.total, 2);
    assert.equal(d.lista[0].email, "nueva@a.com",
      "el pedido más reciente tiene que estar primero");
  } finally {
    global.fetch = anterior;
  }
});

test("los pedidos de demo se ven aunque falte el token de MercadoPago",
  async () => {
    // El dato de prospectos sirve ANTES de que haya una sola venta: esconderlo
    // detrás del token de pagos lo haría inútil justo al principio.
    //
    // La credencial del dueño no se puede tipear en un test (el código no está
    // en el repo, a propósito), así que se reemplaza `exigirOwner` por uno que
    // deja pasar. Lo que se prueba acá es el cuerpo de la respuesta, no la
    // puerta: la puerta la prueban los cuatro tests de credencial de arriba.
    const ruta = require.resolve("./_owner_auth");
    const real = require(ruta);
    require.cache[ruta].exports = { ...real, exigirOwner: () => false };
    const mpAnterior = process.env.MP_ACCESS_TOKEN;
    delete process.env.MP_ACCESS_TOKEN;
    const anterior = global.fetch;
    global.fetch = async () => ({ ok: true, json: async () => ({ value: [
      { id: "a1", fecha: "2026-09-01T00:00:00.000Z", email: "uno@a.com" },
    ] }) });
    let codigo = null, cuerpo = null;
    const res = { status(c) { codigo = c; return this; },
                  json(b) { cuerpo = b; return this; } };
    try {
      const m = cargarMonitor(true);
      await m({ headers: {}, query: {} }, res);
      assert.equal(codigo, 503, "sin MP_ACCESS_TOKEN el monitor responde 503");
      assert.equal(cuerpo.demos.total, 1,
        "el 503 de pagos se llevó puesta la lista de prospectos");
      assert.equal(cuerpo.demos.lista[0].email, "uno@a.com");
    } finally {
      global.fetch = anterior;
      require.cache[ruta].exports = real;
      if (mpAnterior) process.env.MP_ACCESS_TOKEN = mpAnterior;
      delete require.cache[require.resolve("./monitor")];
    }
  });

test("la pantalla del monitor escapa lo que escribió un desconocido", () => {
  // Nombre, empresa y mail de un pedido de demo los escribe cualquiera que
  // entre a /pedir-demo. El servidor les saca los saltos de línea, no los
  // signos de menor: pintarlos crudos sería un XSS en la pantalla que muestra
  // la facturación.
  const fs = require("node:fs");
  const html = fs.readFileSync(path.join(RAIZ, "landing/monitor.html"), "utf8");
  const bloque = html.slice(html.indexOf("function bloqueDemos"),
                            html.indexOf("function pintar"));
  assert.ok(bloque.length > 0, "desapareció el bloque de pedidos de demo");
  for (const campo of ["x.nombre", "x.empresa", "x.email", "x.pais", "x.id"]) {
    assert.ok(bloque.includes("esc(" + campo + ")"),
      `${campo} se pinta sin escapar en landing/monitor.html`);
  }
});
