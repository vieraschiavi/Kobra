# 📞 Guía: hacer una llamada REAL con el Gestor IA (Twilio)

El modo **"Probar mi cartera"** del dashboard *simula* la conversación. Para que
el Gestor IA **hable de verdad** por teléfono, MV Kobra AI ya trae el flujo completo:
el bot **saluda, escucha, negocia y cierra** usando el **TTS y el reconocimiento
de voz en español de Twilio** — sin instalar nada de voz local.

Necesitás dos cosas que no dependen del código:

1. **Una cuenta de Twilio** con un número.
2. **Consentimiento** de la persona a la que vas a llamar. Empezá probando con
   **tu propio celular**.

---

## Cómo funciona (ya está implementado)

```
Twilio llama al número
   └─► pide TwiML a  /voz/entrante   → el Gestor IA saluda (dentro de <Gather>)
        └─► Twilio transcribe lo que dice el cliente → POST /voz/turno
             └─► el Gestor IA responde y negocia … (se repite)
                  └─► al cerrar: registra la gestión (aparece en el dashboard)
```

Endpoints en `realtime/server.py`: `/voz/entrante`, `/voz/turno`,
`/voz/llamar` (dispara la llamada saliente) y **`/llamar`** (página con
formulario y botón, sin consola).

---

## Paso a paso (primera llamada a tu propio celular)

### 1. Crear cuenta Twilio (gratis para probar)
- Registrate en <https://www.twilio.com/try-twilio>. La cuenta **trial** da
  crédito de prueba y permite llamar **solo a números verificados**: verificá tu
  propio celular en *Verified Caller IDs*.
- Anotá **Account SID** y **Auth Token** (Console → Account Info).

### 2. Cargar las credenciales en MV Kobra AI (sin código)
- En el **dashboard → pestaña ⚙️ Configuración**, ingresá:
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`. Quedan guardadas.

### 3. Conseguir un número y apuntar su webhook — con un botón
En vez de ir a la Console de Twilio a comprar el número y configurar a mano
su webhook de voz, la sección **📞 Auto-configurar número Twilio** (misma
pestaña Configuración, justo debajo de las API keys) lo hace por vos:

- **"Comprar número nuevo"**: busca números disponibles en tu país, elegís
  uno y al comprarlo queda **ya apuntado** a `/voz/entrante` de tu servidor
  — sin volver a la Console. Se guarda solo como `TWILIO_FROM`.
- **"Ya tengo un número"**: si ya compraste un número a mano (o lo tenías de
  antes), esta pestaña solo le actualiza el webhook de voz a tu servidor.

> Requiere que ya tengas `PUBLIC_BASE_URL` seteada en el servidor (ver paso
> 4) — sin eso no hay a qué URL apuntar el webhook. Comprar un número tiene
> **costo real** (verificá la tarifa vigente antes de confirmar).

Si preferís hacerlo a mano igual: Console → **Phone Numbers → Buy a
number** (con *Voice*), y en la ficha del número, **Voice Configuration →
"A call comes in" → Webhook**, pegá `https://tu-servidor/voz/entrante`
(método `HTTP POST`) — este es el paso que la mayoría de las guías se
saltea y por el que las llamadas *entrantes* no llegan al Gestor IA aunque
las salientes ya funcionen.

### 4. Poner el servidor accesible desde internet
Twilio necesita alcanzar tu servidor. Levantá el backend de voz y exponelo:

```bash
python -m realtime.server        # http://localhost:8000
ngrok http 8000                  # te da https://XXXX.ngrok-free.app
```

> El servidor **detecta solo** la URL pública (por los headers de ngrok); no
> tenés que configurarla. Si preferís fijarla, seteá `PUBLIC_BASE_URL`.

### 5. Llamar — con un botón
- Abrí **`https://XXXX.ngrok-free.app/llamar`** en el navegador.
- Completá: **teléfono** (formato internacional, ej. `+59809XXXXXXX`), nombre y
  **monto de la deuda**. Tocá **📞 Llamar ahora**.
- El Gestor IA llama, negocia y, al cortar, **registra la gestión** (se ve en el
  dashboard *Gestores & Evolución* como gestor IA).

---

## Voz más natural / rioplatense
Por defecto habla con **Polly Lupe (neural, es-US)** — la voz latina más
natural incluida vía Twilio — y **escucha en `es-UY`** (entiende mejor el
habla rioplatense del deudor). La voz se cambia desde el dashboard →
**⚙️ Configuración → 🗣️ Voz de las llamadas**, o con las variables
`TWILIO_TTS_VOICE` / `TWILIO_TTS_LANG` / `TWILIO_ASR_LANG`. Las voces
*neural* tienen un costo chico por carácter en Twilio (pricing de `<Say>`).

**Importante**: ninguna voz del catálogo de Polly es rioplatense de verdad
(no existen voces es-AR/es-UY en Polly). Para acento rioplatense natural,
configurá la **voz premium ElevenLabs** en la misma pestaña: en
elevenlabs.io → *Voice Library* buscá «Argentine» o «Rioplatense», agregá
la voz a tu cuenta y elegila en el selector. En llamadas se usa el modelo
*flash* de baja latencia (y las frases repetidas se cachean), así la
conversación fluye sin pausas.

## Costos aproximados (verificá tarifas vigentes)
- **Trial**: crédito gratis para las primeras pruebas.
- **Número**: ~USD 1–3 / mes.
- **Minutos a Uruguay**: del orden de centavos de USD por minuto (móvil vs. fijo).
- **Claude (opcional)**: si cargás `ANTHROPIC_API_KEY`, redacta más natural
  (centavos por conversación); sin key, plantillas.

## Alternativa sin Twilio: tu central
Si la empresa ya tiene **Avaya / Asterisk / Genesys / Cisco**, no hace falta
Twilio: el conector `realtime/conector_avaya.py` recibe el RTP que la central
forkea (SIPREC/DMCC). Ver el README, sección *Conector Avaya / SIPREC*.

---

> ⚖️ **Antes de llamar a terceros**: asegurate del consentimiento y respetá el
> módulo de **cumplimiento** (`kobra/cumplimiento.py`): horarios, topes de
> frecuencia y lista de *No Contactar*. Si en la llamada el cliente dice "no me
> llamen más", el Gestor IA **lo registra solo** y no se lo vuelve a contactar.
