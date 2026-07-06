# Plantilla — Acuerdo de Nivel de Servicio (SLA)

> ⚠️ **BORRADOR con placeholders, no un compromiso ya asumido.** Todos los
> números entre `[corchetes]` son ejemplos de referencia de mercado para
> software B2B chico/mediano — **no son promesas que este documento haga en
> tu nombre**. Completalos solo con niveles que realmente puedas sostener
> (soporte, infraestructura, tiempo disponible) antes de ofrecérselo a un
> cliente. Si el dashboard corre en la infraestructura del propio cliente
> (caso más común hoy, ver `WHITEPAPER_SEGURIDAD.md` sección 9), el uptime
> de "el sistema" depende de esa infraestructura, no de vos — aclaralo así
> en el contrato para no comprometerte a algo fuera de tu control.

---

## 1. Alcance

Este acuerdo aplica a: **[Nombre del cliente]**, para el uso de Kobra IA en
la modalidad **[self-serve / PoC+implementación / Edición Venta con
backend de licencias]**.

## 2. Disponibilidad

- **Si el dashboard corre en infraestructura del cliente** (instalación
  local/servidor propio): no aplica un compromiso de uptime de nuestra
  parte — el Servicio depende de la disponibilidad de esa infraestructura,
  que es responsabilidad del cliente.
- **Si se usa el backend de licencias/gateway** (`backend_venta/`) hosteado
  por nosotros: uptime objetivo mensual de **[ej. 99.0% / 99.5%]**,
  medido excluyendo ventanas de mantenimiento programado (ver punto 4).
- **Landing/demo pública** (`kobra-ia.vercel.app`): mejor esfuerzo, sin
  compromiso de SLA — es material de marketing, no un componente
  operativo del Servicio contratado.

## 3. Soporte

| Severidad | Descripción | Tiempo de primera respuesta | Canal |
|---|---|---|---|
| **Crítica** | El sistema no procesa gestiones / caída total | `[ej. 4 horas hábiles]` | `[email/WhatsApp/teléfono]` |
| **Alta** | Una función clave no funciona, hay alternativa | `[ej. 1 día hábil]` | `[canal]` |
| **Media** | Bug menor, no bloquea la operación | `[ej. 3 días hábiles]` | `[canal]` |
| **Baja** | Consulta, mejora sugerida | `[ej. 5 días hábiles]` | `[canal]` |

Horario de soporte: **[ej. lunes a viernes, 9 a 18 hora Uruguay]**.

## 4. Mantenimiento programado

Se notificará con **[ej. 48 horas]** de anticipación cualquier ventana de
mantenimiento que pueda afectar la disponibilidad del backend de
licencias/gateway (si aplica). Se intentará programar fuera del horario
pico de operación del cliente.

## 5. Actualizaciones y reentrenamiento del modelo

- El modelo ProbPago puede reentrenarse periódicamente (`kobra/train.py`,
  ya automatizado semanalmente en CI para el dataset de referencia). Para
  una cartera real del cliente, la cadencia de reentrenamiento se acuerda
  por separado — no hay un compromiso automático de reentrenamiento sobre
  datos reales de producción salvo que se contrate ese servicio.
- Cambios que afecten la compatibilidad de integraciones (formato de la
  sábana de exportación, endpoints del gateway) se comunicarán con
  **[ej. 30 días]** de anticipación.

## 6. Backup y continuidad

- **Si los datos viven en infraestructura del cliente**: el backup es
  responsabilidad del cliente (o se puede contratar como servicio
  adicional — a definir).
- **Si se usa el backend de licencias/gateway hosteado**: se realizan
  backups de la base de uso/licencias con frecuencia **[ej. diaria]** y
  retención de **[ej. 30 días]**. Esto no reemplaza el backup de la cartera
  de deudores del cliente, que no pasa por este backend salvo que se
  configure explícitamente esa integración.

## 7. Créditos por incumplimiento (opcional)

**[Definir solo si vas a ofrecerlo — ej.: por cada punto porcentual por**
**debajo del uptime objetivo mensual, un crédito de X% sobre la facturación**
**de ese mes, hasta un tope de Y%.]**

## 8. Exclusiones

No se computan como incumplimiento de este SLA: causas de fuerza mayor,
fallas de proveedores de terceros fuera de nuestro control razonable
(Anthropic, OpenAI, Twilio, Meta, MercadoPago, el proveedor de hosting
elegido por el cliente), ni mantenimiento programado notificado según el
punto 4.

---

**Por el proveedor (Kobra IA)**

Firma: _______________________  Fecha: __________

**Por el cliente**

Firma: _______________________  Fecha: __________
