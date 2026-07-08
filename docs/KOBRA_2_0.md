# Kobra 2.0 — estado de ejecución del brief maestro

> Mapea cada bloque del "PROMPT MAESTRO KOBRA AI 2.0" a su estado real en
> este repositorio: construido, diseñado-diferido, o acción comercial que no
> se resuelve con código. Actualizar al cerrar cada hito.

## Resumen: un motor, tres módulos

| Módulo | Estado | Dónde |
|---|---|---|
| **Origination Score** (nuevo) | ✅ Construido (demo sintética) | `kobra/originacion.py` + `POST /api/originacion/score` |
| **Collections Copilot** (existente) | ✅ En producción de demo | ProbPago + Negociador + campaña + NBA (`GET /api/nba/{id}`) |
| **Scoring API B2B2B** (canal) | 🕓 Diseñado, activación diferida | Mismos endpoints; gate = cliente ancla + caso de estudio (Bloque 12) |

## Bloque por bloque

- **B0 · Alcance** — ✅ respetado: un solo motor (mismo stack GB/walk-forward
  que ProbPago), tres empaquetados. El canal API no se vende hasta cumplir
  el gate del B12.
- **B1 · Posicionamiento** — mensaje central y comparativa vs. Salesforce/
  Kolleno/Topaz son material comercial (no código). La regla "precio siempre
  debajo de US$325/usuario" ya se cumple con el pricing actual de la web.
- **B2 · Ciclo de vida** — Etapa 1 (originación) ✅; Etapa 3 (cobranza) ✅;
  Etapa 2 (early warning sobre créditos vigentes) y Etapa 4 (feedback loop
  de reentrenamiento automático) quedan para la fase con datos reales del
  piloto — con datos sintéticos serían teatro.
- **B3 · Motor de originación** — ✅ `kobra/originacion.py`: two-stage GB
  (misma familia que ProbPago), walk-forward temporal (75% pasado / 25%
  futuro), anti-SMOTE (ponderación de muestras), decisión Aprobar/Derivar/
  Rechazar por umbrales configurables, monto/plazo sugeridos, top-3 razones
  en lenguaje simple (atribución por oclusión — mismo rol de producto que
  SHAP, sin la dependencia; si un cliente exige SHAP literal se agrega en su
  implementación), y **nivel de confianza por completitud de datos**: con
  datos insuficientes NUNCA auto-decide — deriva a analista humano.
  Métricas demo (sintéticas, honestas): AUC walk-forward ~0.84, KS ~0.57,
  +0.21 AUC sobre la "regla del oficial" de benchmark.
- **B4 · NBA de cobranza** — ✅ expuesto como contrato API
  (`GET /api/nba/{id_deudor}`: canal, estrategia, descuento, guion, motivo).
  Pendiente para fase piloto: usar el score de originación como feature de
  cobranza (requiere historial real que conecte ambas etapas).
- **B5 · Canal API B2B2B** — 🕓 los endpoints ya existen y sirven al cliente
  directo; venderlos a partners queda **bloqueado hasta el gate del B12**.
  Mitigaciones contractuales (caja negra, verticales no competitivas,
  cuentas protegidas, won't-build) son cláusulas de contrato — redactarlas
  con abogado antes del primer partner.
- **B6 · Explicabilidad y compliance** — razones por decisión ✅ en los dos
  motores; guardrails de cobranza ✅ (`kobra/cumplimiento.py`); auditoría ✅
  (`kobra/auditoria.py`, cadena de hashes). Mapa regulatorio por país =
  tarea legal previa a vender fuera de Uruguay (no código).
- **B7 · Datos e integraciones** — ✅ ya cubierto: CSV/Excel manual, BD
  directa (PR #29), API entrante (`POST /api/integracion/cartera`, PR #30),
  y ahora `/api/originacion/*` + `/api/nba/*`. Panel web-first ✅ (webapp
  React, PR #30).
- **B8 · Panel/UX** — pantallas (2) cartera priorizada y (3) KPIs ✅ en la
  webapp; (1) cola de decisiones de originación = **siguiente iteración**.
- **B9 · Estándares ML** — walk-forward ✅, anti-leakage ✅ (solo features
  disponibles al originar), anti-SMOTE ✅, benchmark vs. regla actual ✅,
  glosario en lenguaje simple ✅ (docstrings + etiquetas de razones).
- **B10 · Pricing** — decisión comercial. Los tiers del brief (Starter
  149–249 / Pro 600–1.100 / Enterprise 60–120 por usuario) difieren del
  pricing publicado hoy en la landing (Starter US$490 + 29/mes · Pro
  US$149/mes) — **la landing no se toca hasta que el dueño confirme** cuál
  rige; cambiar precio público es decisión de negocio, no un commit.
- **B11 · Riesgo de marca** — ✅ mitigado en esta misma sesión: rebrand a
  "MV Kobra AI" por las colisiones Red Kobra + trykobra. El registro formal
  DNPI/INPI/IMPI sigue siendo trámite del dueño
  (ver `docs/GUIA_REGISTRO_LEGAL_URUGUAY.md`).
- **B12 · Cliente ancla** — acción comercial del dueño. El producto ya tiene
  todo lo que el piloto necesita medir (AUC vs. regla actual, recupero con
  NBA, tiempo ahorrado).
- **B13 · GTM/contenido** — acción comercial (LinkedIn, cadencia, pauta).
- **B14 · Exclusiones** — respetadas: no se construyó nada fuera de este
  alcance.
- **B15 · Roadmap 90 días** — semanas 3–6 ("construir originación sobre el
  motor existente, con datos sintéticos si no hay piloto") = ✅ hecho.
