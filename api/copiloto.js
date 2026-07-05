// Copiloto de cobranzas con Claude — función serverless (Vercel, CommonJS).
// La API key vive SOLO acá, del lado del servidor, como variable de entorno
// (ANTHROPIC_API_KEY). Nunca se expone al navegador ni se guarda en el repo.
//
// TOPE GLOBAL: cuenta los análisis en Edge Config (ai_count / ai_limit). Al llegar
// al límite (30 por defecto) devuelve 429 y, si hay RESEND_API_KEY, manda un mail.
// Para AMPLIAR el límite: subir "ai_limit" en el Edge Config (o pedírmelo).

const MODEL = "claude-haiku-4-5-20251001";
const MAX_INPUT = 4000;
const MAX_TOKENS = 500;

const EC = process.env.EDGE_CONFIG_ID;
const VT = process.env.VC_API_TOKEN;
const TEAM = process.env.VC_TEAM_ID;
const COUNTER_ON = !!(EC && VT && TEAM);
const ECBASE = "https://api.vercel.com/v1/edge-config/" + EC;

async function ecGet(key) {
  try {
    const r = await fetch(ECBASE + "/item/" + key + "?teamId=" + TEAM,
      { headers: { Authorization: "Bearer " + VT } });
    if (!r.ok) return null;
    const d = await r.json();
    return (d && typeof d.value !== "undefined") ? d.value : null;
  } catch (e) { return null; }
}
async function ecSet(key, value) {
  try {
    await fetch(ECBASE + "/items?teamId=" + TEAM, {
      method: "PATCH",
      headers: { Authorization: "Bearer " + VT, "Content-Type": "application/json" },
      body: JSON.stringify({ items: [{ operation: "update", key: key, value: value }] }),
    });
  } catch (e) {}
}
async function notifyOwner(limit) {
  if (!process.env.RESEND_API_KEY) return;
  try {
    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: "Bearer " + process.env.RESEND_API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: "Kobra IA <onboarding@resend.dev>",
        to: ["vieraschiavi@gmail.com"],
        subject: "Kobra: se agotaron las " + limit + " demos de IA en vivo",
        text: "La demo de IA en vivo llegó al tope de " + limit + " análisis. " +
              "Cuando quieras ampliar, subí 'ai_limit' en el Edge Config (o pedímelo).",
      }),
    });
  } catch (e) {}
}

module.exports = async (req, res) => {
  if (req.method !== "POST") { res.status(405).json({ error: "method" }); return; }

  // Acepta pedidos desde el propio host (sirve para *.vercel.app y para
  // cualquier dominio propio que se agregue después, sin tocar código),
  // más *.vercel.app (previews) y localhost (desarrollo).
  const origin = req.headers.origin || "";
  const host = req.headers.host || "";
  const sameHost = origin && host && origin.replace(/^https?:\/\//, "") === host;
  if (origin && !sameHost && !/(\.vercel\.app$)|(localhost)/.test(origin)) {
    res.status(403).json({ error: "origin" }); return;
  }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) { res.status(500).json({ error: "no_key" }); return; }

  const body = typeof req.body === "string" ? safeJson(req.body) : (req.body || {});
  const texto = String(body.texto || "").slice(0, MAX_INPUT).trim();
  if (!texto) { res.status(400).json({ error: "empty" }); return; }

  // ---- Tope global ----
  let count = 0, limit = 30;
  if (COUNTER_ON) {
    const c = await ecGet("ai_count");
    const l = await ecGet("ai_limit");
    count = (typeof c === "number") ? c : 0;
    limit = (typeof l === "number") ? l : 30;
    if (count >= limit) { res.status(429).json({ error: "limit", remaining: 0 }); return; }
  }

  const prompt =
    "Sos un copiloto experto en cobranzas para un gestor humano. Analizá la siguiente " +
    "conversación con un deudor y devolvé ÚNICAMENTE un objeto JSON válido (sin texto " +
    "alrededor, sin markdown) con estas claves:\n" +
    '{"sentimiento":"Positivo|Neutro|Negativo","temperatura":<0-100, disposición del cliente a pagar>,' +
    '"tecnicas":[<técnicas de negociación que conviene usar, 2 a 4 strings cortos>],' +
    '"proxima_jugada":"<qué debería hacer el gestor ahora, 1 frase>",' +
    '"guion":"<exactamente qué decir ahora, 1-2 frases, tono profesional y cordial, español neutro, SIN modismos ni jerga informal>"}\n\n' +
    "Respetá la ley (no amenazar, no hostigar). Mantené un registro formal y profesional en todo momento. " +
    "Conversación:\n\"\"\"\n" + texto + "\n\"\"\"";

  try {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: MAX_TOKENS,
        messages: [{ role: "user", content: prompt }],
      }),
    });
    const data = await r.json();
    if (!r.ok) {
      res.status(502).json({ error: "anthropic", detail: (data.error && data.error.message) || "" });
      return;
    }
    const text = (data.content && data.content[0] && data.content[0].text) || "";
    let analisis = null;
    const m = text.match(/\{[\s\S]*\}/);
    try { analisis = JSON.parse(m ? m[0] : text); } catch (e) { analisis = null; }

    let remaining = null;
    if (COUNTER_ON) {
      const nuevo = count + 1;
      await ecSet("ai_count", nuevo);
      remaining = Math.max(0, limit - nuevo);
      if (nuevo >= limit) await notifyOwner(limit);
    }
    res.status(200).json({ ok: true, analisis: analisis, raw: text, remaining: remaining });
  } catch (e) {
    res.status(500).json({ error: "exception", detail: String(e).slice(0, 200) });
  }
};

function safeJson(s) { try { return JSON.parse(s); } catch (e) { return {}; } }
