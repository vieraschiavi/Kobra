// Webhook de MercadoPago: la red de seguridad del cobro.
//
// EL PROBLEMA QUE RESUELVE
// Hasta acá, la licencia se emitía en UN solo lugar: `verify-payment.js`,
// disparado por el navegador del comprador al volver del pago
// (`landing/descarga.html`). Si el comprador cerraba la pestaña, se quedaba
// sin señal, o el fetch fallaba, la plata entraba y NO quedaba ningún rastro
// del lado del servidor de que había una licencia por entregar. El único
// mecanismo de recuperación era que el cliente escribiera por mail.
//
// MercadoPago avisa server-to-server cada vez que un pago cambia de estado.
// Ese aviso llega igual aunque el comprador haya cerrado todo — es el único
// camino que no depende de su navegador.
//
// LA REGLA, Y POR QUÉ
// Esta URL es PÚBLICA: cualquiera puede hacerle POST. Así que el cuerpo del
// aviso NO se cree para nada — no se lee de ahí ni el estado, ni el monto, ni
// el plan. Lo único que se toma es un id ("mirá este pago") y con eso se
// vuelve a consultar la API de MercadoPago con el access token del vendedor,
// que es la única fuente de verdad. Un atacante que invente un aviso solo
// logra que releamos un pago real; no puede fabricar uno aprobado.
//
// Es el mismo criterio que ya usa `verify-payment.js` (que además exige la
// referencia del checkout para no revelarle a un tercero los datos de un pago
// ajeno). Acá esa comprobación NO hace falta y sería contraproducente: el
// aviso no viene del navegador de nadie, no le devuelve datos a quien llama
// (siempre responde 200 vacío) y su función es justamente cubrir el caso en
// que el comprador perdió su referencia.
//
// QUÉ HACE CON EL PAGO APROBADO
// Emite la licencia (idéntica a la de `verify-payment.js`: mismo `sign`,
// mismo secreto, mismo `pid`) y se la manda por mail al comprador, con copia
// al dueño. Si no hay `RESEND_API_KEY` configurada, igual deja el registro en
// los logs de la función para poder recuperarla a mano — nunca se pierde en
// silencio, que es exactamente lo que pasaba antes.
//
// CONFIGURACIÓN: ninguna del lado de MercadoPago — `checkout.js` manda
// `notification_url` apuntando acá en cada preferencia que crea, así que sabe
// adónde avisar sin tocar nada en su panel. Del lado del mail hay dos
// variables opcionales, y el webhook funciona sin ninguna de las dos:
//   · RESEND_API_KEY — sin ella no se manda ningún mail (la licencia igual se
//     emite y queda en el log de la función).
//   · RESEND_FROM    — remitente. Sin ella se usa el compartido de prueba de
//     Resend, que entrega solo a la casilla del titular de la cuenta: el mail
//     al comprador va a rebotar hasta que haya un dominio propio verificado.

const { sign, secretoActivo } = require("./_license");
const { limitar } = require("./_ratelimit");

const AVISOS_AL_DUENO = "vieraschiavi@gmail.com";

/** El id del pago que viene en el aviso, en cualquiera de las formas en que
 *  MercadoPago lo manda (IPN viejo con `topic`/`id`, o Webhooks con
 *  `type`/`data.id`, por query o por body). Solo es un puntero: lo que diga
 *  el resto del aviso no se usa. */
function idDePago(req) {
  const q = req.query || {};
  const b = (req.body && typeof req.body === "object") ? req.body : {};
  const tipo = String(q.type || q.topic || b.type || b.topic || "").toLowerCase();
  // Los avisos de `merchant_order` traen el id de la ORDEN, no del pago:
  // consultarlo contra /v1/payments daría 404. Se ignoran — el pago que
  // interesa dispara además su propio aviso de tipo `payment`.
  if (tipo && tipo !== "payment") return null;
  const id = q["data.id"] || q.id || (b.data && b.data.id) || b.id;
  const limpio = String(id == null ? "" : id).trim();
  return /^[0-9]+$/.test(limpio) ? limpio : null;
}

/** Un envío, un destinatario. Devuelve si Resend lo aceptó. */
async function enviarUno(clave, para, asunto, texto) {
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: "Bearer " + clave, "Content-Type": "application/json" },
      body: JSON.stringify({ from: remitente(), to: [para], subject: asunto, text: texto }),
    });
    if (!r.ok) {
      console.error("webhook-mp: Resend rechazó el envío a", para, r.status, await r.text());
      return false;
    }
    return true;
  } catch (e) {
    console.error("webhook-mp: excepción enviando la licencia a", para, e);
    return false;
  }
}

/** El remitente. Por defecto el compartido de prueba de Resend, que SOLO
 *  entrega a la casilla del titular de la cuenta. Para que le llegue al
 *  comprador hay que verificar un dominio propio en Resend y poner acá algo
 *  del estilo "MV Kobra AI <licencias@mvkobranzaia.com>". */
function remitente() {
  return process.env.RESEND_FROM || "MV Kobra AI <onboarding@resend.dev>";
}

