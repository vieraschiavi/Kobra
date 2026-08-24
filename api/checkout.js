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
const { limitar, permitir, ipDe } = require("./_ratelimit");

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

const AVISOS_AL_DUENO = "vieraschiavi@gmail.com";

/**
 * Avisa por mail que alguien tocó "Comprar".
 *
 * `webhook-mercadopago.js` ya avisa cuando el pago SE CONCRETA. Esto es otra
 * señal y llega antes: la INTENCIÓN. Sirve para dos cosas distintas —
 *
 *   · saber que hay demanda real sin tener que mirar el panel de MercadoPago,
 *   · y decidir cuándo pagar infraestructura, en vez de pagarla por las dudas.
 *
 * Nunca puede romper el checkout. Si Resend está caído o sin configurar, el
 * comprador tiene que recibir su URL de pago igual: perder una venta por no
 * poder mandar un aviso sería exactamente al revés de lo que se busca. Por eso
 * todo el cuerpo va adentro de un try y el resultado se ignora.
 *
 * Se espera el envío (no fire-and-forget) porque en una función serverless el
 * proceso se congela apenas se responde: un `fetch` sin await se muere a mitad
 * y el aviso no sale nunca.
 */
async function avisarIntencion(plan, precio, moneda, ref, req) {
  const clave = process.env.RESEND_API_KEY;
  if (!clave) return;

  // Un aviso por persona y plan cada media hora.
  //
  // Comprar software no es un click: es mirar el precio, dudar, abrir el
  // comparativo, volver. Ese recorrido normal generaba cinco mails del mismo
  // señor, y cinco mails que dicen lo mismo enseñan a ignorar los mails.
  //
  // La ficha se pide DESPUÉS de comprobar que hay con qué mandar: si no hay
  // clave, no se gasta la ficha, así el día que la configures el primer click
  // avisa aunque alguien haya tanteado antes.
  //
  // Es dedupe de mejor esfuerzo, igual que el freno (ver `_ratelimit.js`):
  // cada instancia tibia tiene su propia memoria, así que si el mismo
  // visitante cae en dos instancias distintas te van a llegar dos avisos. No
  // se puede hacer mejor sin una base compartida, y una base para no repetir
  // un mail es más pieza de la que el problema justifica.
  if (!permitir("aviso-intencion:" + ipDe(req) + ":" + plan, 1, 1800).ok) return;

  try {
    const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
    const pais = req.headers["x-vercel-ip-country"] || "";
    const cuerpo =
      "Alguien tocó Comprar en MV Kobra AI.\n\n" +
      `Plan:       ${plan}\n` +
      `Precio:     ${precio} ${moneda}\n` +
      `Referencia: ${ref}\n` +
      (pais ? `País:       ${pais}\n` : "") +
      (ip ? `IP:         ${ip}\n` : "") +
      "\nOJO: esto es INTENCIÓN, no una venta. El pago confirmado llega " +
      "aparte, por el webhook, con la licencia adjunta.\n" +
      "\nSe avisa una vez por visitante y plan cada 30 minutos: si esta " +
      "persona vuelve a tocar Comprar, no te llega otro mail.\n";
    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: "Bearer " + clave, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: process.env.RESEND_FROM || "MV Kobra AI <onboarding@resend.dev>",
        to: [AVISOS_AL_DUENO],
        subject: `Intención de compra · ${plan} · ${precio} ${moneda}`,
        text: cuerpo,
      }),
    });
  } catch (e) {
    // A propósito: solo al log. El checkout sigue.
    console.error("checkout: no se pudo avisar la intención de compra", e);
  }
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
    const unitPrice = CURRENCY === "UYU" ? Math.round(p.price * TASA_UYU) : p.price;
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
    // Recién acá: la preferencia se creó de verdad. Avisar antes sería avisar
    // de clicks que terminaron en error y no en una pantalla de pago.
    await avisarIntencion(plan, unitPrice, CURRENCY, ref, req);
    res.status(200).json({ url: data.init_point });
  } catch (e) {
    console.error("checkout: excepción creando la preferencia", e);
    res.status(500).json({ error: "exception" });
  }
};

function safeJson(s) { try { return JSON.parse(s); } catch (e) { return {}; } }
