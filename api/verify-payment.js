// Verifica un pago de MercadoPago contra la API real (server-side) antes de habilitar
// la descarga. Evita que alguien arme la URL de /descarga a mano sin haber pagado.
// Si el pago está aprobado, emite automáticamente la licencia MV Kobra AI (firmada).

const { emitirLicencia, secretoLicencia } = require("./_license");
const { limitar } = require("./_ratelimit");

module.exports = async (req, res) => {
  // Sin esto se podía tantear payment_id a la velocidad que diera la red: es
  // un endpoint público, sin bot-check, que consulta la API de MercadoPago.
  // 20 por minuto alcanza para el polling normal de /descarga tras pagar.
  if (!limitar(req, res, "verify-payment", 20, 60)) return;

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

    // La licencia se emite como JWT HS256 con el juego de claims que valida la
    // app instalada (ver _license.js). `emitirLicencia` devuelve null si el
    // plan que vino en la metadata del pago no existe: preferimos no entregar
    // licencia a entregar una que la app rechace delante del cliente.
    let license = null;
    const secret = secretoLicencia();
    if (approved && secret) {
      license = emitirLicencia({
        plan: plan,
        pid: paymentId,
        email: (data.payer && data.payer.email) || null,
      }, secret);
    }

    res.status(200).json({ approved: approved, status: data.status, plan: plan, license: license });
  } catch (e) {
    res.status(500).json({ approved: false, error: "exception" });
  }
};
