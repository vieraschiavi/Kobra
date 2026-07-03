# 📞 Guía: hacer una llamada REAL con el Gestor IA (Twilio)

El modo **"Probar mi cartera"** del dashboard *simula* la conversación. Para que
el Gestor IA **hable de verdad** por teléfono necesitás dos cosas que no
dependen del código de Kobra:

1. **Telefonía** — una cuenta de **Twilio** con un número (o tu central
   Avaya/Asterisk).
2. **Consentimiento** de la persona a la que vas a llamar. Para un tercero es
   requisito legal; para tu propio celular, obvio que sí. Empezá probando con
   **tu propio número**.

> Kobra ya trae el endpoint listo: `WS /twilio` en `realtime/server.py` recibe
> el audio de Twilio (μ-law 8 kHz) y lo pasa al Gestor IA / Copiloto.

---

## Paso a paso (primera llamada a tu propio celular)

### 1. Crear cuenta Twilio (gratis para probar)
- Registrate en <https://www.twilio.com/try-twilio>. La cuenta **trial** da
  crédito de prueba y permite llamar **solo a números verificados** (verificá
  tu propio celular en *Verified Caller IDs*).
- Anotá tu **Account SID** y **Auth Token** (Console → Account Info).

### 2. Conseguir un número
- Console → **Phone Numbers → Buy a number** (con capacidad *Voice*). En trial
  se paga con el crédito de prueba.

### 3. Publicar el servidor de Kobra en internet
Twilio necesita alcanzar tu servidor. En tu máquina:

```bash
python -m realtime.server          # levanta http://localhost:8000
```

Y exponelo con un túnel (o desplegalo en un server con dominio):

```bash
# opción simple para probar: ngrok
ngrok http 8000                    # te da una URL https://XXXX.ngrok-free.app
```

Tu WebSocket de audio queda en: `wss://XXXX.ngrok-free.app/twilio`

### 4. Decirle a Twilio que envíe el audio a Kobra
La llamada usa este TwiML (XML de Twilio). Para una **llamada saliente** creá la
llamada con la API y este TwiML:

```xml
<Response>
  <Connect>
    <Stream url="wss://XXXX.ngrok-free.app/twilio" />
  </Connect>
</Response>
```

Ejemplo de disparo saliente (reemplazá las X y los números):

```bash
curl -X POST "https://api.twilio.com/2010-04-01/Accounts/<ACCOUNT_SID>/Calls.json" \
  --data-urlencode "To=+59809XXXXXXX" \
  --data-urlencode "From=<TU_NUMERO_TWILIO>" \
  --data-urlencode "Twiml=<Response><Connect><Stream url=\"wss://XXXX.ngrok-free.app/twilio\"/></Connect></Response>" \
  -u <ACCOUNT_SID>:<AUTH_TOKEN>
```

Para **recibir** llamadas: en la config del número (Voice → *A call comes in*),
apuntá a una URL que devuelva ese mismo TwiML.

### 5. Voz natural (TTS/STT)
- Sin componentes de voz, el Gestor IA corre en **modo texto** (el stream llega
  igual). Para voz neuronal local y baja latencia, instalá los adaptadores
  opcionales **Piper TTS** y **faster-whisper STT** (ver `realtime/voicebot.py`).
- Alternativa nube: Twilio `<Say>`/`<Gather>` o Media Streams bidireccional.

---

## Costos aproximados (verificá tarifas vigentes)
- **Trial**: crédito gratis para las primeras pruebas.
- **Número**: ~USD 1–3 / mes.
- **Minutos salientes a Uruguay**: depende del destino (móvil vs. fijo); del
  orden de centavos de USD por minuto. Confirmá en la calculadora de Twilio.
- **Claude (opcional)**: centavos por conversación si activás `ANTHROPIC_API_KEY`.

## Alternativa sin Twilio: tu central
Si la empresa ya tiene **Avaya / Asterisk / Genesys / Cisco**, no hace falta
Twilio: el conector `realtime/conector_avaya.py` recibe el RTP que la central
forkea (SIPREC/DMCC) y lo pasa a Kobra. Ver el README, sección *Conector Avaya /
SIPREC*.

---

> ⚖️ **Antes de llamar a terceros**: asegurate del consentimiento y de respetar
> el módulo de **cumplimiento** (`kobra/cumplimiento.py`): horarios permitidos,
> topes de frecuencia y lista de *No Contactar*. Kobra los hace cumplir, pero la
> política la definís vos con tu asesoría legal.
