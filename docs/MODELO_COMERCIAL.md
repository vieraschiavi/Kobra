# MV Kobra AI — Modelo comercial (propuesta, a confirmar)

> **Este documento es una propuesta basada en el informe de auditoría del
> proyecto.** Las cifras son puntos de partida razonables, no precios
> definitivos — ajustalos según tu criterio antes de ofrecerlos a un cliente.

## 1. Qué existe hoy (dos motores, con roles distintos)

| Canal | Qué es | Para quién sirve |
|---|---|---|
| **Web self-serve** (`mvkobranzaia.com`) | Landing + demo + checkout de MercadoPago (Starter US$490+US$29/mes, Pro US$149/mes) | Generar leads, dejar probar la demo, validar interés técnico. **No esperes que una financiera compre así** — el ciclo de venta B2B a bancos/mutuales es largo y requiere confianza, no un botón de "suscribirse". |
| **Venta directa / PoC** | Contacto 1 a 1, demo guiada, piloto pago acotado | **Es el motor de ingresos real en el corto plazo.** Así se cierran los primeros clientes. |

La web no se descarta — sirve como vidriera y para calificar interés — pero el
plan de ingresos 2026 debe apoyarse en la venta directa, no en el self-serve.

## 2. Modelo recomendado para el corto plazo: PoC pago + implementación + retainer

**No SaaS de autoservicio** como motor principal — el modelo que cierra
negocios con financieras/mutuales/estudios de cobranza es:

1. **Piloto pagado (PoC)** — alcance acotado (una cartera chica, un canal),
   4-8 semanas, con **descuento fuerte** si hace falta para cerrar el primero.
2. **Implementación** — pago único al confirmar el piloto: conectar su
   cartera real, su ERP (ya construido: `kobra/integracion.py`), ajustar
   cumplimiento (horarios, feriados UY) a su política.
3. **Retainer mensual** — soporte, monitoreo, reentrenamiento periódico del
   modelo (`.github/workflows/train.yml` ya corre esto semanalmente).

### Cifras de referencia (del informe — confirmar antes de cotizar)

| Concepto | Rango sugerido |
|---|---|
| Setup/implementación (pago único) | USD 3.000 – 8.000 por cliente |
| Retainer mensual | USD 500 – 1.500 por cliente |

### Proyección de facturación (realista, no aspiracional)

| Escenario | Facturación mensual |
|---|---|
| Hoy (0 clientes) | USD 0 |
| 1er piloto cerrado (6-12 meses de venta activa) | USD 500 – 1.500/mes |
| 3 clientes estables (techo como developer solo) | USD 1.500 – 4.500/mes de retainer + picos de USD 3.000-8.000 por implementación nueva |

> Con más de 3-4 clientes concurrentes, el soporte empieza a consumir el
> tiempo de venta — a esa escala, la conversación pasa a ser "¿contrato
> alguien?", no "¿bajo el precio?".

## 3. Cómo se relaciona con los planes de la web

Los planes Starter/Pro del checkout **no desaparecen** — son la puerta de
entrada de autoservicio para:
- Técnicos/estudios chicos que quieren arrancar ya, sin proceso de compra largo.
- Referencia de precio pública (ancla comercial) al conversar con cuentas más
  grandes.

Para **Enterprise** (bancos, financieras grandes) el botón ya dice "Hablar con
ventas" — ahí es donde entra el modelo de PoC + implementación + retainer de
este documento, no el checkout automático.

## 4. Próximo paso concreto: cerrar 1 piloto real

Esto **no se resuelve escribiendo código** — es una acción comercial tuya.
Ideas concretas para destrabarlo:

- Ofrecer el primer piloto con **descuento fuerte** (o gratis) a cambio de
  poder usarlo como caso de referencia medido (ver sección de honestidad de
  números del README — ahí es donde este piloto se vuelve oro: por fin hay
  un uplift *medido*, no simulado).
- Alcance acotado: una sola cartera chica, un solo canal (ej. WhatsApp),
  4-8 semanas — baja fricción para que el cliente diga que sí.
- Usar `kobra/roi.py` (`python -m kobra.roi --cartera ... --tasa-base ...
  --costo-mensual ...`) para armar el caso de negocio a medida de ESE
  prospecto específico.

## 5. Registro de marca — decisión revertida: rebrand a "MV Kobra AI"

La nota anterior de este documento marcaba un riesgo ya conocido: posible
colisión con **"Red Kobra"** (kobra.red, activa en México/Colombia/Perú,
mismo rubro), decidiendo entonces mantener el nombre "Kobra" sin acción. Esa
decisión quedó revertida al confirmarse una **segunda colisión independiente**:
trykobra.com, un competidor de cobranza con IA activo en Chile, con
posicionamiento y pitch casi calcados (agente conversacional que llama,
negocia por WhatsApp/email, mismo rubro). Dos colisiones no relacionadas con
el mismo nombre genérico en el mismo mercado regional son demasiado riesgo de
confusión de marca para sostener "Kobra" a secas.

**Decisión tomada:** renombrar el producto a **"MV Kobra AI"** en todo texto
de cara al cliente (landing, dashboard, docs, instalador, entregables
descargables). El paquete Python interno (`kobra/`, imports, nombres de
variables/columnas) **no se renombra** — es infraestructura de código sin
visibilidad para el cliente, y tocarlo es un refactor grande sin beneficio de
marca. Si en algún momento se avanza con el registro formal de marca,
verificar la disponibilidad de "MV Kobra AI" con un agente de marcas antes de
gastar en el trámite (sigue sin ser algo que se resuelva por código).

## 6. Voz premium (ElevenLabs) — cómo cobrarla sin subsidiar el costo

A raíz de comparar con un competidor ("Mozart") que anuncia un motor de voz
propio con clonación y múltiples idiomas/acentos, se agregó **ElevenLabs**
como motor de voz opcional (`kobra/voz_tts.py`), alternativo al Twilio/Polly
que ya viene incluido sin costo extra. A diferencia de Polly, **ElevenLabs
cobra por carácter** — real, variable, y crece con el uso del cliente.

Decisiones de precio ya tomadas en el código, para que este costo no se
termine subsidiando:

- La feature `"voz_premium"` **no viene en ningún plan por default**
  (`backend_venta/licencias.py::PLANES`) — se habilita explícitamente por
  cliente cuando se emite su licencia, una vez que se decidió cómo cobrarla.
- Cada uso queda medido en `backend_venta/uso.py` (caracteres + costo
  estimado), igual que el uso de Claude — se puede facturar como excedente
  o incluir en un plan superior con el margen ya calculado.
- `kobra.voz_tts.COSTO_POR_1000_CHARS_USD` es una **referencia de mercado**
  (~US$0.17–0.20 cada 1.000 caracteres según el plan de ElevenLabs, julio
  2026) — no es el costo real de tu cuenta. Antes de ofrecerla a un cliente:
  confirmar el costo real contra tu plan de ElevenLabs contratado, y fijar
  el precio del addon (o del plan que la incluya) con margen sobre ese
  costo real, no sobre la referencia.
- Sugerencia de piso: cobrarla como addon mensual con un tope de caracteres
  incluido (igual que el cupo de gestiones), no "ilimitada" a precio fijo —
  así un cliente que la use mucho no se come el margen del plan.
