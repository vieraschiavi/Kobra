# 🐍 Kobra IA · Plataforma de Cobranzas Inteligentes

**Kobra** convierte una cartera de cobranzas en un plan de acción priorizado.
Combina un modelo de **probabilidad de pago (ProbPago)** con un **Agente IA
Negociador** que recomienda la mejor estrategia, descuento, canal y guion, y un
**Copiloto de Negociación en Vivo** que analiza el **sentimiento del cliente**
(voz o WhatsApp) y asesora al gestor en tiempo real — todo dentro de un
dashboard gerencial con KPIs, filtros, gráficos y exportación a Excel/CSV.

> **Qué es esto (léase primero).** Kobra es una **demo comercial funcional**
> construida sobre **datos 100% sintéticos** (sin nombres de clientes, apta
> para mostrar sin problemas legales). Todo lo que ves funcionar es real:
> el pipeline, el copiloto, la integración telefónica, el dashboard. Pero
> **ninguna métrica de impacto o de modelo mostrada acá es evidencia de
> resultados reales** — son **ilustrativas de la metodología**. La sección
> [Honestidad de los números](#-honestidad-de-los-números-leer-antes-de-vender)
> explica exactamente qué es demostración y qué se valida con datos reales.

**Presentación gerencial:** `presentation/Kobra_Presentacion_Gerencial.pptx`
(generada con `python presentation/build_ppt.py`) · versión **Canva** editable
(reetiquetada, cifras marcadas como ilustrativas):
<https://www.canva.com/d/VJ__8kGcZ2M3Q7D> (exportable a PDF/PPTX).

---

## ⚖️ Honestidad de los números (leer antes de vender)

Esta demo genera sus propios datos, y eso tiene una consecuencia directa sobre
qué se puede afirmar frente a un cliente:

1. **El "impacto de Kobra" (+pp de conversión/recupero) es un supuesto
   programado, no un resultado medido.** El generador de gestiones
   (`data/generate_gestiones.py`) **inyecta por diseño** una mejora progresiva
   en los gestores que "adoptan Kobra" (una curva de aprendizaje codificada).
   La pestaña *Gestores & Evolución* y `outputs/impacto_kobra.json` después
   "recuperan" ese efecto. Es **circular a propósito**: demuestra *cómo se
   mediría* el impacto (grupo con vs. sin herramienta, evolución mensual,
   uplift por cohorte), no *cuánto* mejora Kobra. **Nunca presentar esos
   números como ROI medido.**

2. **El AUC del modelo tampoco prueba desempeño real.** La etiqueta `pago` del
   dataset sintético se genera con una función logística conocida; que un
   modelo la reaprenda con AUC ≈ 0.87 es **trivial y esperable por
   construcción**. De hecho, en la selección de modelos el mejor resultó la
   **Regresión Logística** (ver `outputs/model_selection.json`) — coherente con
   que los datos son, literalmente, logísticos. Con una cartera real, el
   algoritmo ganador y el AUC serán otros. Lo que vale acá es la
   **metodología** (comparación de modelos con validación cruzada +
   calibración), no el número.

3. **El sentimiento y la emoción de voz son heurísticos**, no modelos de deep
   learning entrenados: léxico en español con negación/intensificadores para
   texto, y prosodia (energía, F0, ritmo) para voz. Funcionan bien para la demo
   y para casos claros; en producción se reemplazan por modelos entrenados
   (SER tipo wav2vec2/SpeechBrain, diarización pyannote) **manteniendo las
   mismas interfaces**, que para eso están diseñadas.

4. **Streamlit es front de demo/piloto**, no de SaaS multi-tenant. Aguanta un
   piloto con un equipo; para cientos de gestores concurrentes con aislamiento
   de datos por cliente, la capa de UI se reescribe (el motor — `kobra/` y
   `realtime/` — se conserva).

### 🧪 Cómo se validaría con datos reales

Al implementar con la cartera real de un cliente, la evidencia se construye
así (y solo entonces se pueden afirmar números):

- **Validación temporal (walk-forward):** entrenar con los meses 1…N y evaluar
  en el mes N+1, deslizando la ventana — nunca validación aleatoria que mezcle
  pasado y futuro.
- **Anti-leakage:** cada feature debe estar disponible **al momento de la
  gestión** (nada posterior al contacto: sin pagos futuros, sin promesas aún
  no ocurridas, sin campos que se completan al cierre).
- **Calibración medida, no asumida:** curvas de confiabilidad y Brier score
  sobre datos reales; recalibración periódica.
- **Uplift causal con grupo de control:** asignación aleatoria de gestores o
  subcarteras a "con Kobra" vs. "sin Kobra" durante el piloto; la diferencia
  de tasa de cura / $ recuperado por hora de gestor / promesas cumplidas es el
  impacto real — exactamente el análisis que la pestaña *Gestores & Evolución*
  ya sabe hacer.
- **Monitoreo de drift** y reentrenamiento programado (el workflow
  `train.yml` ya existe).

**Camino comercial honesto:** demo con datos sintéticos → **piloto pago
acotado** sobre una subcartera real → caso testigo con números medidos → ahí sí,
implementación completa con evidencia propia.

---

## 🎯 Qué resuelve

| Problema tradicional | Con Kobra |
|---|---|
| Se gestiona igual a todos los deudores | Se prioriza por **valor esperado de recupero** |
| Descuentos y planes "a ojo" | Decisiones según **probabilidad de pago** |
| No se sabe a quién contactar primero | Ranking operativo automático |
| Guiones de negociación improvisados | **Guion generado** por el agente IA |
| El gestor negocia "a ciegas" | **Copiloto en vivo**: sentimiento + próxima jugada |
| Reporting manual y lento | **Dashboard + export a Excel/CSV** |

---

## 🏗️ Arquitectura (end-to-end)

```
Cartera (CSV)
   │
   ├─►  ProbPago  (kobra/probpago.py)      modelo de probabilidad de pago (ML)
   │
   ├─►  Agente Negociador (kobra/negociador.py)   estrategia + descuento + canal + guion
   │
   ├─►  Copiloto en Vivo (kobra/copiloto.py)       sentimiento + técnicas + asesoría en tiempo real
   │        ├─ realtime/  (FastAPI + WebSocket)     audio en vivo durante la llamada
   │        └─ voz (kobra/voz.py)                   diarización + emoción acústica de voz
   │
   ├─►  Analítica de gestión (kobra/analitica.py)  por gestor/mes/tramo/segmento + medición de impacto
   │
   ├─►  Entrenamiento ML (kobra/train.py)          selección de modelos + calibración (ProbPago)
   │
   ├─►  Pipeline (kobra/pipeline.py)       orquesta todo y exporta
   │        ├─ outputs/kobra_scored.csv / .xlsx
   │        ├─ outputs/kobra_bundle.json
   │        └─ dashboard_estatico/kobra_data.js
   │
   ├─►  Dashboard Streamlit (app/app.py)   KPIs · filtros · gráficos · export
   ├─►  Dashboard estático (dashboard_estatico/index.html)   zero-install, offline
   └─►  Presentación gerencial (presentation/*.pptx)
```

---

## 🚀 Cómo ejecutarlo

### Opción rápida (todo en uno)
```bash
./run.sh            # instala deps, genera datos, corre el modelo y abre el dashboard
```

### Paso a paso
```bash
pip install -r requirements.txt
python data/generate_dataset.py --n 12000 --seed 42   # genera la cartera sintética
python -m kobra.pipeline                              # entrena ProbPago + negociador + exports
streamlit run app/app.py                              # dashboard interactivo
python presentation/build_ppt.py                      # presentación gerencial (PPTX)
```

### Dashboard sin instalar nada
Abrí `dashboard_estatico/index.html` en cualquier navegador (funciona
offline, con librerías locales). Ideal para demos y para compartir por mail.

### 🐳 Despliegue con Docker (piloto/producción)

```bash
docker compose up --build
#  Dashboard:  http://localhost:8501
#  Realtime :  http://localhost:8000   (copiloto de audio en vivo)
```

Una sola imagen sirve ambos servicios (dashboard Streamlit y API realtime). Los
datos/modelo se generan en el primer arranque; los volúmenes persisten datos,
outputs y la **configuración de API keys** entre reinicios.

### 🔑 Configuración de API keys (persistente)

Las keys se cargan de tres formas (prioridad de arriba hacia abajo):

1. **Variables de entorno / `.env`** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) — ideal en producción.
2. **Dashboard → pestaña “Configuración”**: se ingresan una vez y quedan
   **guardadas** (`$KOBRA_CONFIG_DIR/config.json`, por defecto `~/.kobra`), así
   se cargan solas en cada arranque sin reingresarlas.
