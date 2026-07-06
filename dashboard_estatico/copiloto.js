/* MV Kobra AI · Copiloto de Negociación — motor offline en JS
 * Port del motor Python (kobra/copiloto.py): análisis de sentimiento,
 * emociones, técnicas, calidad y asesoría en vivo. Funciona sin backend.
 */
(function (global) {
  const POS = ["gracias","perfecto","excelente","bien","buenisimo","genial","acepto",
    "dale","listo","ok","okey","acuerdo","puedo","quiero","pago","pagar","abonar","abono",
    "solucion","ayuda","ayudar","tranquilo","tranquila","conforme","contento","contenta",
    "agradezco","dispuesto","dispuesta","dispongo","coordinar","coordinamos","compromiso",
    "comprometo","cuota","cuotas","cerramos","cerrar","hecho"];
  const NEG = ["no","nunca","imposible","problema","problemas","molesto","molesta","cansado",
    "cansada","harto","harta","mal","peor","pesimo","reclamo","queja","enojado","enojada",
    "bronca","estafa","mentira","mienten","verguenza","amenaza","abogado","denuncia","denunciar",
    "desocupado","desempleado","endeudado","urgente","grave","basta","dejen","acoso",
    "hostigamiento","presion","cortar","colgar","cuelgo","nervioso","nerviosa","preocupado",
    "preocupada","angustia","angustiado","dificil"];
  const BOOST = ["muy","super","recontra","demasiado","bastante","tan"];
  const NEGATORS = ["no","nunca","jamas","tampoco","ni"];

  const EMOCIONES = {
    frustracion: /(harto|harta|cansad|otra vez|siempre lo mismo|ya les dije|basta|hasta cuando)/,
    enojo: /(enojad|bronca|indignad|estafa|mentira|verguenza|amenaz|denunci|abogad|acoso)/,
    ansiedad: /(nervios|angustia|preocupad|no se que hacer|desesperad|urgente|ayuda por favor)/,
    dificultad_economica: /(sin (plata|dinero|trabajo)|desemplead|desocupad|no me alcanza|no llego|no tengo)/,
    satisfaccion: /(gracias|perfecto|excelente|buenisimo|genial|de acuerdo|me sirve|tranquil)/,
    intencion_pago: /(quiero pagar|puedo pagar|voy a pagar|como (pago|abono)|acepto|dale|coordinamos|me sirve)/,
    objecion: /(pero|el tema es|el problema es|no puedo|es mucho|no me alcanza|mas adelante|despues)/,
  };
  const TECNICAS = {
    Anclaje: /(el total es|la deuda total|monto total|son \$?\s?\d)/,
    Fraccionamiento: /(cuotas?|en partes|dividir|fraccionar|50%|mitad|una parte)/,
    Alternativas: /(opcion|alternativa|o bien|otra posibilidad|le ofrezco|puede elegir|tambien puede)/,
    Reciprocidad: /(si (usted|hace|paga).*(yo|le|hacemos|bonific)|a cambio|por su parte)/,
    Urgencia: /(hoy|ahora|antes de|valid[ao] hasta|por tiempo limitado|vence|ultimo dia|solo por hoy)/,
    Escasez: /(beneficio unico|oferta especial|solo (por hoy|esta semana)|no lo vamos a repetir|excepcion)/,
    Validacion: /(entiendo|comprendo|me pongo en su lugar|se que|imagino que|tiene razon)/,
    Cierre: /(coordinamos|le envio el (link|qr)|queda acordado|entonces quedamos|confirmamos)/,
  };

  const strip = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

  function sentimiento(texto) {
    const toks = strip(texto).split(/\s+/).filter(Boolean);
    let score = 0;
    for (let i = 0; i < toks.length; i++) {
      let val = POS.includes(toks[i]) ? 1 : NEG.includes(toks[i]) ? -1 : 0;
      if (val !== 0) {
        if (i > 0 && BOOST.includes(toks[i - 1])) val *= 1.6;
        for (let j = Math.max(0, i - 2); j < i; j++) if (NEGATORS.includes(toks[j])) val *= -0.8;
        score += val;
      }
    }
    const n = Math.max(toks.length, 1);
    let norm = Math.max(-1, Math.min(1, score / Math.sqrt(n)));
    const etiqueta = norm > 0.15 ? "positivo" : norm < -0.15 ? "negativo" : "neutro";
    const s = strip(texto);
    const emo = Object.keys(EMOCIONES).filter(e => EMOCIONES[e].test(s));
    return { score: +norm.toFixed(3), etiqueta, emociones: emo };
  }

  function parse(texto) {
    const raw = texto.split(/\n/).map(l => l.trim()).filter(Boolean);
    const wa = /^\[?\d{1,2}\/\d{1,2}\/\d{2,4},?\s*\d{1,2}:\d{2}(?::\d{2})?\]?\s*-?\s*([^:]{1,40}):\s*(.+)$/;
    const plain = /^([^:]{1,25}):\s*(.+)$/;
    const items = [];
    for (const line of raw) {
      let m = line.match(wa) || line.match(plain);
      if (m) items.push([m[1].trim(), m[2].trim()]);
      else if (items.length) items[items.length - 1][1] += " " + line;
    }
    if (!items.length) return { turnos: [], gestor: "Gestor", cliente: "Cliente" };
    const nombres = items.map(i => i[0]);
    const counts = {}; nombres.forEach(n => counts[n] = (counts[n] || 0) + 1);
    const gestor = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
    const cliente = [...new Set(nombres)].find(n => n !== gestor) || "Cliente";
    const turnos = items.map(([nombre, texto], i) => ({
      orden: i, emisor: nombre === gestor ? "gestor" : "cliente", nombre, texto,
    }));
    return { turnos, gestor, cliente };
  }

  const CRIT = [
    ["saludo_inicial", "Saludo Inicial", 5, /(hola|buenos dias|buenas tardes|buen dia)/, true],
    ["identificacion", "Identificación", 5, /(soy|le habla|mi nombre|de parte de|del area)/],
    ["validacion_datos", "Validación Datos", 10, /(confirm|verific|es usted|hablo con|su documento|sus datos)/],
    ["empatia", "Empatía", 15, /(entiendo|comprendo|me pongo en su lugar|tranquil|se que)/],
    ["claridad", "Claridad", 10, null],
    ["solucion", "Solución", 15, /(le ofrezco|opcion|alternativa|plan|cuotas?|descuento|facilidad)/],
    ["objeciones", "Manejo Objeciones", 15, /(entiendo (pero|que)|de todas formas|le propongo|podemos|que le parece)/],
    ["cierre", "Cierre", 15, /(coordinamos|le envio|queda acordado|confirmamos|entonces quedamos|link|qr)/],
    ["registro", "Registro", 10, /(le envio (el|un) (comprobante|resumen|detalle)|por escrito|le llega|confirmacion)/],
  ];

  function calidad(turnos) {
    const g = turnos.filter(t => t.emisor === "gestor").map(t => t.texto);
    const gtxt = strip(g.join(" "));
    const prim = g.length ? strip(g[0]) : "";
    const avg = g.length ? g.reduce((a, x) => a + x.length, 0) / g.length : 0;
    let total = 0, sumaPesos = 0; const det = [];
    for (const [id, nombre, peso, re, usaPrim] of CRIT) {
      let cumple;
      if (id === "claridad") cumple = gtxt.length > 0 && avg < 320;
      else cumple = re.test(usaPrim ? prim : gtxt);
      const sc = cumple ? 100 : 35;
      total += sc * peso / 100; sumaPesos += peso;
      det.push({ nombre, peso, score: sc, cumple });
    }
    return { score_total: +(total / sumaPesos * 100).toFixed(1), criterios: det };
  }

  function tecnicas(turnos) {
    const gtxt = strip(turnos.filter(t => t.emisor === "gestor").map(t => t.texto).join(" "));
    const out = {}; for (const k in TECNICAS) out[k] = TECNICAS[k].test(gtxt); return out;
  }

  function clima(scores) {
    if (!scores.length) return 0;
    let num = 0, den = 0;
    scores.forEach((s, i) => { num += s * (i + 1); den += (i + 1); });
    return num / den;
  }

  function sugerencias(turnos, sents, probpago, estrategia) {
    const cliIdx = turnos.map((t, i) => t.emisor === "cliente" ? i : -1).filter(i => i >= 0);
    const cliSent = cliIdx.map(i => sents[i].score);
    const cl = clima(cliSent);
    const emo = new Set(); cliIdx.forEach(i => sents[i].emociones.forEach(e => emo.add(e)));
    const tips = [];
    if (emo.has("enojo")) tips.push(["🔴 Cliente enojado", "Bajá el ritmo, validá su malestar ANTES de ofrecer. Evitá justificar."]);
    if (emo.has("frustracion")) tips.push(["🟠 Frustración", "Reconocé el historial y ofrecé algo concreto y distinto a lo anterior."]);
    if (emo.has("ansiedad")) tips.push(["🟠 Ansiedad", "Transmití calma y pasos claros y cortos: 'hagamos una sola cosa hoy'."]);
    if (emo.has("dificultad_economica")) tips.push(["💸 Dificultad económica", "Priorizá plan de cuotas o quita; no presiones el pago total."]);
    if (emo.has("intencion_pago") || cl > 0.2) tips.push(["🟢 Señal de compra", "Clima favorable: CERRÁ ahora con fecha y medio de pago."]);
    if (emo.has("objecion") && cl <= 0.2) tips.push(["🟡 Objeción activa", "No rebatas de frente: '¿qué parte le complica?' y ofrecé 2 alternativas."]);
    if (probpago != null) {
      if (probpago >= 0.65) tips.push(["📈 Alta propensión", "Apuntá a pago total o cuota inicial fuerte; poca o nula quita."]);
      else if (probpago < 0.35) tips.push(["📉 Baja propensión", "Asegurá CUALQUIER pago: habilitá quita/plan largo y compromiso escrito."]);
    }
    if (estrategia) tips.push(["🎯 Estrategia sugerida", `Guion recomendado por MV Kobra AI: «${estrategia}».`]);
    let next;
    if (cl > 0.2 || emo.has("intencion_pago")) next = "Perfecto, coordinemos: le envío ahora el link de pago y le llega el comprobante. ¿Le queda cómodo?";
    else if (emo.has("enojo") || emo.has("frustracion")) next = "Entiendo su molestia y quiero resolverlo hoy mismo. Le propongo una opción hecha a su medida, ¿la vemos?";
    else if (emo.has("dificultad_economica")) next = "Sin problema, busquemos algo acorde a su situación. ¿Cuánto podría afrontar este mes?";
    else next = "¿Qué le parece si lo dividimos en cuotas cómodas y arrancamos con una hoy?";
    if (!tips.length) tips.push(["🟢 Todo en orden", "Mantené el tono y avanzá hacia el cierre con una propuesta concreta."]);
    return { clima: +cl.toFixed(3), clima_etiqueta: cl > 0.15 ? "positivo" : cl < -0.15 ? "negativo" : "neutro",
      emociones_cliente: [...emo].sort(), sugerencias: tips, proxima_frase: next };
  }

  function analizar(texto, probpago, estrategia) {
    const { turnos } = parse(texto);
    const sents = turnos.map(t => sentimiento(t.texto));
    return {
      turnos, sents,
      calidad: calidad(turnos),
      tecnicas: tecnicas(turnos),
      copiloto: sugerencias(turnos, sents, probpago, estrategia),
    };
  }

  global.KobraCopiloto = { analizar, sentimiento, parse };
})(window);
