// © 2026 Martín Viera. Todos los derechos reservados.

// Checkout de MercadoPago — función serverless (Vercel, CommonJS).
// El Access Token de MercadoPago vive SOLO como variable de entorno del servidor
// (MP_ACCESS_TOKEN). Nunca se expone al navegador ni se guarda en el repo.
// Alternativa sin token: configurar links de pago por plan (MP_LINK_PRO, MP_LINK_STARTER).
//
// POST + JSON (no GET/redirect): Vercel BotID solo puede adjuntar su verificación
// a pedidos hechos por fetch/XHR desde el navegador, nunca a una navegación de
// página completa (location.href). El cliente hace fetch acá y recién después
// navega él mismo a la URL de pago que devolvemos.

const crypto = require("crypto");
const { checkBotId } = require("botid/server");
const { limitar, ipDe, permitir } = require("./_ratelimit");
const { AVISOS_AL_DUENO, enviarUno } = require("./_aviso");

const PLANS = {
  basico:  { title: "MV Kobra AI · Básico (mensual)",    price: 99.0 },
  pro:     { title: "MV Kobra AI · Pro (todo incluido)", price: 349.0 },
  starter: { title: "MV Kobra AI · Starter (licencia)",  price: 690.0 },
};

// Módulos que se venden sueltos, sobre cualquier plan. Van en un catálogo
// aparte y no como una fila más de PLANS porque no son escalones de la misma
// escalera: Logística cuesta menos que Básico y no es "menos Kobra", es otro
// producto. Espejo de backend_venta/licencias.py::MODULOS_VENTA.
const MODULOS = {
  logistica: { title: "MV Kobra AI · Logística y reposición", price: 79.0 },
  proyectos: { title: "MV Kobra AI · Proyectos",              price: 69.0 },
};

// Lo que se puede comprar: planes y módulos, con el mismo flujo de pago.
const COMPRABLES = { ...PLANS, ...MODULOS };
// La cuenta de cobro (collector) de Mercado Pago 1007782272006 es de Uruguay (site MLU),
// que solo acepta preferencias en UYU: mandar "USD" hace que la API rechace la preferencia
// (no llega init_point) y el checkout falla con "No se pudo iniciar el pago". Los precios en
// la landing se muestran de referencia en USD pero "se cobran en pesos uruguayos al tipo de
// cambio del día" — por eso acá se convierte antes de crear la preferencia.
const CURRENCY = process.env.MP_CURRENCY || "UYU";
const TASA_UYU = Number(process.env.MP_TASA_UYU) || 40; // mismo valor de referencia que la landing (US$1 ≈ $U 40)

// ---------------------------------------------------------------------------
//  Aviso de INTENCIÓN de compra.
//
//  MercadoPago ya avisa por mail cuando un pago se concreta, y el webhook de
//  este repo manda la licencia. Lo que no existía era enterarse de quien llegó
//  hasta el botón y NO compró — que es la mitad del embudo que dice si el
//  precio, el plan o la pasarela están espantando gente.
//
//  Tres decisiones, y las tres tienen su motivo:
//
//  1. VA ANTES DE HABLAR CON MERCADOPAGO. Si MercadoPago rechaza la
//     preferencia o está caído, ese es JUSTAMENTE el caso que hay que saber:
//     alguien quiso comprar y el sistema no lo dejó. Avisar sólo cuando la
//     preferencia sale bien dejaría invisible la falla que más caro sale.
//
//  2. NUNCA PUEDE ROMPER EL CHECKOUT. Sin RESEND_API_KEY no manda nada y sigue
//     de largo en silencio; si Resend falla o tarda, se corta a los 2,5 s
//     (`enviarUno` con timeout) y el checkout continúa igual. El aviso es un
//     lujo; la venta no.
//
//  3. UN AVISO POR PERSONA Y POR PLAN CADA 15 MINUTOS. El que duda toca
//     "Comprar" cinco veces, vuelve, compara planes, prueba de nuevo. Sin
//     freno, eso son cinco mails por una sola intención y a la semana el aviso
//     se vuelve ruido que se archiva sin leer — o sea que deja de servir.
//
//     OJO con el alcance del freno: reusa el mismo cubo en memoria que
//     `_ratelimit.js`, que es "mejor esfuerzo" y por instancia tibia, no
//     global al fleet (está explicado en ese archivo). En la práctica alcanza
//     —el que tantea el botón cae casi siempre en la misma instancia—, pero no
//     es una garantía: si Vercel levanta una instancia nueva, puede entrar un
//     mail repetido. Se prefirió eso antes que escribir en Edge Config en cada
//     click, que pega contra los límites de la API de administración.
// ---------------------------------------------------------------------------
async function avisarIntencion(req, plan, p, unitPrice, moneda) {
  // Interruptor propio. Hace falta uno separado porque RESEND_API_KEY no
  // sirve de interruptor: es la MISMA clave con la que el webhook le manda la
  // licencia al comprador, así que apagarla para no recibir estos avisos
  // dejaría a los clientes sin licencia. Poné AVISO_INTENCION=0 y seguís
  // recibiendo el mail de cada VENTA, sin los de intención.
  if (/^(0|no|off|false)$/i.test(String(process.env.AVISO_INTENCION || ""))) return false;

  const clave = process.env.RESEND_API_KEY;
  if (!clave) return false;   // sin clave configurada no hay nada que hacer

  // 1 aviso por (IP + plan) cada 15 minutos.
  if (!permitir("aviso-intencion:" + ipDe(req) + ":" + plan, 1, 900).ok) return false;

  // Hora de Montevideo, que es la que te sirve para saber si vale la pena
  // contestar ahora o mañana. El servidor corre en UTC.
  let cuando;
  try {
    cuando = new Date().toLocaleString("es-UY", { timeZone: "America/Montevideo" });
  } catch {
    cuando = new Date().toISOString();   // si falta la base de husos, UTC
  }

  // País e IP, si el proxy los pasa: ayuda a distinguir un prospecto real de
  // alguien tanteando la API desde un script. Nunca son obligatorios — un
  // proxy que no los manda no puede tumbar el aviso.
  const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  const pais = req.headers["x-vercel-ip-country"] || "";

  const cuerpo =
    "Alguien apretó COMPRAR en mvkobranzaia.com.\n\n" +
    "Producto: " + p.title + "\n" +
    "Plan:     " + plan + "\n" +
    "Precio:   US$ " + p.price + "  (se cobra " + moneda + " " + unitPrice + ")\n" +
    "Cuándo:   " + cuando + " (hora de Montevideo)\n" +
    (pais ? "País:     " + pais + "\n" : "") +
    (ip ? "IP:       " + ip + "\n" : "") +
    "\nEsto es INTENCIÓN de compra, no una venta: recién se va a MercadoPago.\n" +
    "Si en los próximos minutos no llega el mail de licencia, es que no completó el pago.\n\n" +
    "Un solo aviso por persona y por plan cada 15 minutos, así el que duda y\n" +
    "toca varias veces no te llena la casilla.";

  return enviarUno(clave, AVISOS_AL_DUENO, "Intención de compra · " + p.title, cuerpo, 2500);
}

