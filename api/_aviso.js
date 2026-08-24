// © 2026 Martín Viera. Todos los derechos reservados.

// Envío de mails de aviso — lo compartido entre el webhook de MercadoPago (que
// manda la licencia al comprador) y el checkout (que avisa al dueño que
// alguien apretó "Comprar").
//
// Estaba todo adentro de webhook-mercadopago.js. Se saca acá porque ahora hay
// dos endpoints que mandan mail, y `remitente()` es justo la clase de función
// que no puede tener dos copias: el día que se verifique el dominio propio en
// Resend hay que cambiarla en UN lugar, y si hay dos, la que se olvide sigue
// mandando desde `onboarding@resend.dev` —que entrega SOLO a la casilla del
// titular de la cuenta— sin que nadie se entere hasta que un cliente reclame
// que nunca le llegó nada.

// Adónde van los avisos internos. Es la casilla del dueño, no la de un
// cliente: acá llegan tanto la copia de cada licencia vendida como el aviso de
// intención de compra.
const AVISOS_AL_DUENO = "vieraschiavi@gmail.com";

/** El remitente. Por defecto el compartido de prueba de Resend, que SOLO
 *  entrega a la casilla del titular de la cuenta. Para que le llegue al
 *  comprador hay que verificar un dominio propio en Resend y poner acá algo
 *  del estilo "MV Kobra AI <licencias@mvkobranzaia.com>". */
function remitente() {
  return process.env.RESEND_FROM || "MV Kobra AI <onboarding@resend.dev>";
}

/** Un envío, un destinatario. Devuelve si Resend lo aceptó.
 *
 *  `timeoutMs` existe por el checkout: ahí el mail se manda mientras el
 *  comprador espera la URL de pago, así que una demora de Resend no puede
 *  convertirse en una demora del checkout. Sin tope, un Resend lento o colgado
 *  dejaba al que quiere comprar mirando un botón que no responde — o sea que
 *  el aviso de venta costaría ventas, que es exactamente al revés de para lo
 *  que existe. */
async function enviarUno(clave, para, asunto, texto, timeoutMs) {
  const ctrl = timeoutMs ? new AbortController() : null;
  const reloj = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: "Bearer " + clave, "Content-Type": "application/json" },
      body: JSON.stringify({ from: remitente(), to: [para], subject: asunto, text: texto }),
      signal: ctrl ? ctrl.signal : undefined,
    });
    if (!r.ok) {
      console.error("aviso: Resend rechazó el envío a", para, r.status, await r.text());
      return false;
    }
    return true;
  } catch (e) {
    console.error("aviso: excepción enviando a", para, e);
    return false;
  } finally {
    if (reloj) clearTimeout(reloj);
  }
}

module.exports = { AVISOS_AL_DUENO, remitente, enviarUno };
