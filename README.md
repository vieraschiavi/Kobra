# 🐍 Kobra · Plataforma de Cobranzas Inteligente

**Kobra** convierte una cartera de cobranzas en un plan de acción priorizado.
Combina un modelo de **probabilidad de pago (ProbPago)** con un **Agente IA
Negociador** que recomienda la mejor estrategia, descuento, canal y guion, y un
**Copiloto de Negociación en Vivo** que analiza el **sentimiento del cliente**
(voz o WhatsApp) y asesora al gestor en tiempo real — todo dentro de un
dashboard gerencial con KPIs, filtros, gráficos y exportación a Excel/CSV.

> Demo lista para vender a cualquier empresa con cartera vencida (banca,
> financieras, retail, telco, utilities, fintech). Pensada para **Uruguay**,
> con **datos sintéticos y sin nombres de clientes** — sin problemas legales.

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
   ├─►  ProbPago  (kobra/probpago.py)      Gradient Boosting → probabilidad de pago
   │
   ├─►  Agente Negociador (kobra/negociador.py)   estrategia + descuento + canal + guion
   │
   ├─►  Copiloto en Vivo (kobra/copiloto.py)       sentimiento + técnicas + asesoría en tiempo real
   │        ├─ realtime/  (FastAPI + WebSocket)     audio en vivo durante la llamada
   │        └─ voz (kobra/voz.py)                   diarización + emoción acústica de voz
   │
   ├─►  Analítica de gestión (kobra/analitica.py)  por gestor/mes/tramo/segmento + impacto Kobra
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

---

## 📊 El dashboard

Cuatro secciones, todas con **filtros dinámicos** (segmento, producto, tramo
de mora, propensión, departamento, monto y ProbPago mínima):

1. **Visión general** — 6 KPIs, cartera vs. recupero por tramo, propensión,
   recupero por segmento y top departamentos.
2. **Agente Negociador** — estrategias recomendadas, recupero por estrategia y
   un **simulador por deudor** con el guion listo para enviar.
3. **Cartera & Export** — tabla priorizada + descarga a **CSV / Excel**.
4. **Modelo ProbPago** — métricas (AUC, lift), drivers del modelo y
   distribución de la probabilidad de pago.

![Dashboard](assets/dashboard_overview.png)

---

## 🧠 ProbPago (el modelo)

- **Algoritmo:** Gradient Boosting (scikit-learn).
- **Features:** monto, días de mora, score de buró, contactabilidad,
  historial de pagos y promesas, antigüedad, gestiones previas, segmento,
  producto, departamento y canal.
- **Salida:** probabilidad de pago (0–1), decil y segmento de propensión
  (Alta / Media / Baja).
- **Desempeño (demo):** AUC-ROC ≈ 0.87 · Lift del top decil ≈ 1.7x vs. base.

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

- **Análisis de sentimiento** turno a turno (léxico español rioplatense, con
  manejo de negación e intensificadores). Acepta además señales de voz
  (energía, variabilidad de pitch, ritmo) para negociación telefónica.
- **Detección de emociones** del cliente (enojo, frustración, ansiedad,
  dificultad económica, intención de pago, objeción…).
- **Detección de técnicas** del gestor (anclaje, fraccionamiento, alternativas,
  reciprocidad, urgencia, escasez, validación, cierre…).
- **Scoring de calidad** de la gestión (16 criterios ponderados).
- **Asesoría en tiempo real**: sugerencias accionables + la **próxima frase**
  sugerida, ligadas a la ProbPago del deudor.

Funciona **100% offline**. Si hay claves en el entorno se enriquece solo:
`OPENAI_API_KEY` → transcripción de audio (Whisper); `ANTHROPIC_API_KEY` →
evaluación cualitativa (Claude). Es una adaptación generalizada del motor de
evaluación de llamadas/WhatsApp incluido en `referencia_R/` (marca removida,
de evaluación *post-mortem* a **asistencia en vivo**).

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
- **Fusión voz + texto**: el sentimiento acústico se combina con el de texto
  (`copiloto.analizar_sentimiento(texto, voz=…)`), de modo que una **voz tensa
  del cliente adelanta la alerta** aunque las palabras sean neutras.

Probalo con la grabación de demo (dual-channel sintética):

```bash
python data/generate_audio_demo.py      # crea data/ejemplo_llamada.wav
# En el dashboard → pestaña "Copiloto en Vivo" → "Analizar grabación (voz)"
# o por API:  POST /analizar_audio  al servidor realtime
```

En producción se puede reemplazar el estimador heurístico por un modelo SER
entrenado (wav2vec2 / SpeechBrain) manteniendo la misma interfaz, y la
diarización mono por pyannote.audio.

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

## 📇 Analítica por gestor y por mes (`kobra/analitica.py`)

Sobre el historial de gestiones (`data/generate_gestiones.py`) responde:

- **Qué características suceden más** por tramo de mora, segmento, canal o
  producto (emoción dominante del cliente, calidad, conversión, recupero) y una
  **matriz de emociones** por tramo/segmento.
- **Cómo evolucionan mes a mes** (calidad, sentimiento, conversión, recupero).
- **Impacto en la cobranza**: a mayor calidad de gestión, mayor conversión y
  recupero.
- **Si los gestores mejoran con el tiempo** usando Kobra: comparación
  *con vs. sin Kobra* y evolución por gestor (primeros vs. últimos meses).

Todo en la pestaña **Gestores & Evolución** del dashboard, con export a Excel.

## 🔬 Entrenamiento ML (mejora de ProbPago)

`kobra/train.py` eleva ProbPago a una **selección de modelos**: compara
Regresión Logística, Random Forest, Gradient Boosting e HistGradientBoosting
con **validación cruzada (5 folds)**, elige el mejor por ROC-AUC, lo
**calibra** (isotónica) y lo persiste:

```bash
python -m kobra.train
# → outputs/probpago_model.joblib  y  outputs/model_selection.json
```

Se reentrena en CI vía **GitHub Actions** (`.github/workflows/train.yml`,
manual o semanal). El workflow `ci.yml` corre los tests y un smoke test del
pipeline en cada push/PR.

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
│   ├── train.py                    # entrenamiento ML (selección de modelos)
│   └── pipeline.py                 # orquestación end-to-end + exports
├── realtime/                       # copiloto de audio en vivo (FastAPI + WebSocket)
├── app/app.py                      # dashboard Streamlit (6 pestañas)
├── dashboard_estatico/             # dashboard + copiloto zero-install (offline)
├── presentation/build_ppt.py       # generador de presentación gerencial
├── tests/test_kobra.py             # pruebas del pipeline y el copiloto
├── referencia_R/                   # motor R original adaptado (referencia)
├── .github/workflows/              # CI (tests) + entrenamiento ML programado
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