3. **Sin keys**: Kobra funciona igual (sin transcripción Whisper ni evaluación Claude).

Con `OPENAI_API_KEY` se habilita la transcripción real (Whisper) y con
`ANTHROPIC_API_KEY` la evaluación cualitativa con Claude.

---

## 📊 El dashboard

Siete pestañas, con **filtros dinámicos** (segmento, producto, tramo de mora,
propensión, departamento, monto y ProbPago mínima):

1. **Visión general** — 6 KPIs, cartera vs. recupero por tramo, propensión,
   recupero por segmento y top departamentos.
2. **Agente Negociador** — estrategias recomendadas, recupero por estrategia y
   un **simulador por deudor** con el guion listo para enviar.
3. **Cartera & Export** — tabla priorizada + descarga a **CSV / Excel**.
4. **Modelo ProbPago** — métricas de la demo, drivers y distribución.
5. **Copiloto en Vivo** — análisis de conversaciones y de grabaciones (voz).
6. **Gestores & Evolución** — metodología de medición de impacto (ilustrativa).
7. **Configuración** — API keys persistentes.

---

## 🧠 ProbPago (el modelo)

- **Metodología:** selección de modelos con **validación cruzada (5 folds)** —
  Regresión Logística, Random Forest, Gradient Boosting, HistGradientBoosting —
  elección por ROC-AUC, **calibración isotónica** y persistencia
  (`python -m kobra.train` → `outputs/probpago_model.joblib` +
  `outputs/model_selection.json`).
