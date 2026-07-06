// DIAGNÓSTICO TEMPORAL — borrar este archivo apenas tengamos la respuesta.
// Prueba si la cuenta real de MercadoPago puede crear un Preapproval
// (suscripción recurrente) en USD, o si exige UYU. No cobra nada: crea el
// preapproval en status "pending" (el pagador nunca llega a autorizarlo).
//
// Uso: GET /api/diag-preapproval?clave=kobra-diag-2026

module.exports = async (req, res) => {
  if (req.query.clave !== "kobra-diag-2026") { res.status(403).json({ error: "no autorizado" }); return; }

  const token = process.env.MP_ACCESS_TOKEN;
  if (!token) { res.status(503).json({ error: "MP_ACCESS_TOKEN no configurado" }); return; }

  const base = "https://" + (req.headers.host || "kobra-ia.vercel.app");

  async function intentar(currency) {
    const body = {
      reason: "Kobra IA - diagnostico moneda (borrar)",
      auto_recurring: { frequency: 1, frequency_type: "months", transaction_amount: 1, currency_id: currency },
      back_url: base + "/",
      payer_email: "test_user_diag_kobra@testuser.com",
      status: "pending",
    };
    try {
      const r = await fetch("https://api.mercadopago.com/preapproval", {
        method: "POST",
        headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      return { currency, http_status: r.status, ok: r.ok, respuesta: data };
    } catch (e) {
      return { currency, error: String(e) };
    }
  }

  const usd = await intentar("USD");
  const uyu = await intentar("UYU");
  res.status(200).json({ usd, uyu });
};
