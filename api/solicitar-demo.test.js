// © 2026 Martín Viera. Todos los derechos reservados.

// El pedido de demo, que reemplaza a la demo pública.
//
// Lo que se protege acá no es el formulario: es la decisión de no publicar el
// artefacto de ingeniería. `dashboard_estatico/modelo_web.js` es el modelo
// ProbPago ENTRENADO —tipo, variables y parámetros de escala— y `guiones.js`
// son 41 KB de guiones de negociación. Servirlos era regalar el núcleo del
// producto a cualquiera que supiera la URL.
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const RAIZ = path.join(__dirname, "..");

function res() {
  return {
    statusCode: null, body: null, cabeceras: {},
    setHeader(k, v) { this.cabeceras[k] = v; },
    status(c) { this.statusCode = c; return this; },
    json(b) { this.body = b; return this; },
  };
}
const req = (body, extra = {}) => ({
  method: "POST", body, headers: {}, socket: { remoteAddress: "1.2.3.4" },
  ...extra,
});

const COMPLETO = { nombre: "Ana Pérez", empresa: "Cobranzas SA",
                   pais: "Uruguay", email: "ana@empresa.com" };

const ECFG = { EDGE_CONFIG_ID: "ecfg_prueba", VC_API_TOKEN: "vt_prueba",
               VC_TEAM_ID: "team_prueba" };

function cargar({ almacen = false } = {}) {
  for (const k of Object.keys(ECFG)) {
    if (almacen) process.env[k] = ECFG[k];
    else delete process.env[k];
  }
  delete require.cache[require.resolve("./solicitar-demo")];
  delete require.cache[require.resolve("./_ratelimit")];
  delete require.cache[require.resolve("./_pedidos")];
  return require("./solicitar-demo");
}

/**
 * Doble de `fetch` que separa las dos salidas del handler: lo que se guarda
 * (Edge Config) de lo que se manda (Resend). Sin separarlas no se puede probar
 * lo único que importa acá — que el pedido queda guardado AUNQUE el mail falle.
 */
function red({ mailFalla = false } = {}) {
  const reg = { guardado: null, mails: [] };
  const anterior = global.fetch;
  global.fetch = async (url, opts) => {
    if (String(url).includes("api.resend.com")) {
      reg.mails.push(JSON.parse(opts.body));
      if (mailFalla) return { ok: false, status: 500, text: async () => "boom" };
      return { ok: true, json: async () => ({}) };
    }
    if (opts && opts.method === "PATCH") {
      reg.guardado = JSON.parse(opts.body).items[0].value;
      return { ok: true, json: async () => ({}) };
    }
    return { ok: true, json: async () => ({ value: reg.guardado }) };
  };
  reg.restaurar = () => { global.fetch = anterior; };
  return reg;
}

// ---------------------------------------------------------------------------
// La decisión de fondo
// ---------------------------------------------------------------------------
test("la demo no se despliega: está excluida en .vercelignore", () => {
  // No alcanza con sacar la ruta `/demo/` de vercel.json — Vercel sirve los
  // archivos del repo por su ruta real, y `/dashboard_estatico/modelo_web.js`
  // seguía respondiendo 200 con el modelo adentro. Se comprobó en vivo.
  const ignore = fs.readFileSync(path.join(RAIZ, ".vercelignore"), "utf8");
  const lineas = ignore.split("\n").map((l) => l.trim());
  assert.ok(lineas.includes("dashboard_estatico"),
    "dashboard_estatico volvió a subir al deploy: el modelo entrenado queda " +
    "descargable por su ruta directa");
});

test("vercel.json no publica ninguna ruta de la demo", () => {
  const cfg = JSON.parse(fs.readFileSync(path.join(RAIZ, "vercel.json"), "utf8"));
  const rutas = [...cfg.rewrites, ...cfg.redirects].map((r) => r.source);
  const deDemo = rutas.filter((r) => r.startsWith("/demo"));
  assert.deepEqual(deDemo, [], `la demo volvió a publicarse: ${deDemo}`);
  assert.ok(rutas.includes("/pedir-demo"), "no hay dónde pedir la demo");
});

test("la landing no ofrece la demo abierta y sí el pedido", () => {
  for (const rel of ["landing/index.html", "landing/en/index.html",
                     "landing/pt/index.html"]) {
    const html = fs.readFileSync(path.join(RAIZ, rel), "utf8");
    assert.ok(!html.includes("/demo/"), `${rel} sigue enlazando la demo pública`);
    assert.ok(html.includes("/pedir-demo"), `${rel} no ofrece pedir una demo`);
    // El registro viejo guardaba los datos en localStorage y no los mandaba a
    // ningún lado: cero leads y la demo se abría igual por la URL.
    assert.ok(!html.includes("kobra_reg"),
      `${rel} conserva el registro que no avisaba a nadie`);
  }
});

