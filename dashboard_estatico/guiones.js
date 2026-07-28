// MV Kobra AI · Guiones de las demos animadas, en los tres idiomas del producto.
//
// Antes vivían escritos a mano dentro de index.html, solo en castellano: elegir
// portugués o inglés en el sitio no cambiaba nada de la llamada ni del chat.
//
// Es un .js y no un .json a propósito: el demo offline se abre con doble clic
// (protocolo file://), donde `fetch` de un archivo local está bloqueado por
// CORS. Un <script> se carga siempre.
//
// Formato estricto `window.GUIONES = {...};` — `data/generar_audio_demo_voz.py`
// lee este mismo archivo para sintetizar el audio, así que texto en pantalla y
// audio no se pueden desincronizar.
//
// Sobre la moneda: los importes quedan en pesos en los tres idiomas porque el
// tablero que se ve al lado muestra la cartera sintética en pesos uruguayos.
// Traducir la moneda en el guion y no en los datos dejaría la demo incoherente.
window.GUIONES = {
  "es": {
    "nombre": "Español",
    "llamada": [
      {"who": "ia", "text": "Buenos días, hablo de MV Kobra AI en representación de su entidad financiera. ¿Hablo con Juan Pérez?"},
      {"who": "cliente", "text": "Sí, soy yo."},
      {"who": "ia", "text": "Lo contacto por un saldo pendiente de 6.000 pesos con más de 60 días de atraso. ¿Podemos revisar juntos las opciones de pago disponibles?"},
      {"who": "cliente", "text": "La verdad ahora no puedo pagar todo junto, estoy complicado económicamente."},
      {"who": "ia", "text": "Entiendo la situación. Puedo ofrecerle cancelar hoy con un 5% de descuento, quedando en 5.700 pesos, o dividirlo en 3 cuotas de 1.900 pesos sin recargo. ¿Cuál se ajusta mejor a su situación?"},
      {"who": "cliente", "text": "Prefiero las 3 cuotas."},
      {"who": "ia", "text": "Perfecto. Le voy a enviar por WhatsApp el link de pago de la primera cuota, con vencimiento en 5 días. ¿Confirma este número para el envío?"},
      {"who": "cliente", "text": "Sí, confirmo."},
      {"who": "ia", "text": "Excelente. Quedó registrado el acuerdo de pago en 3 cuotas. Muchas gracias por su tiempo, que tenga un buen día."}
    ],
    "whatsapp": [
      {"who": "ia", "text": "Hola Juan 👋 Soy el asistente de cobranzas de su entidad financiera. Tiene un saldo pendiente de $U 6.000 con más de 60 días de atraso. ¿Quiere que veamos opciones para regularizarlo?"},
      {"who": "cliente", "text": "Hola, sí. Ahora no puedo pagar todo junto."},
      {"who": "ia", "text": "No hay problema. Puedo ofrecerle: 1) Pagar hoy $U 5.700 (5% de descuento), o 2) 3 cuotas de $U 1.900 sin recargo. ¿Cuál prefiere?"},
      {"who": "cliente", "text": "Las 3 cuotas, por favor."},
      {"who": "ia", "text": "Perfecto ✅ Le comparto el link de pago de la primera cuota: kobra.pay/ab12c9 — vence en 5 días."},
      {"who": "cliente", "text": "Listo, muchas gracias."}
    ],
    "ui": {
      "etiqueta_ia": "🤖 MV Kobra AI (voz)",
      "etiqueta_cliente": "👤 Cliente",
      "en_curso_voz": "🔊 Llamada en curso (voz real)…",
      "en_curso_nav": "🔊 Llamada en curso (con voz)…",
      "en_curso": "🔊 Llamada en curso…",
      "detenida": "⏹ Detenida",
      "finalizada": "✓ Llamada finalizada · Duración 00:42 · Acuerdo de pago en 3 cuotas · sincronizado al ERP",
      "idioma": "Idioma"
    }
  },
  "pt": {
    "nombre": "Português",
    "llamada": [
      {"who": "ia", "text": "Bom dia, falo da MV Kobra AI em nome da sua instituição financeira. Falo com João Pereira?"},
      {"who": "cliente", "text": "Sim, sou eu."},
      {"who": "ia", "text": "Estou entrando em contato por um saldo pendente de 6.000 pesos com mais de 60 dias de atraso. Podemos ver juntos as opções de pagamento disponíveis?"},
      {"who": "cliente", "text": "Na verdade, agora não consigo pagar tudo de uma vez, estou apertado financeiramente."},
      {"who": "ia", "text": "Entendo a situação. Posso oferecer quitar hoje com 5% de desconto, ficando em 5.700 pesos, ou dividir em 3 parcelas de 1.900 pesos sem juros. Qual se encaixa melhor na sua situação?"},
      {"who": "cliente", "text": "Prefiro as 3 parcelas."},
      {"who": "ia", "text": "Perfeito. Vou enviar pelo WhatsApp o link de pagamento da primeira parcela, com vencimento em 5 dias. Confirma este número para o envio?"},
      {"who": "cliente", "text": "Sim, confirmo."},
      {"who": "ia", "text": "Excelente. O acordo de pagamento em 3 parcelas ficou registrado. Muito obrigado pelo seu tempo, tenha um bom dia."}
    ],
    "whatsapp": [
      {"who": "ia", "text": "Olá João 👋 Sou o assistente de cobrança da sua instituição financeira. Você tem um saldo pendente de $U 6.000 com mais de 60 dias de atraso. Quer ver as opções para regularizar?"},
      {"who": "cliente", "text": "Oi, quero. Agora não consigo pagar tudo de uma vez."},
      {"who": "ia", "text": "Sem problema. Posso oferecer: 1) Pagar hoje $U 5.700 (5% de desconto), ou 2) 3 parcelas de $U 1.900 sem juros. Qual prefere?"},
      {"who": "cliente", "text": "As 3 parcelas, por favor."},
      {"who": "ia", "text": "Perfeito ✅ Segue o link de pagamento da primeira parcela: kobra.pay/ab12c9 — vence em 5 dias."},
      {"who": "cliente", "text": "Pronto, muito obrigado."}
    ],
    "ui": {
      "etiqueta_ia": "🤖 MV Kobra AI (voz)",
      "etiqueta_cliente": "👤 Cliente",
      "en_curso_voz": "🔊 Chamada em andamento (voz real)…",
      "en_curso_nav": "🔊 Chamada em andamento (com voz)…",
      "en_curso": "🔊 Chamada em andamento…",
      "detenida": "⏹ Interrompida",
      "finalizada": "✓ Chamada finalizada · Duração 00:42 · Acordo de pagamento em 3 parcelas · sincronizado ao ERP",
      "idioma": "Idioma"
    }
  },
  "en": {
    "nombre": "English",
    "llamada": [
      {"who": "ia", "text": "Good morning, this is MV Kobra AI calling on behalf of your financial institution. Am I speaking with John Parker?"},
      {"who": "cliente", "text": "Yes, speaking."},
      {"who": "ia", "text": "I'm calling about an outstanding balance of 6,000 pesos, more than 60 days overdue. Can we go over the available payment options together?"},
      {"who": "cliente", "text": "Honestly, I can't pay it all at once right now, money is tight."},
      {"who": "ia", "text": "I understand. I can offer you a 5% discount if you settle today, bringing it to 5,700 pesos, or split it into 3 instalments of 1,900 pesos at no extra cost. Which one works better for you?"},
      {"who": "cliente", "text": "I'd rather do the 3 instalments."},
      {"who": "ia", "text": "Perfect. I'll send you the payment link for the first instalment on WhatsApp, due in 5 days. Can you confirm this number?"},
      {"who": "cliente", "text": "Yes, confirmed."},
      {"who": "ia", "text": "Excellent. The payment plan in 3 instalments has been recorded. Thank you for your time, have a good day."}
    ],
    "whatsapp": [
      {"who": "ia", "text": "Hi John 👋 I'm the collections assistant from your financial institution. You have an outstanding balance of $U 6,000, more than 60 days overdue. Would you like to look at the options to settle it?"},
      {"who": "cliente", "text": "Hi, yes. I can't pay it all at once right now."},
      {"who": "ia", "text": "No problem. I can offer you: 1) Pay $U 5,700 today (5% discount), or 2) 3 instalments of $U 1,900 at no extra cost. Which do you prefer?"},
      {"who": "cliente", "text": "The 3 instalments, please."},
      {"who": "ia", "text": "Perfect ✅ Here's the payment link for the first instalment: kobra.pay/ab12c9 — due in 5 days."},
      {"who": "cliente", "text": "Got it, thank you."}
    ],
    "ui": {
      "etiqueta_ia": "🤖 MV Kobra AI (voice)",
      "etiqueta_cliente": "👤 Customer",
      "en_curso_voz": "🔊 Call in progress (real voice)…",
      "en_curso_nav": "🔊 Call in progress (with voice)…",
      "en_curso": "🔊 Call in progress…",
      "detenida": "⏹ Stopped",
      "finalizada": "✓ Call ended · Duration 00:42 · Payment plan in 3 instalments · synced to the ERP",
      "idioma": "Language"
    }
  }
};

// Idioma activo del demo. Prioridad: ?lang= en la URL (sirve también offline,
// donde no hay localStorage compartido con el sitio) → lo que se eligió en la
// landing (mismo origen, misma clave) → el idioma del navegador → español.
window.IDIOMA_DEMO = (function () {
  var soportados = ['es', 'pt', 'en'];
  function normalizar(v) {
    if (!v) return null;
    v = String(v).toLowerCase().slice(0, 2);
    return soportados.indexOf(v) >= 0 ? v : null;
  }
  var url = null;
  try {
    url = normalizar(new URLSearchParams(window.location.search).get('lang'));
  } catch (e) { /* URLSearchParams falta en navegadores muy viejos */ }
  var guardado = null;
  try { guardado = normalizar(window.localStorage.getItem('kobra_lang')); } catch (e) {}
  var navegador = normalizar(navigator && navigator.language);
  return url || guardado || navegador || 'es';
})();
