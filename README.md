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
│   ├── train.py                    # entrenamiento ML (selección de modelos)
│   └── pipeline.py                 # orquestación end-to-end + exports
├── app/app.py                      # dashboard Streamlit (incluye Copiloto en Vivo)
├── dashboard_estatico/index.html   # dashboard zero-install (offline)
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