// ---------------------------------------------------------------------------
// El endpoint
// ---------------------------------------------------------------------------
test("sin los campos obligatorios no se manda nada", async () => {
  const h = cargar();
  for (const falta of ["nombre", "empresa", "pais", "email"]) {
    const datos = { ...COMPLETO, [falta]: "" };
    const r = res();
    await h(req(datos), r);
    assert.equal(r.statusCode, 400, `pasó sin ${falta}`);
    assert.deepEqual(r.body.campos, [falta]);
  }
});

test("un mail sin arroba se rechaza", async () => {
  const h = cargar();
  const r = res();
  await h(req({ ...COMPLETO, email: "no-es-un-mail" }), r);
  assert.equal(r.statusCode, 400);
  assert.equal(r.body.error, "email_invalido");
});

test("acepta direcciones legítimas que una regex estricta rechazaría", () => {
  const { pareceMail } = cargar();
  for (const bueno of ["ana+demo@sub.empresa.com.uy", "a@b.io",
                       "nombre.apellido@cobranzas-sa.com"]) {
    assert.ok(pareceMail(bueno), `rechazó ${bueno}`);
  }
});

test("los saltos de línea no se cuelan en el asunto del mail", () => {
  // Sin esto, un nombre con \n inyecta cabeceras en el correo.
  const { campo } = cargar();
  assert.equal(campo("Ana\r\nBcc: otro@mail.com", 120), "Ana Bcc: otro@mail.com");
});

test("los campos se recortan: nadie manda un mail de 1 MB", () => {
  const { campo } = cargar();
  assert.equal(campo("x".repeat(9000), 120).length, 120);
});

test("solo POST", async () => {
  const h = cargar();
  const r = res();
  await h({ method: "GET", headers: {}, body: {} }, r);
  assert.equal(r.statusCode, 405);
});

test("sin RESEND_API_KEY avisa y NO pierde al prospecto", async () => {
  const h = cargar();
  delete process.env.RESEND_API_KEY;
  const r = res();
  await h(req(COMPLETO), r);
  assert.equal(r.statusCode, 503);
  // La respuesta trae la dirección directa: el que quería la demo puede
  // escribir igual en vez de quedarse con un error y nada más.
  assert.equal(r.body.contacto, h.DESTINO);
});

test("el pedido llega al mail del dueño, con reply_to del prospecto", async () => {
  const h = cargar();
  process.env.RESEND_API_KEY = "re_prueba";
  let enviado = null;
  const fetchOriginal = global.fetch;
  global.fetch = async (url, opts) => {
    enviado = JSON.parse(opts.body);
    return { ok: true, json: async () => ({}) };
  };
  try {
    const r = res();
    await h(req({ ...COMPLETO, mensaje: "12.000 cuentas, 6 gestores" }), r);
    assert.equal(r.statusCode, 200);
    assert.deepEqual(enviado.to, [h.DESTINO]);
    // Contestar el mail le responde al prospecto, sin copiar la dirección.
    assert.equal(enviado.reply_to, COMPLETO.email);
    for (const dato of [COMPLETO.nombre, COMPLETO.empresa, COMPLETO.pais,
                        COMPLETO.email, "12.000 cuentas"]) {
      assert.ok(enviado.text.includes(dato), `el mail no dice ${dato}`);
    }
    assert.ok(enviado.subject.includes(COMPLETO.empresa));
  } finally {
    global.fetch = fetchOriginal;
  }
});

test("si Resend falla, el pedido queda en el log y se ofrece el mail directo",
  async () => {
    const h = cargar();
    process.env.RESEND_API_KEY = "re_prueba";
    const fetchOriginal = global.fetch;
    const errorOriginal = console.error;
    let logueado = "";
    console.error = (...a) => { logueado += a.join(" "); };
    global.fetch = async () => ({ ok: false, status: 500, text: async () => "boom" });
    try {
      const r = res();
      await h(req(COMPLETO), r);
      assert.equal(r.statusCode, 502);
      assert.equal(r.body.contacto, h.DESTINO);
      assert.ok(logueado.includes(COMPLETO.email),
        "el pedido se perdió: no quedó ni en el log");
    } finally {
      global.fetch = fetchOriginal;
      console.error = errorOriginal;
    }
  });

test("el freno por IP corta una ráfaga", async () => {
  const h = cargar();
  process.env.RESEND_API_KEY = "re_prueba";
  const fetchOriginal = global.fetch;
  global.fetch = async () => ({ ok: true, json: async () => ({}) });
  try {
    let frenado = null;
    for (let i = 0; i < 8; i++) {
      const r = res();
      await h(req(COMPLETO), r);
      if (r.statusCode === 429) { frenado = r; break; }
    }
    assert.ok(frenado, "un formulario público sin freno es un amplificador de spam");
    assert.ok(frenado.cabeceras["Retry-After"], "no dice cuándo reintentar");
  } finally {
    global.fetch = fetchOriginal;
  }
});

