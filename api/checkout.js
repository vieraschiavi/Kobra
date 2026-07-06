// Checkout de MercadoPago — función serverless (Vercel, CommonJS).
// El Access Token de MercadoPago vive SOLO como variable de entorno del servidor
// (MP_ACCESS_TOKEN). Nunca se expone al navegador ni se guarda en el repo.
// Alternativa sin token: configurar links de pago por plan (MP_LINK_PRO, MP_LINK_STARTER).
//
// POST + JSON (no GET/redirect): Vercel BotID solo puede adjuntar su verificación
// a pedidos hechos por fetch/XHR desde el navegador, nunca a una navegación de
// página completa (location.href). El cliente hace fetch acá y recién después
// navega él mismo a la URL de pago que devolvemos.

const { checkBotId } = require("botid/server");

const PLANS = {
  pro:     { title: "Kobra IA · Pro (todo incluido)", price: 149.0 },
  starter: { title: "Kobra IA · Starter (licencia)",  price: 490.0 },
};
const CURRENCY = process.env.MP_CURRENCY || "USD";  // coincide con los precios mostrados en la landing (US$)

module.exports = async (req, res) => {
  if (req.method !== "POST") { res.status(405).json({ error: "method" }); return; }

  const verification = await checkBotId({ advancedOptions: { headers: req.headers } });
  if (verification.isBot) { res.status(403).json({ error: "bot" }); return; }

  const body = typeof req.body === "string" ? safeJson(req.body) : (req.body || {});
  const plan = String(body.plan || "").toLowerCase();
  const p = PLANS[plan];
  if (!p) { res.status(400).json({ error: "plan_invalido" }); return; }

  const base = "https://" + (req.headers.host || "kobra-ia.vercel.app");
  const token = process.env.MP_ACCESS_TOKEN;
  const link = process.env["MP_LINK_" + plan.toUpperCase()];

  // Sin Access Token: si hay link de pago configurado, devuelvo ese.
  if (!token) {
    if (link) { res.status(200).json({ url: link }); return; }
    res.status(503).json({ error: "medio_pago_no_configurado" });
    return;
  }

  try {
    const pref = {
      items: [{ title: p.title, quantity: 1, unit_price: p.price, currency_id: CURRENCY }],
      back_urls: {
        success: base + "/descarga?status=approved&plan=" + plan,
        pending: base + "/descarga?status=pending",
        failure: base + "/#precios",
      },
      auto_return: "approved",
      metadata: { plan: plan },
    };
    const r = await fetch("https://api.mercadopago.com/checkout/preferences", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      body: JSON.stringify(pref),
    });
    const data = await r.json();
    if (!r.ok || !data.init_point) {
      res.status(502).json({ error: "mercadopago" });
      return;
    }
    res.status(200).json({ url: data.init_point });
  } catch (e) {
    res.status(500).json({ error: "exception" });
  }
};

function safeJson(s) { try { return JSON.parse(s); } catch (e) { return {}; } }
