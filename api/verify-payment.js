// Verifica un pago de MercadoPago contra la API real (server-side) antes de habilitar
// la descarga. Evita que alguien arme la URL de /descarga a mano sin haber pagado.
// Si el pago está aprobado, emite automáticamente la licencia MV Kobra AI (firmada).
//
// `payment_id` NO alcanza por sí solo para autorizar nada: es un identificador
// de MercadoPago, no un secreto — cualquiera puede tantear valores cercanos al
// suyo propio (los ids de una misma cuenta de cobro caen en rangos parecidos) y
// terminar consultando el pago aprobado de OTRO comprador, recibiendo su
// licencia y su email. `checkout.js` genera un `ref` aleatorio por checkout y
// lo manda como `external_reference` a MercadoPago; acá se exige ese mismo
// `ref` y se compara contra lo que MercadoPago devuelve — sin la coincidencia,
// no importa que el pago exista y esté aprobado: no es SU pago.

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
  const ref = String((req.query && req.query.ref) || "").trim();
  if (!ref || !/^[0-9a-f]{32}$/.test(ref)) {
    res.status(400).json({ approved: false, error: "ref inválido" });
    return;
  }
  const token = process.env.MP_ACCESS_TOKEN;
  if (!token) { res.status(500).json({ approved: false, error: "no_token" }); return; }

  try {
    const r = await fetch("https://api.mercadopago.com/v1/payments/" + paymentId, {
      headers: { Authorization: "Bearer " + token },
    });
    const data = await r.json();
    if (!r.ok) {
      console.error("verify-payment: mercadopago respondió error", r.status, data);
      res.status(502).json({ approved: false, error: "mp_error" });
      return;
    }

    // El pago existe y puede estar aprobado, pero si no es el que ESTE
    // checkout originó, tratarlo como no aprobado — no se revela ni el plan
    // ni ningún otro dato del pago ajeno.
    if (data.external_reference !== ref) {
      res.status(200).json({ approved: false, license: null, error: "referencia_no_coincide" });
      return;
    }

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
    console.error("verify-payment: excepción verificando el pago", e);
    res.status(500).json({ approved: false, error: "exception" });
  }
};
