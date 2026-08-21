// © 2026 Martín Viera. Todos los derechos reservados.

// Verifica la credencial del dueño (`mail|codigo`) desde Node.
//
// Es la MISMA credencial que desbloquea el programa, con los mismos
// parámetros de scrypt: así el monitor de ventas no agrega un secreto más
// para configurar. Ya hay bastantes.
//
// La sal y el hash se copian de `kobra/owner.py`, que documenta por qué son
// publicables: sin el código no sirven de nada — scrypt es deliberadamente
// caro y el código tiene ~125 bits. Que estén duplicados en dos lenguajes es
// el riesgo real (rotás en Python y acá queda el viejo), y por eso
// `api/owner-auth.test.js` falla si dejan de coincidir.
const crypto = require("crypto");

const EMAIL = "vieraschiavi@gmail.com";
const SAL = Buffer.from("13c8a3fa47e247bd5fc3d4b2650c8ccb", "hex");
const HASH = Buffer.from(
  "d6a1711f7c425876f1a75c5b84c86236fb8459c78a3bee8e1c64237d63eb6d61", "hex");

// _N, _R, _P, _DKLEN y _MAXMEM de kobra/owner.py. `maxmem` explícito: el
// default de OpenSSL (32 MB) no alcanza para N=2^15 y tira "memory limit
// exceeded" — el mismo motivo que documenta el lado Python.
const PARAMS = { N: 32768, r: 8, p: 1, maxmem: 67108864 };
const DKLEN = 32;
const SEPARADOR = "|";

/** `"mail|codigo"` → `{mail, codigo}`, o null si no tiene esa forma. */
function partir(texto) {
  if (typeof texto !== "string") return null;
  const i = texto.indexOf(SEPARADOR);
  if (i <= 0 || i === texto.length - 1) return null;
  return {
    mail: texto.slice(0, i).trim().toLowerCase(),
    codigo: texto.slice(i + 1).trim(),
  };
}

/**
 * ¿`texto` es la credencial del dueño?
 *
 * Compara en tiempo constante los DOS campos. Con `===` el tiempo de
 * respuesta filtra cuántos bytes coincidieron; y comparar el mail rápido
 * delataría que el mail es correcto y solo falla el código.
 */
function esOwner(texto) {
  const partes = partir(texto);
  if (partes === null) return false;

  const mailEsperado = Buffer.from(EMAIL.toLowerCase(), "utf8");
  const mailRecibido = Buffer.from(partes.mail, "utf8");
  const mailOk = mailRecibido.length === mailEsperado.length &&
    crypto.timingSafeEqual(mailRecibido, mailEsperado);

  let codigoOk = false;
  try {
    const derivado = crypto.scryptSync(partes.codigo, SAL, DKLEN, PARAMS);
    codigoOk = crypto.timingSafeEqual(derivado, HASH);
  } catch {
    codigoOk = false;   // código vacío o scrypt sin memoria: no es la credencial
  }
  return mailOk && codigoOk;
}

/**
 * Corta el pedido si no viene la credencial del dueño.
 * Devuelve true si YA respondió (o sea: el handler tiene que cortar).
 */
function exigirOwner(req, res) {
  const cabecera = req.headers?.authorization || "";
  const credencial = cabecera.startsWith("Bearer ")
    ? cabecera.slice(7)
    : (req.body && req.body.credencial) || "";
  if (esOwner(credencial)) return false;
  // 401 y no 403: falta autenticarse, no es un permiso denegado. Sin detalles
  // sobre qué parte falló.
  res.status(401).json({ error: "credencial_invalida" });
  return true;
}

module.exports = { esOwner, exigirOwner, partir, EMAIL, SAL, HASH, PARAMS, DKLEN };
