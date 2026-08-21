// © 2026 Martín Viera. Todos los derechos reservados.

// Monitor del negocio: cuántos clientes, cuánta plata, cuántas descargas.
//
// No hay base de datos, y no hace falta ninguna. El webhook de MercadoPago
// entrega la licencia por mail y no persiste nada, así que hasta acá no
// existía forma de saber cuánto se vendió. Pero el libro de ventas ya existe
// en dos lugares que son la fuente de verdad:
//
//   * **MercadoPago** sabe cada pago: monto, moneda, fecha, estado y qué plan
//     (viaja en `metadata.plan`, que pone nuestro propio checkout).
//   * **GitHub Releases** cuenta cada descarga del instalador en
//     `assets[].download_count`.
//
// Consultar esas dos APIs es más honesto que llevar un contador propio: un
// contador se desincroniza en cuanto un webhook se pierde o se reintenta, y
// ya vimos que los reintentos existen. Acá el número sale de donde está la
// plata de verdad.
//
// Lo que NO hace: descontar comisiones ni impuestos. MercadoPago informa el
// monto bruto y el neto acreditado por pago; el neto que devolvemos es la
// suma de lo que MercadoPago dice que quedó, no una estimación nuestra.
const { exigirOwner } = require("./_owner_auth");

const MP = "https://api.mercadopago.com";
const REPO_DESCARGAS = "vieraschiavi/mv-kobra-ai-releases";

/** Pide una página de pagos aprobados. MercadoPago pagina de a 50. */
async function paginaDePagos(token, offset, desde) {
  const q = new URLSearchParams({
    status: "approved",
    sort: "date_created",
    criteria: "desc",
    limit: "50",
    offset: String(offset),
  });
  if (desde) {
    q.set("range", "date_created");
    q.set("begin_date", desde);
    q.set("end_date", "NOW");
  }
  const r = await fetch(`${MP}/v1/payments/search?${q}`, {
    headers: { Authorization: "Bearer " + token },
  });
  if (!r.ok) {
    const detalle = await r.text();
    const e = new Error("mercadopago_error");
    e.status = r.status;
    e.detalle = detalle.slice(0, 300);
    throw e;
  }
  return r.json();
}

/**
 * Todos los pagos aprobados, paginando.
 *
 * Tope de 40 páginas (2.000 pagos): sin él, un error de la API que devuelva
 * siempre resultados dejaría la función colgada hasta que Vercel la mate, y
 * el monitor no mostraría nada en vez de mostrar casi todo.
 */
async function todosLosPagos(token, desde) {
  const pagos = [];
  let truncado = false;
  for (let pagina = 0; pagina < 40; pagina++) {
    const d = await paginaDePagos(token, pagina * 50, desde);
    const lote = d.results || [];
    pagos.push(...lote);
    if (lote.length < 50) return { pagos, truncado };
    truncado = true;   // hay al menos una página más
  }
  return { pagos, truncado };
}

/** Descargas del instalador, por versión. Repo público: no necesita token. */
async function descargas() {
  try {
    const r = await fetch(
      `https://api.github.com/repos/${REPO_DESCARGAS}/releases?per_page=100`,
      { headers: { Accept: "application/vnd.github+json" } });
    if (!r.ok) {
      // 404 = el repo público todavía no existe (o no tiene releases). Es el
      // estado real hasta que se configure RELEASES_TOKEN, y no es un error
      // del monitor: se informa como tal en vez de romper la pantalla.
      return { total: 0, por_version: [], disponible: false,
               motivo: r.status === 404
                 ? "el repo público de descargas no existe o no tiene releases"
                 : `github respondió ${r.status}` };
    }
    const releases = await r.json();
    const por_version = releases.map((rel) => ({
      version: rel.tag_name,
      fecha: rel.published_at,
      descargas: (rel.assets || [])
        .filter((a) => a.name.endsWith(".exe"))
        .reduce((s, a) => s + (a.download_count || 0), 0),
    }));
    return {
      total: por_version.reduce((s, v) => s + v.descargas, 0),
      por_version,
      disponible: true,
    };
  } catch (e) {
    return { total: 0, por_version: [], disponible: false,
             motivo: String(e).slice(0, 200) };
  }
}

function resumir(pagos) {
  const porPlan = {};
  const porMes = {};
  const clientes = new Set();
  let bruto = 0, neto = 0;

  for (const p of pagos) {
    const plan = (p.metadata && p.metadata.plan) || "sin_plan";
    const monto = Number(p.transaction_amount) || 0;
    // `net_received_amount` es lo que MercadoPago acreditó de verdad: el
    // bruto menos su comisión. Si no viene, se cae al bruto y se avisa.
    const recibido = Number(
      p.transaction_details?.net_received_amount ?? monto) || 0;
    const mes = String(p.date_approved || p.date_created || "").slice(0, 7);
    const quien = (p.payer && (p.payer.email || p.payer.id)) || p.id;

    bruto += monto;
    neto += recibido;
    clientes.add(String(quien));

    porPlan[plan] = porPlan[plan] || { plan, ventas: 0, bruto: 0, neto: 0 };
    porPlan[plan].ventas += 1;
    porPlan[plan].bruto += monto;
    porPlan[plan].neto += recibido;

    if (mes) {
      porMes[mes] = porMes[mes] || { mes, ventas: 0, bruto: 0, neto: 0 };
      porMes[mes].ventas += 1;
      porMes[mes].bruto += monto;
      porMes[mes].neto += recibido;
    }
  }

  const redondear = (o) => ({ ...o, bruto: Math.round(o.bruto * 100) / 100,
                              neto: Math.round(o.neto * 100) / 100 });
  return {
    ventas: pagos.length,
    clientes: clientes.size,
    bruto: Math.round(bruto * 100) / 100,
    neto: Math.round(neto * 100) / 100,
    comision: Math.round((bruto - neto) * 100) / 100,
    moneda: pagos[0]?.currency_id || null,
    por_plan: Object.values(porPlan).map(redondear)
      .sort((a, b) => b.neto - a.neto),
    por_mes: Object.values(porMes).map(redondear)
      .sort((a, b) => a.mes.localeCompare(b.mes)),
  };
}

module.exports = async function handler(req, res) {
  if (exigirOwner(req, res)) return;

  const token = process.env.MP_ACCESS_TOKEN;
  if (!token) {
    res.status(503).json({
      error: "sin_configurar",
      detalle: "Falta MP_ACCESS_TOKEN: sin esa credencial no hay forma de " +
               "consultar las ventas. Cargala en Vercel.",
    });
    return;
  }

  try {
    const desde = typeof req.query?.desde === "string" ? req.query.desde : "";
    const [{ pagos, truncado }, desc] = await Promise.all([
      todosLosPagos(token, desde),
      descargas(),
    ]);
    const resumen = resumir(pagos);
    res.status(200).json({
      ...resumen,
      truncado,   // true = hay más de 2.000 pagos y esto es un parcial
      descargas: desc,
      // Sirve para saber si el número es de HOY o de una respuesta cacheada.
      generado: new Date().toISOString(),
    });
  } catch (e) {
    if (e.message === "mercadopago_error") {
      res.status(502).json({ error: "mercadopago_error", status: e.status,
                             detalle: e.detalle });
      return;
    }
    console.error("monitor: falló", e);
    res.status(500).json({ error: "interno" });
  }
};

module.exports.resumir = resumir;
