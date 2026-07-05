// Checkout de MercadoPago — función serverless (Vercel, CommonJS).
// El Access Token de MercadoPago vive SOLO como variable de entorno del servidor
// (MP_ACCESS_TOKEN). Nunca se expone al navegador ni se guarda en el repo.
// Alternativa sin token: configurar links de pago por plan (MP_LINK_PRO, MP_LINK_STARTER).

const PLANS = {
  pro:     { title: "Kobra IA · Pro (todo incluido)", price: 149.0 },
  starter: { title: "Kobra IA · Starter (licencia)",  price: 490.0 },
};
const CURRENCY = process.env.MP_CURRENCY || "UYU";  // MercadoPago Uruguay usa UYU

module.exports = async (req, res) => {
  const plan = String((req.query && req.query.plan) || "").toLowerCase();
  const p = PLANS[plan];
  if (!p) { res.status(400).send("Plan inválido."); return; }

  const base = "https://" + (req.headers.host || "kobra-ia.vercel.app");
  const token = process.env.MP_ACCESS_TOKEN;
  const link = process.env["MP_LINK_" + plan.toUpperCase()];

  // Sin Access Token: si hay link de pago configurado, redirijo ahí.
  if (!token) {
    if (link) { res.writeHead(302, { Location: link }); res.end(); return; }
    res.status(503).send("El medio de pago se está configurando. Probá de nuevo en un rato.");
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
      res.status(502).send("No se pudo iniciar el pago. Intentá de nuevo.");
      return;
    }
    res.writeHead(302, { Location: data.init_point });
    res.end();
  } catch (e) {
    res.status(500).send("Error iniciando el pago.");
  }
};
