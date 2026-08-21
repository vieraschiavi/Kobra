// © 2026 Martín Viera. Todos los derechos reservados.

// Pedido de demo. Reemplaza la demo pública.
//
// Lo que había antes era un registro que guardaba nombre y mail en
// `localStorage` y no los mandaba a ningún lado: no llegaba ni un lead, y la
// demo se abría igual escribiendo la URL. O sea, lo peor de los dos mundos —
// cero captura y el modelo entrenado (`modelo_web.js`) descargable por
// cualquiera.
//
// Ahora el pedido llega por mail al dueño y la demo se da en vivo. Eso cambia
// tres cosas: no se regala el artefacto de ingeniería, queda registro de quién
// pidió acceso, y la demostración se usa para vender en vez de que la miren
// solos.
const { limitar } = require("./_ratelimit");

const DESTINO = "vieraschiavi@gmail.com";
const MAX = { nombre: 120, empresa: 120, pais: 60, email: 160, mensaje: 1500 };

function remitente() {
  return process.env.RESEND_FROM || "MV Kobra AI <onboarding@resend.dev>";
}

/** Recorta y limpia un campo del formulario. */
function campo(v, tope) {
  if (typeof v !== "string") return "";
  // \r y \n fuera: el asunto del mail es de una línea, y permitir saltos ahí
  // es inyección de cabeceras.
  return v.replace(/[\r\n]+/g, " ").trim().slice(0, tope);
}

/**
 * ¿Parece un mail? Deliberadamente laxo.
 *
 * Validar direcciones con una expresión estricta rechaza casillas legítimas
 * (subdominios, TLD largos, `+etiqueta`), y acá el costo de rechazar a un
 * prospecto real es mucho más alto que el de recibir un pedido inválido: si
 * el mail no existe, el que se queda sin demo es quien lo escribió mal.
 */
function pareceMail(v) {
  return /^[^@\s]+@[^@\s.]+\.[^@\s]+$/.test(v);
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "metodo_no_permitido" });
    return;
  }

  // Un formulario público que dispara mails es un amplificador de spam si no
  // tiene freno. El límite es por IP.
  //
  // `limitar` devuelve true cuando PERMITE (y false cuando ya respondió 429),
  // así que la guarda va negada. Escrito al revés, cortaría todos los pedidos
  // legítimos y dejaría pasar solo a los frenados.
  if (!limitar(req, res, "solicitar-demo", 5, 3600)) return;

  const b = req.body && typeof req.body === "object" ? req.body : {};
  const datos = {
    nombre: campo(b.nombre, MAX.nombre),
    email: campo(b.email, MAX.email),
    empresa: campo(b.empresa, MAX.empresa),
    pais: campo(b.pais, MAX.pais),
    mensaje: campo(b.mensaje, MAX.mensaje),
  };

  const faltan = ["nombre", "email", "empresa", "pais"].filter((k) => !datos[k]);
  if (faltan.length) {
    res.status(400).json({ error: "faltan_campos", campos: faltan });
    return;
  }
  if (!pareceMail(datos.email)) {
    res.status(400).json({ error: "email_invalido" });
    return;
  }

  const clave = process.env.RESEND_API_KEY;
  if (!clave) {
    // 503 y no 500: no está roto, falta configurarlo. Y el mensaje que ve el
    // visitante NO dice esto — dice que escriba directo al mail, así el
    // prospecto no se pierde por un problema nuestro.
    console.error("solicitar-demo: falta RESEND_API_KEY; pedido NO enviado de",
                  datos.email);
    res.status(503).json({ error: "sin_configurar", contacto: DESTINO });
    return;
  }

  const cuerpo =
    "Pedido de demo de MV Kobra AI\n\n" +
    `Nombre:  ${datos.nombre}\n` +
    `Empresa: ${datos.empresa}\n` +
    `País:    ${datos.pais}\n` +
    `Mail:    ${datos.email}\n\n` +
    (datos.mensaje ? `Mensaje:\n${datos.mensaje}\n\n` : "") +
    "Respondé a este mail para coordinar el 1:1.";

  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: "Bearer " + clave,
                 "Content-Type": "application/json" },
      body: JSON.stringify({
        from: remitente(),
        to: [DESTINO],
        // `reply_to` con el mail del prospecto: contestás desde tu casilla y
        // le llega a él, sin copiar y pegar la dirección.
        reply_to: datos.email,
        subject: `Demo · ${datos.empresa} (${datos.pais}) · ${datos.nombre}`,
        text: cuerpo,
      }),
    });
    if (!r.ok) {
      // El pedido queda en el log del servidor: un prospecto no se pierde
      // porque el proveedor de mail tuvo un mal minuto.
      console.error("solicitar-demo: Resend rechazó el envío", r.status,
                    await r.text(), "| pedido:", JSON.stringify(datos));
      res.status(502).json({ error: "no_se_pudo_enviar", contacto: DESTINO });
      return;
    }
  } catch (e) {
    console.error("solicitar-demo: excepción al enviar", e,
                  "| pedido:", JSON.stringify(datos));
    res.status(502).json({ error: "no_se_pudo_enviar", contacto: DESTINO });
    return;
  }

  res.status(200).json({ ok: true });
};

module.exports.campo = campo;
module.exports.pareceMail = pareceMail;
module.exports.DESTINO = DESTINO;