module.exports = async (req, res) => {
  if (req.method !== "POST") { res.status(405).json({ error: "method" }); return; }
  // 10 por minuto por IP: de sobra para alguien probando planes, corto para
  // un script golpeando la API de MercadoPago a través de este endpoint.
  if (!limitar(req, res, "checkout", 10, 60)) return;

  const verification = await checkBotId({ advancedOptions: { headers: req.headers } });
  if (verification.isBot) { res.status(403).json({ error: "bot" }); return; }

  const body = typeof req.body === "string" ? safeJson(req.body) : (req.body || {});
  const plan = String(body.plan || "").toLowerCase();
  const p = COMPRABLES[plan];
  if (!p) { res.status(400).json({ error: "plan_invalido" }); return; }

  const base = "https://" + (req.headers.host || "mvkobranzaia.com");
  const token = process.env.MP_ACCESS_TOKEN;
  const link = process.env["MP_LINK_" + plan.toUpperCase()];

  // El precio ya convertido. Se calcula ACÁ y no adentro del `try` porque el
  // aviso de intención lo necesita, y el aviso tiene que salir aunque el pago
  // ni siquiera llegue a iniciarse (ver el comentario de avisarIntencion).
  const unitPrice = CURRENCY === "UYU" ? Math.round(p.price * TASA_UYU) : p.price;

  // Antes de hablar con MercadoPago, a propósito: si MercadoPago rechaza o
  // está caído, ese es el caso que más importa saber. `await` con tope de
  // 2,5 s adentro; nunca tira ni corta el checkout.
  await avisarIntencion(req, plan, p, unitPrice, CURRENCY);

  // Sin Access Token: si hay link de pago configurado, devuelvo ese.
  if (!token) {
    if (link) { res.status(200).json({ url: link }); return; }
    res.status(503).json({ error: "medio_pago_no_configurado" });
    return;
  }

  try {
    // Referencia aleatoria, única por checkout: es lo único que ata "quién
    // volvió del pago" con "quién lo inició". Sin esto, `verify-payment.js`
    // no tenía forma de distinguir al comprador real de cualquiera que
    // adivinara/tanteara un `payment_id` — ver el comentario largo en
    // verify-payment.js sobre por qué esto es imprescindible, no opcional.
    const ref = crypto.randomBytes(16).toString("hex");
    const pref = {
      items: [{ title: p.title, quantity: 1, unit_price: unitPrice, currency_id: CURRENCY }],
      external_reference: ref,
      back_urls: {
        success: base + "/descarga?status=approved&plan=" + plan + "&ref=" + ref,
        pending: base + "/descarga?status=pending&ref=" + ref,
        failure: base + "/#precios",
      },
      auto_return: "approved",
      // Aviso server-to-server: llega aunque el comprador cierre la pestaña o
      // se quede sin señal al volver del pago. Sin esto, la licencia dependía
      // enteramente de que su navegador ejecutara el fetch de /descarga — y si
      // no lo hacía, la plata entraba sin dejar rastro de que había algo que
      // entregar. Va acá, en la preferencia, para no depender de que alguien
      // configure la URL a mano en el panel de MercadoPago.
      notification_url: base + "/api/webhook-mercadopago",
      metadata: { plan: plan },
    };
    const r = await fetch("https://api.mercadopago.com/checkout/preferences", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      body: JSON.stringify(pref),
    });
    const data = await r.json();
    if (!r.ok || !data.init_point) {
      console.error("checkout: mercadopago rechazó la preferencia", r.status, data);
      res.status(502).json({ error: "mercadopago" });
      return;
    }
    res.status(200).json({ url: data.init_point });
  } catch (e) {
    console.error("checkout: excepción creando la preferencia", e);
    res.status(500).json({ error: "exception" });
  }
};

function safeJson(s) { try { return JSON.parse(s); } catch (e) { return {}; } }
