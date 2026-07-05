// Copiloto de cobranzas con Claude — función serverless (Vercel).
// La API key vive SOLO acá, del lado del servidor, como variable de entorno
// (ANTHROPIC_API_KEY). Nunca se expone al navegador ni se guarda en el repo.

const MODEL = "claude-haiku-4-5-20251001";   // rápido y económico para la demo
const MAX_INPUT = 4000;                        // límite de caracteres de entrada
const MAX_TOKENS = 500;                        // límite de salida (control de costo)

export default async function handler(req, res) {
  if (req.method !== "POST") { res.status(405).json({ error: "method" }); return; }

  // Solo aceptar pedidos desde nuestra propia web (mitiga abuso del endpoint público)
  const origin = req.headers.origin || "";
  if (origin && !/(^https:\/\/kobra-ia\.vercel\.app$)|(\.vercel\.app$)|(localhost)/.test(origin)) {
    res.status(403).json({ error: "origin" }); return;
  }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) { res.status(500).json({ error: "no_key" }); return; }

  const body = typeof req.body === "string" ? safeJson(req.body) : (req.body || {});
  const texto = String(body.texto || "").slice(0, MAX_INPUT).trim();
  if (!texto) { res.status(400).json({ error: "empty" }); return; }

  const prompt =
    "Sos un copiloto experto en cobranzas para un gestor humano. Analizá la siguiente " +
    "conversación con un deudor y devolvé ÚNICAMENTE un objeto JSON válido (sin texto " +
    "alrededor, sin markdown) con estas claves:\n" +
    '{"sentimiento":"Positivo|Neutro|Negativo","temperatura":<0-100, disposición del cliente a pagar>,' +
    '"tecnicas":[<técnicas de negociación que conviene usar, 2 a 4 strings cortos>],' +
    '"proxima_jugada":"<qué debería hacer el gestor ahora, 1 frase>",' +
    '"guion":"<exactamente qué decir ahora, tono uruguayo, 1-2 frases>"}\n\n' +
    "Respetá la ley (no amenazar, no hostigar). Conversación:\n\"\"\"\n" + texto + "\n\"\"\"";

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
    res.status(200).json({ ok: true, analisis, raw: text });
  } catch (e) {
    res.status(500).json({ error: "exception", detail: String(e).slice(0, 200) });
  }
}

function safeJson(s) { try { return JSON.parse(s); } catch (e) { return {}; } }
