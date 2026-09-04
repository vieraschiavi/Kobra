// © 2026 Martín Viera. Todos los derechos reservados.

// Registro durable de los pedidos de demo.
//
// El agujero que tapa: `solicitar-demo.js` mandaba el pedido por mail y, si el
// mail fallaba —o si faltaba RESEND_API_KEY—, el prospecto quedaba SOLO en un
// `console.error` de una función serverless. Los logs de Vercel se rotan y no
// se consultan; en la práctica ese prospecto estaba perdido. El pedido se
// guarda ANTES de intentar el mail, por el mismo motivo: un proveedor caído no
// puede costar un lead.
//
// Y responde la pregunta que motivó esto: "¿a cuántos y a qué mails les mandé
// una demo?". Cada pedido queda con un `id` corto, que es el enganche para
// atribuir una copia filtrada del programa a la demo concreta de la que salió.
//
// Dónde se guarda: Edge Config, el único almacén durable que ya tiene este
// proyecto (lo usa `copiloto.js` para el contador global). No es una base de
// datos y no pretende serlo:
//
//   * La escritura es leer-modificar-escribir, así que dos pedidos en el mismo
//     segundo pueden pisarse. Los pedidos de demo llegan de a uno cada tantos
//     días y hay freno de 5/hora por IP: el costo de esa carrera es perder un
//     registro que igual salió por mail, y la alternativa era montar una base
//     entera para un puñado de filas al mes.
//   * El store es chico (el plan Hobby son pocos KB), así que la lista se poda
//     por BYTES y no por cantidad: ver `podar`.
//
// Nada de acá levanta una excepción. Si el registro falla, el pedido tiene que
// seguir su camino igual.
const EC = process.env.EDGE_CONFIG_ID;
const VT = process.env.VC_API_TOKEN;
const TEAM = process.env.VC_TEAM_ID;

const CLAVE = "demos_pedidas";
// Presupuesto de bytes del JSON guardado. Deliberadamente por debajo del tope
// del plan más chico: un PATCH rechazado por tamaño no pierde un pedido, los
// pierde TODOS, porque deja de escribirse la lista entera.
const MAX_BYTES = 6000;

function base() {
  return "https://api.vercel.com/v1/edge-config/" + EC;
}

/** ¿Está configurado el almacén? Sin las tres variables, no hay dónde guardar. */
function disponible() {
  return !!(EC && VT && TEAM);
}

/** Lee la lista guardada. Devuelve `[]` ante cualquier problema. */
async function listar() {
  if (!disponible()) return [];
  try {
    const r = await fetch(`${base()}/item/${CLAVE}?teamId=${TEAM}`,
      { headers: { Authorization: "Bearer " + VT } });
    if (!r.ok) return [];
    const d = await r.json();
    return Array.isArray(d && d.value) ? d.value : [];
  } catch {
    return [];
  }
}

/**
 * Recorta la lista hasta que entre en `MAX_BYTES`, tirando los más viejos.
 *
 * Podar por cantidad obligaría a adivinar cuánto ocupa un pedido (el nombre de
 * una empresa puede ser 3 caracteres o 120), y adivinar de más rompe la
 * escritura entera. Medir el JSON real no se equivoca.
 */
function podar(lista) {
  let podada = lista;
  while (podada.length > 1 &&
         Buffer.byteLength(JSON.stringify(podada), "utf8") > MAX_BYTES) {
    podada = podada.slice(1);
  }
  return podada;
}

/** Un id corto y legible para atribuir después una copia a esta demo. */
function nuevoId() {
  return Math.random().toString(36).slice(2, 8) +
         Date.now().toString(36).slice(-4);
}

/**
 * Guarda un pedido. Devuelve el id asignado, o `null` si no se pudo guardar.
 *
 * No guarda el `mensaje`: es texto libre sin tope útil para el presupuesto de
 * bytes, y su lugar es el mail, que sí lo lleva entero.
 */
async function guardar(datos) {
  if (!disponible()) return null;
  const id = nuevoId();
  const entrada = {
    id,
    fecha: new Date().toISOString(),
    nombre: datos.nombre,
    email: datos.email,
    empresa: datos.empresa,
    pais: datos.pais,
  };
  try {
    const lista = podar([...(await listar()), entrada]);
    const r = await fetch(`${base()}/items?teamId=${TEAM}`, {
      method: "PATCH",
      headers: { Authorization: "Bearer " + VT,
                 "Content-Type": "application/json" },
      body: JSON.stringify({
        items: [{ operation: "upsert", key: CLAVE, value: lista }],
      }),
    });
    return r.ok ? id : null;
  } catch {
    return null;
  }
}

module.exports = { guardar, listar, disponible, podar, MAX_BYTES, CLAVE };