async function enviarLicencia(email, plan, paymentId, license) {
  const clave = process.env.RESEND_API_KEY;
  if (!clave) return { comprador: false, dueno: false };
  const cuerpo =
    "¡Gracias por tu compra!\n\n" +
    "Tu licencia de MV Kobra AI (plan " + plan + "):\n\n" +
    license + "\n\n" +
    "Cómo activarla: abrí MV Kobra AI y pegala en la pantalla de activación.\n" +
    "Descarga del instalador para Windows:\n" +
    "https://github.com/vieraschiavi/mv-kobra-ai-releases/releases/latest/download/MVKobraAI_Setup.exe\n\n" +
    "Guardá este mail: es tu comprobante de activación.\n" +
    "Nº de operación: " + paymentId + "\n\n" +
    "Cualquier duda, respondé este mail.";
  const asunto = "Tu licencia de MV Kobra AI (plan " + plan + ")";
  // Dos envíos separados a propósito, no uno con dos destinatarios. Con el
  // remitente compartido de prueba (`onboarding@resend.dev`) Resend entrega
  // SOLO a la casilla del titular de la cuenta y rechaza el resto: mandados
  // juntos, ese rechazo se llevaba puesta también la copia al dueño y nadie
  // quedaba con la licencia en la mano. Separados, el dueño la recibe siempre
  // y puede reenviarla mientras el dominio propio no esté verificado.
  const dueno = await enviarUno(clave, AVISOS_AL_DUENO, asunto, cuerpo);
  const comprador = email ? await enviarUno(clave, email, asunto, cuerpo) : false;
  return { comprador: comprador, dueno: dueno };
}

module.exports = async (req, res) => {
  // MercadoPago espera un 200 rápido; si no, reintenta. Todo lo que sale mal
  // acá se loguea y se responde 200 igual, EXCEPTO los errores nuestros
  // transitorios (ver más abajo), donde el reintento de MercadoPago es
  // justamente lo que queremos.
  if (!limitar(req, res, "webhook-mp", 120, 60)) return;

  const paymentId = idDePago(req);
  if (!paymentId) { res.status(200).json({ ok: true, ignorado: true }); return; }

  const token = process.env.MP_ACCESS_TOKEN;
  if (!token) {
    console.error("webhook-mp: falta MP_ACCESS_TOKEN, no se puede verificar el pago", paymentId);
    // 500 a propósito: MercadoPago reintenta, y para cuando alguien cargue la
    // variable el aviso todavía puede llegar. Un 200 acá perdería el pago.
    res.status(500).json({ error: "no_token" });
    return;
  }

  try {
    const r = await fetch("https://api.mercadopago.com/v1/payments/" + paymentId, {
      headers: { Authorization: "Bearer " + token },
    });
    const data = await r.json();
    if (!r.ok) {
      console.error("webhook-mp: mercadopago respondió error al releer el pago",
                    paymentId, r.status, data);
      // Idem: dejar que reintente en vez de dar el pago por perdido.
      res.status(502).json({ error: "mp_error" });
      return;
    }

    if (data.status !== "approved") {
      // Pendiente, rechazado, en proceso: nada que emitir todavía. Cuando se
      // apruebe, MercadoPago manda otro aviso.
      res.status(200).json({ ok: true, status: data.status });
      return;
    }

    const plan = (data.metadata && data.metadata.plan) || null;
    const email = (data.payer && data.payer.email) || null;
    const secret = secretoActivo();
    if (!secret) {
      console.error("webhook-mp: PAGO APROBADO SIN SECRETO DE LICENCIA CONFIGURADO —",
                    "hay que emitir a mano. payment_id:", paymentId, "plan:", plan,
                    "email:", email);
      res.status(200).json({ ok: true, license: false, motivo: "sin_secreto" });
      return;
    }

    let license;
    try {
      license = sign({ plan: plan, pid: paymentId, email: email }, secret);
    } catch (e) {
      console.error("webhook-mp: PAGO APROBADO DE UN PLAN NO LICENCIABLE —",
                    "hay que resolverlo a mano. payment_id:", paymentId, "plan:", plan,
                    "email:", email);
      res.status(200).json({ ok: true, license: false, motivo: "plan_no_licenciable" });
      return;
    }

    const enviado = await enviarLicencia(email, plan, paymentId, license);
    if (!enviado.comprador) {
      // Sin mail configurado, o con el remitente de prueba de Resend (que solo
      // entrega al titular de la cuenta), o si el envío falló: la licencia NO
      // se pierde. Queda en el log de la función, que es recuperable, y si al
      // menos salió la copia al dueño, ya está en su casilla para reenviar.
      console.error("webhook-mp: licencia emitida pero NO enviada al comprador —",
                    "recuperar de acá. payment_id:", paymentId, "plan:", plan,
                    "email:", email, "copia_al_dueno:", enviado.dueno,
                    "license:", license);
    }
    res.status(200).json({ ok: true, license: true,
                           enviado: enviado.comprador, avisado_dueno: enviado.dueno });
  } catch (e) {
    console.error("webhook-mp: excepción procesando el aviso", paymentId, e);
    res.status(500).json({ error: "exception" });
  }
};

module.exports.idDePago = idDePago;