// ---------------------------------------------------------------------------
// El pedido no se pierde: queda guardado antes de intentar el mail
// ---------------------------------------------------------------------------
test("el pedido se guarda ANTES de mandar el mail", async () => {
  // El orden es la regla. Guardando después de un envío exitoso, el prospecto
  // se pierde exactamente cuando el correo está caído — el único momento en
  // que el registro hace falta.
  const h = cargar({ almacen: true });
  process.env.RESEND_API_KEY = "re_prueba";
  const orden = [];
  const anterior = global.fetch;
  global.fetch = async (url, opts) => {
    if (String(url).includes("api.resend.com")) {
      orden.push("mail");
      return { ok: true, json: async () => ({}) };
    }
    if (opts && opts.method === "PATCH") orden.push("guardar");
    return { ok: true, json: async () => ({ value: [] }) };
  };
  try {
    const r = res();
    await h(req(COMPLETO), r);
    assert.equal(r.statusCode, 200);
    assert.deepEqual(orden, ["guardar", "mail"],
      "se mandó el mail antes de guardar: un SMTP caído pierde al prospecto");
  } finally {
    global.fetch = anterior;
  }
});

test("si Resend rechaza el envío, el pedido YA está guardado", async () => {
  const h = cargar({ almacen: true });
  process.env.RESEND_API_KEY = "re_prueba";
  const r0 = red({ mailFalla: true });
  const errorOriginal = console.error;
  console.error = () => {};
  try {
    const r = res();
    await h(req(COMPLETO), r);
    assert.equal(r.statusCode, 502);
    assert.ok(Array.isArray(r0.guardado) && r0.guardado.length === 1,
      "el mail falló y el prospecto no quedó en ningún lado");
    assert.equal(r0.guardado[0].email, COMPLETO.email);
  } finally {
    r0.restaurar();
    console.error = errorOriginal;
  }
});

test("sin RESEND_API_KEY el pedido igual queda guardado", async () => {
  // Es el caso más silencioso de todos: nadie configuró el mail y el
  // formulario parece andar. Con el registro, al menos el prospecto existe.
  const h = cargar({ almacen: true });
  delete process.env.RESEND_API_KEY;
  const r0 = red();
  const errorOriginal = console.error;
  console.error = () => {};
  try {
    const r = res();
    await h(req(COMPLETO), r);
    assert.equal(r.statusCode, 503);
    assert.equal(r0.mails.length, 0, "mandó un mail sin clave");
    assert.equal(r0.guardado[0].email, COMPLETO.email);
  } finally {
    r0.restaurar();
    console.error = errorOriginal;
  }
});

test("si el almacén falla, el pedido sale igual por mail", async () => {
  // El registro es una red de contención, no un requisito. Que un Edge Config
  // caído corte el formulario sería cambiar un modo de perder prospectos por
  // otro peor.
  const h = cargar({ almacen: true });
  process.env.RESEND_API_KEY = "re_prueba";
  const anterior = global.fetch;
  const errorOriginal = console.error;
  console.error = () => {};
  let mails = 0;
  global.fetch = async (url) => {
    if (String(url).includes("api.resend.com")) {
      mails += 1;
      return { ok: true, json: async () => ({}) };
    }
    throw new Error("edge config caído");
  };
  try {
    const r = res();
    await h(req(COMPLETO), r);
    assert.equal(r.statusCode, 200, "un almacén caído tumbó el formulario");
    assert.equal(mails, 1);
  } finally {
    global.fetch = anterior;
    console.error = errorOriginal;
  }
});

test("sin Edge Config configurado el formulario funciona como antes", async () => {
  const h = cargar({ almacen: false });
  process.env.RESEND_API_KEY = "re_prueba";
  const r0 = red();
  const errorOriginal = console.error;
  console.error = () => {};
  try {
    const r = res();
    await h(req(COMPLETO), r);
    assert.equal(r.statusCode, 200);
    assert.equal(r0.mails.length, 1);
    assert.equal(r0.guardado, null, "guardó sin tener dónde");
  } finally {
    r0.restaurar();
    console.error = errorOriginal;
  }
});

test("el id del pedido viaja en el mail, no en la respuesta al visitante",
  async () => {
    // El id es el enganche para atribuir después una copia filtrada a la demo
    // de la que salió. Devolvérselo a quien llena el formulario es contarle
    // que existe una marca y cuál es.
    const h = cargar({ almacen: true });
    process.env.RESEND_API_KEY = "re_prueba";
    const r0 = red();
    try {
      const r = res();
      await h(req(COMPLETO), r);
      const id = r0.guardado[0].id;
      assert.ok(r0.mails[0].text.includes(id), "el mail no trae el id del pedido");
      assert.deepEqual(r.body, { ok: true });
    } finally {
      r0.restaurar();
    }
  });
