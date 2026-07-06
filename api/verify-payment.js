// Verifica un pago de MercadoPago contra la API real (server-side) antes de habilitar
// la descarga. Evita que alguien arme la URL de /descarga a mano sin haber pagado.
// Si el pago está aprobado, emite automáticamente la licencia MV Kobra AI (firmada).

const { sign } = require("./_license");

module.exports = async (req, res) => {
  const paymentId = String((req.query && req.query.payment_id) || "").trim();
  if (!paymentId || !/^[0-9]+$/.test(paymentId)) {
    res.status(400).json({ approved: false, error: "payment_id inválido" });
    return;
  }
  const token = process.env.MP_ACCESS_TOKEN;
  if (!token) { res.status(500).json({ approved: false, error: "no_token" }); return; }

  try {
    const r = await fetch("https://api.mercadopago.com/v1/payments/" + paymentId, {
      headers: { Authorization: "Bearer " + token },
    });
    const data = await r.json();
    if (!r.ok) { res.status(502).json({ approved: false, error: "mp_error" }); return; }

    const approved = data.status === "approved";
    const plan = (data.metadata && data.metadata.plan) || null;

    let license = null;
    const secret = process.env.LICENSE_SECRET;
    if (approved && secret) {
      license = sign({
        plan: plan,
        pid: paymentId,
        email: (data.payer && data.payer.email) || null,
        iat: Math.floor(Date.now() / 1000),
      }, secret);
    }

    res.status(200).json({ approved: approved, status: data.status, plan: plan, license: license });
  } catch (e) {
    res.status(500).json({ approved: false, error: "exception" });
  }
};
