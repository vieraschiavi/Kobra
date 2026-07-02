# 🐍 Kobra · Manual de Puesta en Marcha (1 página)

Guía rápida para dejar Kobra operativo con un cliente. Tiempo estimado: **~30 min**.

---

## 1. Requisitos
- **Docker** y **Docker Compose** instalados en el servidor (Linux/Windows/Mac).
- (Opcional) `OPENAI_API_KEY` (transcripción Whisper) y `ANTHROPIC_API_KEY` (Claude).
  *Kobra funciona sin ellas; se pueden cargar después desde la app.*

## 2. Levantar la plataforma (1 comando)
```bash
docker compose up --build -d
```
- **Dashboard gerencial:** http://SERVIDOR:8501
- **Servicio de audio en vivo (copiloto):** http://SERVIDOR:8000

En el primer arranque genera datos y modelo automáticamente. Los volúmenes
guardan datos, resultados y configuración entre reinicios.

## 3. Configurar las API keys (una sola vez)
Dashboard → pestaña **⚙️ Configuración** → pegar las keys → **Guardar**.
Quedan persistidas y se cargan solas en cada arranque. *(Alternativa: variables
de entorno `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` en `docker-compose.yml`.)*

## 4. Cargar la cartera real
Reemplazar el dataset sintético por el del cliente respetando el mismo esquema
(ver columnas en `data/generate_dataset.py`):
```bash
cp cartera_cliente.csv data/kobra_cartera.csv
docker compose run --rm dashboard python -m kobra.pipeline   # reentrena y recalcula
```
Para reentrenar/comparar modelos ML: `python -m kobra.train`.

## 5. Conectar la telefonía (opcional, para copiloto en vivo)
El audio va por la central, **no** por el micrófono de la PC. Según la plataforma:
- **Twilio:** apuntar el `<Stream>` a `wss://SERVIDOR:8000/twilio`.
- **Avaya / Genesys / Cisco (SIPREC o DMCC/AES):** reenviar el media (PCM16) a
  `wss://SERVIDOR:8000/ws_audio`.
- **Sin integración:** subir la grabación `.wav` (dual-channel) en el dashboard
  → pestaña *Copiloto en Vivo* → *Analizar grabación*.

Prueba sin central real: `docker compose exec realtime python -m realtime.simular_stream`.

**Ciclo completo con el CTI:**
- *Antes de llamar:* el screen-pop consulta `GET /brief/{id_deudor}` → muestra al
  gestor ProbPago, estrategia, descuento máximo y guion inicial.
- *Durante:* el conector abre `/ws_audio` con `{"tipo":"start","id_deudor":…,"gestor_id":…}`
  y Kobra ajusta la propuesta turno a turno.
- *Al colgar:* envía `{"tipo":"stop","resultado":"<tipificación del CRM>"}` y la
  negociación queda **registrada automáticamente** en la base de gestiones →
  aparece en la pestaña *Gestores & Evolución* del dashboard.

## 6. Uso diario
| Rol | Qué usa |
|---|---|
| **Gerencia** | Dashboard: KPIs, cartera priorizada, *Gestores & Evolución*, export a Excel/CSV |
| **Supervisor** | *Gestores & Evolución*: calidad, conversión, impacto de Kobra, ranking |
| **Gestor** | *Copiloto en Vivo*: sentimiento del cliente + próxima frase sugerida; guion por deudor |

## 7. Operación y soporte
- **Actualizar:** `git pull && docker compose up --build -d`
- **Logs:** `docker compose logs -f dashboard` / `... realtime`
- **Backup:** volúmenes `kobra-config`, `kobra-data`, `kobra-outputs`
- **Reentrenamiento:** manual (`kobra.train`) o automático por CI (semanal)
- **Datos:** dataset sintético por defecto, **sin datos personales**; la cartera
  real queda solo en el servidor del cliente.

---
**Presentación gerencial:** `presentation/Kobra_Presentacion_Gerencial.pptx` ·
Canva: <https://www.canva.com/d/MUuxAHhku6oIR0x>
