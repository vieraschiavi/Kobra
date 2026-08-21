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

function cargar() {
  delete require.cache[require.resolve("./solicitar-demo")];
  delete require.cache[require.resolve("./_ratelimit")];
  return require("./solicitar-demo");
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
