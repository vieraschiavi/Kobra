// Verifica un pago de MercadoPago contra la API real (server-side) antes de habilitar
// la descarga. Evita que alguien arme la URL de /descarga a mano sin haber pagado.
// Si el pago está aprobado, emite automáticamente la licencia MV Kobra AI (firmada).

const { sign, secretoActivo } = require("./_license");
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

    let license = null;
    let licenseError = null;
    const secret = secretoActivo();
    if (approved && secret) {
      try {
        license = sign({
          plan: plan,
          pid: paymentId,
          email: (data.payer && data.payer.email) || null,
        }, secret);
      } catch (e) {
        // Plan aprobado pero desconocido para el catálogo de licencias: no
        // podemos emitir algo que la app rechazaría. Se avisa en vez de
        // devolver una licencia rota, que es el bug que esto viene a cerrar.
        licenseError = "plan_no_licenciable";
      }
    }

    res.status(200).json({
      approved: approved, status: data.status, plan: plan,
      license: license, license_error: licenseError,
    });
  } catch (e) {
    res.status(500).json({ approved: false, error: "exception" });
  }
};
