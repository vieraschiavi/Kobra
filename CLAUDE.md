# CLAUDE.md — MV Kobra AI

> Contexto persistente para Claude Code. Generado por la skill `automatizador-proyecto`.
> Leelo al iniciar cada sesión.

## Qué es
**MV Kobra AI** es una plataforma de cobranzas inteligentes: combina un modelo de probabilidad de
pago (**ProbPago**) con un **Agente IA Negociador** y un **Copiloto de Negociación en Vivo**
(sentimiento de voz/WhatsApp), dentro de un dashboard gerencial. Es una **demo comercial funcional
sobre datos 100% sintéticos** — el pipeline es real, las métricas de impacto son ilustrativas.

## Stack
- **Lenguaje principal:** Python 3.11.9
- **Dashboard:** Streamlit (`app/app.py`)
- **ML/Datos:** pandas, numpy, scikit-learn, plotly, joblib
- **Servicios:** FastAPI + uvicorn + websockets (`realtime/`, `backend_venta/`, `webapp/`)
- **Frontend/pagos:** Node (`api/` — checkout, licencias, verify-payment)
- **Deploy:** Docker / Vercel / Procfile (streamlit)
- **Reportes:** python-pptx, openpyxl, xlsxwriter

## Comandos (fuente: `run.sh`)
| Acción | Comando |
|--------|---------|
| Instalar deps | `pip3 install -r requirements.txt` |
| Generar datos sintéticos | `python3 data/generate_dataset.py --n 12000 --seed 42` |
| Pipeline (datos+modelo+exports) | `python3 -m kobra.pipeline` |
| Entrenar modelo | `python3 -m kobra.train` |
| **Tests** | `python3 -m pytest -q tests/` |
| **Verificar como CI** (antes de pushear) | `python3 verificar.py` |
| Levantar dashboard | `streamlit run app/app.py` |
| Servidor realtime | `python3 -m realtime.server` |
| Presentación PPTX | `python3 presentation/build_ppt.py` |
| End-to-end | `./run.sh` |

## Estructura
- `kobra/` — núcleo (pipeline, train, analítica, autenticación, auditoría…)
- `app/` — dashboard Streamlit
- `realtime/` — copiloto en vivo, conectores (Avaya), websockets
- `backend_venta/` — licencias, descargas, uso
- `webapp/` — backend + frontend web
- `api/` — endpoints Node (checkout, pagos, licencias)
- `data/` — generadores de datos sintéticos
- `tests/` — suite pytest
- `presentation/`, `docs/`, `packaging/`, `electron/` — soporte

## Flujo de trabajo
1. **Planificá** antes de cambios grandes: usá `/plan` (solo lectura primero).
2. Hacé el cambio acotado.
3. **Testeá:** `python3 -m pytest -q tests/` (o `/test`). Nunca declares algo listo sin tests verdes.
4. **Verificá como CI antes de pushear:** `python3 verificar.py`. CI corre cuatro
   gates y `pytest` es uno solo — las dos últimas fallas de este repo fueron
   `ruff` y un test que se encontró a sí mismo, las dos invisibles corriendo
   solo pytest. `python3 verificar.py --instalar-hook` lo deja automático en
   cada `git push`.
5. **Publicá** con `/ship`: checkpoint (commit) → push → PR draft.
6. Para trabajo pesado, delegá en subagentes (`explorer`, `planificador`, `parallel-worker`,
   `specialist`, `revisor`, `verificador`).

## Convenciones
- Datos **siempre sintéticos** — nunca metas datos reales de clientes ni PII.
- Las cifras de impacto son **ilustrativas**; no las presentes como resultados reales (ver README).
- Respetá el estilo del código existente (español en dominio, nombres de módulos en español).
- Reproducibilidad: seeds fijos (`--seed 42`) en generación de datos.

## Do / Don't
- ✅ Correr tests antes de commitear · ✅ Mantener datos sintéticos · ✅ Seeds fijos.
- ❌ `rm -rf` ni `git push --force` · ❌ Leer/loguear secretos o `.env` · ❌ Meter métricas reales sin validación.

## Contexto / Compact
- Si la sesión se hace larga, usá `/compact` para condensar y seguir enfocado.
- Para explorar el repo a lo ancho, delegá en el subagente `explorer` en vez de leer todo en el hilo principal.