- **En el dataset sintético de la demo ganó la Regresión Logística**
  (esperable: la etiqueta se genera con una función logística — ver
  [Honestidad de los números](#-honestidad-de-los-números-leer-antes-de-vender)).
  Con datos reales, el ganador y las métricas se determinan de nuevo con
  validación temporal.
- **Features:** monto, días de mora, score de buró, contactabilidad,
  historial de pagos y promesas, antigüedad, gestiones previas, segmento,
  producto, departamento y canal — todas disponibles al momento de la gestión.
- **Salida:** probabilidad de pago (0–1), decil y propensión (Alta/Media/Baja).
- Reentrenamiento programado vía GitHub Actions (`.github/workflows/train.yml`).

## 🤖 Agente IA Negociador

Para cada deudor decide, maximizando el **recupero esperado** y minimizando la
quita:

- **Estrategia** (recordatorio suave, pago total facilitado, plan de cuotas,
  quita agresiva, derivación especializada…).
- **Descuento** y **plan de cuotas** sugeridos.
- **Canal** óptimo (alto valor → contacto humano).
- **Guion** parametrizado listo para enviar (sin nombres reales).
- **Prioridad** operativa por valor esperado (UYU).

## 🎧 Copiloto de Negociación en Vivo

Asiste al gestor **durante** la negociación telefónica o por WhatsApp
(`kobra/copiloto.py`):

- **Análisis de sentimiento** turno a turno (léxico español rioplatense con
  negación e intensificadores — heurístico, reemplazable por un modelo
  entrenado con la misma interfaz).
- **Detección de emociones** del cliente (enojo, frustración, ansiedad,
  dificultad económica, intención de pago, objeción…).
- **Detección de técnicas** del gestor (anclaje, fraccionamiento, alternativas,
  reciprocidad, urgencia, escasez, validación, cierre…).
- **Scoring de calidad** de la gestión (criterios ponderados).
- **Asesoría en tiempo real**: sugerencias accionables + la **próxima frase**
  sugerida, ligadas a la ProbPago del deudor.

Funciona **100% offline**. Si hay claves en el entorno se enriquece solo:
`OPENAI_API_KEY` → transcripción de audio (Whisper); `ANTHROPIC_API_KEY` →
evaluación cualitativa (Claude).

Disponible en tres lugares:
- **Dashboard Streamlit** → pestaña *Copiloto en Vivo* (pegar/subir conversación).
- **Dashboard estático** → sección *Copiloto (offline)* — motor portado a JS,
  corre en el navegador sin backend (`dashboard_estatico/copiloto.js`).
- **Audio en tiempo real** → `realtime/` (ver más abajo).

### 🎙️ Audio en vivo durante la llamada (`realtime/`)

Backend **FastAPI + WebSocket** que asiste al gestor **mientras** habla:

```
Micrófono/llamada → transcripción en vivo → Copiloto → asesoría en pantalla
```

- El navegador transcribe con la **Web Speech API** (español, sin API key) o,
  del lado del servidor, con **Whisper** (`POST /transcribe`) si hay
  `OPENAI_API_KEY`.
- Cada turno viaja por WebSocket; el servidor corre el Copiloto y devuelve en
  milisegundos: sentimiento, emoción, técnicas, calidad, sugerencias y la
  próxima frase.
- Incluye un modo **“Simular llamada”** para demostrar sin micrófono.

```bash
python -m realtime.server     # http://localhost:8000
```

**En producción telefónica** el audio se toma del softphone/PBX (grabación o
media stream del canal), no del micrófono; el resto del flujo es idéntico.

### 🗣️ Diarización + emoción acústica de voz (`kobra/voz.py`)

Analiza la **señal de voz** de la llamada, no solo las palabras:

- **Diarización** (quién habla):
  - *Dual-channel* (lo habitual en grabación de call center): una pata por
    interlocutor → separación **exacta** por canal.
  - *Mono*: segmentación por energía (VAD) + clustering de 2 hablantes (KMeans
    sobre features espectrales). Offline, sin modelos pesados.
- **Emoción acústica (prosodia)**: a partir de energía, tono (F0), variación de
  tono, ritmo del habla y brillo espectral estima *arousal*/*valencia* y una
  etiqueta (enojo, frustración, ansiedad, resignación, neutro, positivo).
  **Heurística fundada en prosodia** — suficiente para demo; en producción se
  reemplaza por un modelo SER entrenado (wav2vec2/SpeechBrain) y la
  diarización mono por pyannote.audio, con la misma interfaz.
- **Fusión voz + texto**: el sentimiento acústico se combina con el de texto
  (`copiloto.analizar_sentimiento(texto, voz=…)`), de modo que una **voz tensa
  del cliente adelanta la alerta** aunque las palabras sean neutras.

Probalo con la grabación de demo (dual-channel sintética):

```bash
python data/generate_audio_demo.py      # crea data/ejemplo_llamada.wav
# En el dashboard → pestaña "Copiloto en Vivo" → "Analizar grabación (voz)"
# o por API:  POST /analizar_audio  al servidor realtime
```

### ☎️ Integración con telefonía (softphone / PBX)

Un **PBX** es la central telefónica de la empresa; un **softphone** es el
teléfono por software del gestor. Kobra **no los reemplaza**: se conecta al
**audio** que ya manejan. Kobra es **agnóstico de la plataforma** — funciona
con Avaya, Genesys, Cisco, 3CX, Asterisk/FreePBX, Twilio, etc. — porque toma el
audio por mecanismos estándar:

| Plataforma | Cómo se obtiene el audio |
|---|---|
| **Avaya** | Grabación dual-channel (Avaya AES/DMCC) o media stream vía SIPREC |
| **Genesys** | AudioHook / SIPREC / grabación por agente |
| **Cisco** | Built-in Bridge / Network-Based Recording (SIPREC) |
| **Asterisk / 3CX** | `MixMonitor` (dual-channel) o forking de RTP |
| **Twilio / nube** | Media Streams (WebSocket de audio en vivo) |
| **Cualquiera** | Archivo de grabación `.wav` dual-channel post-llamada |

Recomendado: **grabación dual-channel** (una pata por interlocutor) → la
diarización es exacta y la emoción por hablante es más precisa. El resto del
pipeline (transcripción → copiloto → asesoría) es idéntico en todos los casos.

> ⚠️ **Micrófono de la PC ≠ telefonía.** El micrófono solo capta el audio de la
> PC (útil para VoIP en la PC o pruebas). Para una llamada por central (Avaya,
> etc.) el audio va por la telefonía: usá la opción **“Central telefónica /
> grabación”**. En la app realtime hay un selector **“Fuente de audio”** que
> separa ambos modos.

### 📝 Transcripción alineada por hablante

`voz.transcribir_llamada()` / `voz.copiloto_desde_audio()` producen la
transcripción **por turno y por hablante**:

- Con **`OPENAI_API_KEY`** → Whisper transcribe el audio real con **marcas de
  tiempo por segmento**, y cada segmento se asigna al hablante diarizado con
  mayor solapamiento temporal.
- Sin key → se **alinea** una transcripción provista (o la del chat) a los
  hablantes diarizados por orden.

Cada turno se fusiona con la **emoción acústica** de ese tramo, de modo que la
tabla muestra `Sent. texto` vs `Sent. voz+texto` — la voz tensa del cliente
empuja la alerta más allá de las palabras. Endpoints:
`POST /copiloto_audio` (subir grabación) y `GET /copiloto_demo`.

### 📡 Streaming en vivo (conectores) — `realtime/connectors.py`

Para asesorar **mientras la llamada ocurre**, el audio de la central entra por
WebSocket y el copiloto responde turno a turno:

| Fuente | Endpoint | Formato |
|---|---|---|
| **Twilio Media Streams** | `WS /twilio` | μ-law 8 kHz; `track` inbound→cliente, outbound→gestor (protocolo real de Twilio) |
| **SIPREC** (Avaya/Genesys/Cisco) | `WS /ws_audio` | el SBC/grabador forkea el RTP a un media server que reenvía **PCM16** |
| **Avaya DMCC/AES** | `WS /ws_audio` | el SDK entrega el audio del canal y se reenvía como PCM16 |

`StreamSession` acumula audio por hablante y, al cerrar cada turno (silencio /
cambio de interlocutor), transcribe (Whisper si hay key), calcula emoción
acústica, fusiona voz+texto y devuelve la asesoría. Probalo sin central real:

```bash
python -m realtime.server            # levanta el servidor
python -m realtime.simular_stream    # stremea la grabación demo a /ws_audio
# o en el navegador: modo "Central telefónica" → "📡 Simular stream en vivo"
```

**Para conectar tu central**: apuntá el `<Stream>` de Twilio a `wss://<host>/twilio`,
o configurá SIPREC/DMCC para reenviar el media a `wss://<host>/ws_audio`. La
asesoría se enruta a la pantalla del gestor (WS `/ws`).

### ☎️ Conector Avaya / SIPREC (`realtime/conector_avaya.py`)

Puente **RTP → Kobra** listo para producción: recibe el audio que la central
forkea por RTP (**G.711 μ-law o A-law** — A-law es el estándar en Uruguay —,
paquetes de 20 ms, una pata por puerto UDP), hace VAD por energía, corta cada
turno al silencio y lo envía al Copiloto, que devuelve la asesoría en vivo y
registra la gestión al colgar.

```bash
python -m realtime.conector_avaya --deudor KB-100773 --gestor G03
#   --puerto-gestor 5004 --puerto-cliente 5006 --silencio 0.6
#   --transcript <archivo del CTI>   (opcional, enriquece sin Whisper)
```

- **Codecs bit-exactos**: decodificadores μ-law/A-law propios en numpy,
  verificados byte a byte contra la referencia G.711 en todo el rango int16
  (sin depender de `audioop`, eliminado en Python 3.13).
- **Auto-detección de codec** por payload type RTP (0 = PCMU, 8 = PCMA).
- **Lado Avaya**: SIPREC en el SBC/Aura apuntando al host del conector, o
  DMCC/AES dirigiendo el RTP de la estación virtual. El `id_deudor` llega por
  el CTI (UUI/header SIP) y se pasa con `--deudor`.

**Probalo sin central física** con el simulador de RTP incluido (emite la
llamada demo como paquetes RTP reales, igual que un SBC):

```bash
python -m realtime.server                                 # terminal 1
python -m realtime.conector_avaya --deudor KB-100773      # terminal 2
python -m realtime.simular_rtp --codec alaw               # terminal 3
```

Verificado end-to-end: los 10 turnos llegan separados por pata, con emoción
de voz detectada (enojo/frustración del cliente), brief pre-llamada, asesoría
turno a turno y gestión registrada al cortar.

### 🔁 Ciclo completo de la negociación (pre → en vivo → post)

1. **Antes de llamar** — `GET /brief/{id_deudor}`: briefing para el screen-pop
   del CTI (Avaya Workspaces, etc.): ProbPago, estrategia, descuento máximo,
   plan, canal, guion y prioridad, calculados por el pipeline. El marcador
   (p. ej. Avaya Proactive Outreach) puede tomar la lista priorizada exportada.
2. **Durante** — el mensaje `start` de `/ws_audio` acepta `id_deudor` y
   `gestor_id`: Kobra carga solo el briefing y ajusta la propuesta turno a
   turno según el sentimiento (voz + texto) del cliente.
3. **Al colgar** — el mensaje `stop` (acepta `resultado` con la tipificación
   real del CRM; si falta, se infiere del clima + intención de pago) **persiste
   la negociación** en `data/kobra_gestiones.csv` vía `kobra/registro.py`:
   calidad, sentimiento, emoción dominante, técnicas, resultado y recupero.
   Esa es la misma base que alimenta la pestaña **Gestores & Evolución**, así
   el dashboard pasa de la demo a **llamadas reales** sin ningún cambio.

Probalo end-to-end sin central: `python -m realtime.simular_stream` (muestra el
brief, la asesoría en vivo y la gestión registrada al final).

## 🤖 Gestor IA · agente autónomo de negociación (`kobra/gestor_ia.py`)

El **gestor virtual** conduce la negociación completa igual que un humano —
por **voz** (voicebot) o por **WhatsApp** (chatbot): saluda, valida identidad,
propone según ProbPago/estrategia, maneja objeciones con **concesiones
escalonadas dentro del tope autorizado**, cierra, **completa los campos ERP** y
registra la gestión. Aparece en *Gestores & Evolución* como gestor `IA…`, así
su desempeño se **mide contra los humanos**.

- **Dependencias externas mínimas por diseño**: el cerebro (diálogo,
  intención, sentimiento) corre **100% local**. **Claude (Anthropic) es la
  única IA externa y es opcional**: si hay `ANTHROPIC_API_KEY` redacta más
  natural; sin key usa plantillas (funciona igual).
- **Voz local, sin nube**: adaptadores para **Piper TTS** (voz neuronal
  es-AR/es-ES, baja latencia) y **faster-whisper STT**; si no están instalados,
  corre en modo texto (mismo diálogo).
- **Campañas concurrentes** (`realtime/voicebot.py`): **hasta 50 llamadas
  simultáneas** (verificado: 50 líneas, pico 50, 0 errores). El canal de voz
  real lo pone la telefonía del cliente (Twilio `<Connect>`, Avaya/SIPREC con
  el conector incluido, Asterisk…); en demo hay un cliente simulado.
- **Chatbot WhatsApp** (`POST /whatsapp/webhook`): para quien no quiere hablar
  por teléfono. El proxy del canal (WhatsApp Cloud API / Twilio WhatsApp del
  cliente) postea `{sesion, id_deudor, mensaje}` y el Gestor IA negocia y
  registra la gestión como canal WhatsApp.

```bash
python -m realtime.voicebot --lineas 50 --llamadas 50   # campaña saliente
# chatbot WhatsApp: POST /whatsapp/webhook  (ver realtime/server.py)
```

> Nota: en la demo, la cohorte del Gestor IA en *Gestores & Evolución* es
> **sintética e ilustrativa** (como el resto). Con la operación real, cada
> conversación del Gestor IA registra su gestión y el dashboard compara IA vs.
> humanos con datos medidos.

## 📇 Analítica por gestor y por mes (`kobra/analitica.py`)

Sobre el historial de gestiones responde:

- **Qué características suceden más** por tramo de mora, segmento, canal o
  producto (emoción dominante del cliente, calidad, conversión, recupero) y una
  **matriz de emociones** por tramo/segmento.
- **Cómo evolucionan mes a mes** (calidad, sentimiento, conversión, recupero).
- **Relación calidad de gestión ↔ conversión/recupero.**
- **Medición de impacto con grupo de control** (*con vs. sin Kobra*) y
  evolución por gestor — la mecánica exacta que se usaría en un piloto real.

> ⚠️ En la demo, el historial de gestiones es **sintético** y el "efecto
> Kobra" está **inyectado por el generador** para ilustrar la metodología.
> Los uplifts que muestra la pestaña *Gestores & Evolución* **no son
> resultados medidos**. Con el registro post-llamada (`kobra/registro.py`)
> la misma pestaña se alimenta de llamadas reales, y ahí los números sí
> significan algo.

## 🔬 Entrenamiento ML (`kobra/train.py`)

Selección de modelos con **validación cruzada (5 folds)**: compara Regresión
Logística, Random Forest, Gradient Boosting e HistGradientBoosting, elige el
mejor por ROC-AUC, lo **calibra** (isotónica) y lo persiste:

```bash
python -m kobra.train
# → outputs/probpago_model.joblib  y  outputs/model_selection.json
```

Se reentrena en CI vía **GitHub Actions** (`.github/workflows/train.yml`,
manual o semanal). El workflow `ci.yml` corre los tests y un smoke test del
pipeline en cada push/PR.

---

## 🛡️ Cumplimiento, explicabilidad y caso de negocio

Tres capas que hacen a Kobra vendible a una entidad regulada (banco, financiera,
cooperativa, estudio de cobranzas) y no solo demostrable.

### ⚖️ Cumplimiento normativo — `kobra/cumplimiento.py`

Gobierna **cuándo y cómo** se puede contactar a cada deudor, para que la
cobranza —humana o del Gestor IA— opere dentro de la ley y las buenas
prácticas. Es la capa que legal/compliance exige antes de dejar que un bot
llame a una cartera:

- **Horario permitido**: bloquea contactos fuera de franja (default 09–20),
  en domingos o **feriados de Uruguay** (fijos + Semana de Turismo/Carnaval
  derivados de Pascua).
- **Tope de frecuencia** por deudor (anti-hostigamiento): máximos por día y por
  7 días.
- **Lista "No Contactar" / opt-out**: si el deudor pide no ser contactado, el
  Gestor IA lo **detecta, lo registra y no lo vuelve a llamar** (`es_pedido_no_contactar`
  → `registrar_no_contactar`). El voicebot **filtra la base** antes de marcar.
- **Política 100 % configurable** por empresa/país (`PoliticaContacto`).

```python
from kobra import cumplimiento as cp
d = cp.puede_contactar("KB-100773", "Llamada")   # Decision(permitido, codigo, motivo)
```

> ⚠️ Herramienta de **apoyo al cumplimiento, no asesoría legal**: cada empresa
> fija su política con su asesoría jurídica; Kobra provee el mecanismo para
> hacerla cumplir y auditar.

### 🔍 Explicabilidad de ProbPago — `kobra/explicabilidad.py`

Para cada deudor responde **por qué** el modelo le asignó esa probabilidad:
qué características la suben y cuáles la bajan, en puntos porcentuales
(atribución por **oclusión**, model-agnostic — funciona con cualquier modelo
del pipeline). El pipeline agrega la columna `motivo_probpago` a la cartera
scoreada y al **brief pre-llamada**, p. ej.:

```
KB-111022 · ProbPago 99% → Score de buró (+3.9 pp) · Promesas cumplidas (+0.5 pp)
KB-106556 · ProbPago  1% → Promesas incumplidas (-1.1 pp) · Días de mora (-1.0 pp)
```

Convierte a ProbPago de "caja negra" en una **decisión automatizada auditable
y defendible** — lo que exigen la Ley 18.331 de Uruguay y marcos equivalentes.

### 💰 Caso de negocio (ROI) — `kobra/roi.py`

Traduce la cartera del comprador en un rango de valor bajo distintos supuestos
de *uplift*, para dimensionar el premio y justificar un piloto pago:

```bash
python -m kobra.roi --cartera 100000000 --tasa-base 0.30 --costo-mensual 100000
#  [conservador] +2 pp → adicional $U 2.000.000 …
#  [       base] +5 pp → adicional $U 5.000.000 · ROI … · payback … m
```

> ⚠️ El *uplift* es un **supuesto que carga el usuario, no un resultado
> medido**. El módulo proyecta *cuánto valdría*, no afirma cuánto sube Kobra —
> coherente con la sección [Honestidad de los números](#-honestidad-de-los-números-leer-antes-de-vender).

### 🧪 Probar con tu propia cartera — `realtime/mi_cartera.py`

Además de la demo sintética, podés correr el flujo completo sobre **tus propios
contactos** (nombre, teléfono, monto): ProbPago → estrategia → cumplimiento →
Gestor IA negociando → resultado. Cargás un CSV simple y Kobra completa el
resto con supuestos por defecto (en producción vienen del ERP):

```bash
# data/mi_cartera_prueba.csv  →  columnas: nombre, telefono, deuda[, dias_mora]
python -m realtime.mi_cartera
python -m realtime.mi_cartera --base otros_contactos.csv --sin-claude
```

La conversación se **simula**. Para **llamar de verdad** hace falta telefonía
(tu cuenta de Twilio con un número, o tu central Avaya/Asterisk) y el
**consentimiento** de la persona; el `<Connect><Stream>` de Twilio apunta a
`wss://<host>/twilio` y el Gestor IA toma la llamada.

> 🔒 **Privacidad.** Un CSV con nombres/teléfonos **reales** es privado:
> `data/mi_cartera_prueba.csv` y `data/*_prueba.csv` están en `.gitignore` y
> **no se suben al repo**. El producto que se vende sigue siendo 100 %
> sintético (Ley 18.331). Para llamar a un tercero necesitás su consentimiento.

---

## 📁 Estructura

```
Kobra/
├── data/generate_dataset.py        # generador de cartera sintética (Uruguay)
├── kobra/
│   ├── probpago.py                 # modelo de probabilidad de pago
│   ├── negociador.py               # agente IA negociador
│   ├── copiloto.py                 # copiloto de negociación en vivo (sentimiento)
│   ├── voz.py                      # diarización + emoción acústica de voz
│   ├── analitica.py                # analítica por gestor / mes / tramo / segmento
│   ├── cumplimiento.py             # cumplimiento normativo (horarios, topes, no-contactar)
│   ├── explicabilidad.py           # reason codes por deudor (por qué esta ProbPago)
│   ├── roi.py                      # estimador de caso de negocio (ROI)
│   ├── cartera_manual.py           # cargar tu propia cartera de prueba
│   ├── registro.py                 # briefing pre-llamada + registro post-llamada
│   ├── config.py                   # API keys persistentes (Configuración)
│   ├── train.py                    # entrenamiento ML (selección de modelos)
│   └── pipeline.py                 # orquestación end-to-end + exports
├── realtime/                       # copiloto de audio en vivo (FastAPI + WebSocket)
├── app/app.py                      # dashboard Streamlit (7 pestañas)
├── dashboard_estatico/             # dashboard + copiloto zero-install (offline)
├── presentation/build_ppt.py       # generador de presentación gerencial
├── tests/test_kobra.py             # pruebas del pipeline y el copiloto
├── referencia_R/                   # motor R original adaptado (referencia)
├── .github/workflows/              # CI (tests) + entrenamiento ML programado
├── Dockerfile · docker-compose.yml # despliegue (dashboard + realtime)
├── outputs/                        # CSV, Excel, JSON y modelo generados
├── assets/                         # capturas del dashboard
├── requirements.txt
└── run.sh
```

---

## ⚖️ Datos y legalidad

El dataset es **100% sintético**, generado localmente y **sin nombres ni
datos personales de clientes reales**. El esquema es genérico: para usarlo con
una cartera real basta con respetar las mismas columnas
(`data/generate_dataset.py` documenta el esquema). Apto para demo comercial en
Uruguay sin exponer información sensible.

> Origen: el copiloto adapta y generaliza criterios de evaluación de gestiones
> de un motor de referencia de **autoría propia** (`referencia_R/`), sin marcas
> ni datos de terceros.
