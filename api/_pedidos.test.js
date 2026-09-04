// © 2026 Martín Viera. Todos los derechos reservados.

// El registro durable de pedidos de demo.
//
// Lo que se prueba acá no es "guarda bien": es que NUNCA le cueste un pedido a
// nadie. El módulo existe porque un prospecto quedaba solo en un `console.error`
// de una función serverless, así que un registro que rompa el formulario al
// fallar sería peor que el problema que vino a resolver.
const { test } = require("node:test");
const assert = require("node:assert");

const ENTORNO = { EDGE_CONFIG_ID: "ecfg_prueba", VC_API_TOKEN: "vt_prueba",
                  VC_TEAM_ID: "team_prueba" };

/** Recarga el módulo con (o sin) el Edge Config configurado. */
function cargar(configurado) {
  for (const k of Object.keys(ENTORNO)) {
    if (configurado) process.env[k] = ENTORNO[k];
    else delete process.env[k];
  }
  delete require.cache[require.resolve("./_pedidos")];
  return require("./_pedidos");
}

/** Un doble de `fetch` con un Edge Config en memoria. */
function edgeConfigFalso(estado = {}) {
  const registro = { guardado: estado.valor ?? null, escrituras: 0 };
  const anterior = global.fetch;
  global.fetch = async (url, opts) => {
    if (!opts || opts.method !== "PATCH") {
      if (estado.leerFalla) return { ok: false, status: 500 };
      return { ok: true, json: async () => ({ value: registro.guardado }) };
    }
    registro.escrituras += 1;
    if (estado.escribirFalla) return { ok: false, status: 413 };
    registro.guardado = JSON.parse(opts.body).items[0].value;
    return { ok: true, json: async () => ({}) };
  };
  registro.restaurar = () => { global.fetch = anterior; };
  return registro;
}

const PEDIDO = { nombre: "Ana Pérez", email: "ana@empresa.com",
                 empresa: "Cobranzas SA", pais: "Uruguay" };

test("sin Edge Config no explota: devuelve null y no toca la red", async () => {
  const p = cargar(false);
  const anterior = global.fetch;
  global.fetch = async () => { throw new Error("no debió llamar a la red"); };
  try {
    assert.equal(p.disponible(), false);
    assert.equal(await p.guardar(PEDIDO), null);
    assert.deepEqual(await p.listar(), []);
  } finally {
    global.fetch = anterior;
  }
});

test("guarda el pedido y lo devuelve al listarlo", async () => {
  const p = cargar(true);
  const ec = edgeConfigFalso();
  try {
    const id = await p.guardar(PEDIDO);
    assert.ok(id, "no devolvió id");
    const lista = await p.listar();
    assert.equal(lista.length, 1);
    assert.equal(lista[0].email, PEDIDO.email);
    assert.equal(lista[0].empresa, PEDIDO.empresa);
    assert.equal(lista[0].id, id);
    assert.ok(lista[0].fecha, "sin fecha no se sabe cuándo se pidió");
  } finally {
    ec.restaurar();
  }
});

test("cada pedido lleva un id distinto: sirve para atribuir una copia", async () => {
  const p = cargar(true);
  const ec = edgeConfigFalso();
  try {
    const ids = new Set();
    for (let i = 0; i < 20; i++) ids.add(await p.guardar(PEDIDO));
    assert.equal(ids.size, 20, "dos demos con el mismo id no se pueden distinguir");
  } finally {
    ec.restaurar();
  }
});

test("los pedidos se acumulan, no se pisan", async () => {
  const p = cargar(true);
  const ec = edgeConfigFalso();
  try {
    await p.guardar({ ...PEDIDO, email: "uno@a.com" });
    await p.guardar({ ...PEDIDO, email: "dos@a.com" });
    const mails = (await p.listar()).map((x) => x.email);
    assert.deepEqual(mails, ["uno@a.com", "dos@a.com"]);
  } finally {
    ec.restaurar();
  }
});

test("si la escritura falla, devuelve null en vez de levantar", async () => {
  const p = cargar(true);
  const ec = edgeConfigFalso({ escribirFalla: true });
  try {
    assert.equal(await p.guardar(PEDIDO), null);
  } finally {
    ec.restaurar();
  }
});

test("si la lectura falla, listar devuelve [] en vez de levantar", async () => {
  const p = cargar(true);
  const ec = edgeConfigFalso({ leerFalla: true });
  try {
    assert.deepEqual(await p.listar(), []);
  } finally {
    ec.restaurar();
  }
});

test("si la red explota, no se propaga la excepción", async () => {
  const p = cargar(true);
  const anterior = global.fetch;
  global.fetch = async () => { throw new Error("ECONNRESET"); };
  try {
    assert.equal(await p.guardar(PEDIDO), null);
    assert.deepEqual(await p.listar(), []);
  } finally {
    global.fetch = anterior;
  }
});

test("un valor corrupto en el store se lee como lista vacía", async () => {
  // Si alguien edita el Edge Config a mano y deja un objeto donde iba una
  // lista, `listar()` tiene que devolver [] y no romper el monitor entero.
  const p = cargar(true);
  const ec = edgeConfigFalso({ valor: { no: "es una lista" } });
  try {
    assert.deepEqual(await p.listar(), []);
  } finally {
    ec.restaurar();
  }
});

test("la poda tira los más VIEJOS y respeta el presupuesto de bytes", () => {
  // Podar por cantidad obligaría a adivinar cuánto ocupa un pedido; el tope
  // real del Edge Config es de bytes, y pasarlo no pierde un pedido: deja de
  // escribirse la lista entera.
  const p = cargar(true);
  const muchos = Array.from({ length: 400 }, (_, i) => ({
    id: String(i), fecha: "2026-09-04T00:00:00.000Z",
    nombre: "Nombre Largo De Prueba", email: `p${i}@empresa-de-prueba.com`,
    empresa: "Empresa Con Nombre Largo SA", pais: "Uruguay",
  }));
  const podada = p.podar(muchos);
  assert.ok(Buffer.byteLength(JSON.stringify(podada), "utf8") <= p.MAX_BYTES,
    "la lista podada sigue sin entrar en el store");
  assert.ok(podada.length < muchos.length, "no podó nada");
  // El último pedido es el que más importa: es el más reciente.
  assert.equal(podada[podada.length - 1].id, "399");
});

test("una lista chica no se poda", () => {
  const p = cargar(true);
  const pocos = [{ id: "a" }, { id: "b" }];
  assert.deepEqual(p.podar(pocos), pocos);
});
