// © 2026 Martín Viera. Todos los derechos reservados.

// El navegador graba en webm/opus (Chrome, Electron) o mp4 (Safari), y ni
// ElevenLabs ni el servidor de Kobra lo aceptan sin ffmpeg. En vez de exigir
// ffmpeg en cada instalación, la grabación se decodifica acá mismo y se manda
// como WAV mono de 16 bits: el formato que todo el mundo lee y del que el
// servidor sabe medir la duración.

const SR_DESTINO = 22050;   // de sobra para voz; la mitad de peso que 44,1 kHz

/**
 * @param {Blob} grabacion  lo que entregó el MediaRecorder
 * @returns {Promise<{wav: Blob, segundos: number}>}
 */
export async function aWav(grabacion) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  let audio;
  try {
    audio = await ctx.decodeAudioData(await grabacion.arrayBuffer());
  } finally {
    ctx.close();
  }
  // Remuestreo y paso a mono en un solo render: OfflineAudioContext mezcla
  // los canales al destino de 1 canal.
  const cuadros = Math.ceil(audio.duration * SR_DESTINO);
  const offline = new OfflineAudioContext(1, cuadros, SR_DESTINO);
  const fuente = offline.createBufferSource();
  fuente.buffer = audio;
  fuente.connect(offline.destination);
  fuente.start();
  const mono = (await offline.startRendering()).getChannelData(0);
  return { wav: codificar(mono, SR_DESTINO), segundos: audio.duration };
}

/** PCM float [-1, 1] → WAV PCM 16 bits. */
export function codificar(muestras, sr) {
  const datos = muestras.length * 2;
  const buf = new ArrayBuffer(44 + datos);
  const v = new DataView(buf);
  const texto = (pos, s) => { for (let i = 0; i < s.length; i++) v.setUint8(pos + i, s.charCodeAt(i)); };
  texto(0, "RIFF"); v.setUint32(4, 36 + datos, true); texto(8, "WAVE");
  texto(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);   // PCM
  v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  texto(36, "data"); v.setUint32(40, datos, true);
  for (let i = 0; i < muestras.length; i++) {
    const s = Math.max(-1, Math.min(1, muestras[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}
