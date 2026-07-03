# 📞 Guía: hacer una llamada REAL con el Gestor IA (Twilio)

El modo **"Probar mi cartera"** del dashboard *simula* la conversación. Para que
el Gestor IA **hable de verdad** por teléfono, Kobra ya trae el flujo completo:
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

### 2. Conseguir un número
- Console → **Phone Numbers → Buy a number** (con *Voice*). En trial se paga con
  el crédito.

### 3. Cargar las credenciales en Kobra (sin código)
- En el **dashboard → pestaña ⚙️ Configuración**, ingresá:
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` (tu número Twilio).
  Quedan guardadas.

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

## Voz más natural (opcional)
Por defecto usa la voz estándar de Twilio en `es-MX`. Para una voz neuronal
(Amazon Polly), seteá la variable `TWILIO_TTS_VOICE`, por ejemplo
`Polly.Mia-Neural` (revisá que tu cuenta la tenga habilitada). También podés
ajustar `TWILIO_TTS_LANG` / `TWILIO_ASR_LANG`.

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
