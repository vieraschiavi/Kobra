# Plantilla — Acuerdo de Tratamiento de Datos Personales (DPA)

> ⚠️ **BORRADOR, no un contrato listo para firmar.** Esto es un punto de
> partida redactado con referencia a la Ley N.º 18.331 (Protección de Datos
> Personales, Uruguay) y su decreto reglamentario. **Hacelo revisar por un
> abogado antes de firmarlo con cualquier cliente** — los corchetes `[...]`
> marcan datos que hay que completar caso por caso, y puede haber cláusulas
> que un cliente puntual (banco, financiera) pida agregar o modificar según
> su propia política interna.

---

**ACUERDO DE TRATAMIENTO DE DATOS PERSONALES**

Entre **[Razón social del cliente]**, en adelante "el Responsable", y
**[Razón social de quien opera Kobra IA]**, en adelante "el Encargado",
se acuerda lo siguiente respecto del tratamiento de datos personales en el
marco del uso del software Kobra IA ("el Servicio"):

## 1. Objeto

El Responsable encomienda al Encargado, y este acepta, el tratamiento de
datos personales de deudores/clientes del Responsable, con la única
finalidad de prestar el Servicio de gestión de cobranzas descripto en el
contrato principal de fecha **[fecha]**.

## 2. Categorías de datos e interesados

- **Interesados**: personas físicas deudoras de obligaciones con el
  Responsable.
- **Categorías de datos**: identificación (nombre, documento), datos de
  contacto (teléfono, email), datos de la obligación (monto, mora, producto),
  y — si el Responsable habilita los canales de voz/WhatsApp — contenido de
  las conversaciones de negociación.
- El Encargado **no trata categorías especiales de datos** (salud, origen
  racial/étnico, opiniones políticas, etc.) en el marco de este Servicio.

## 3. Obligaciones del Encargado

El Encargado se compromete a:

a. Tratar los datos personales **únicamente** conforme a las instrucciones
   documentadas del Responsable y para la finalidad de este acuerdo — nunca
   para fines propios ni de terceros.

b. Implementar medidas de seguridad técnicas y organizativas razonables,
   incluyendo (ver detalle en `WHITEPAPER_SEGURIDAD.md`):
   - Autenticación obligatoria y control de acceso basado en roles.
   - Cifrado de credenciales/secretos en reposo.
   - Registro de auditoría de accesos y operaciones relevantes.
   - Cumplimiento de horarios/frecuencia de contacto configurables.

c. Garantizar que el personal autorizado a tratar los datos esté sujeto a
   un deber de confidencialidad.

d. **Subencargados**: informar al Responsable si se recurre a
   subencargados (por ejemplo, proveedores de IA como Anthropic/OpenAI para
   el análisis de conversaciones, o Twilio/Meta para telefonía/WhatsApp,
   cuando el Responsable habilita esos canales), identificándolos y sus
   respectivas políticas de tratamiento. Lista de subencargados vigente:
   **[completar: Anthropic (Claude) / OpenAI (Whisper) / Twilio / Meta
   WhatsApp Business — según qué canales tenga habilitados el Responsable]**.

e. **Notificación de incidentes**: notificar al Responsable sin demora
   indebida (dentro de las **[plazo, ej. 48-72 horas]**) ante cualquier
   violación de seguridad que afecte datos personales tratados en el marco
   de este acuerdo, con el detalle disponible en ese momento.

f. **Asistencia**: colaborar con el Responsable para atender solicitudes de
   los titulares de datos (acceso, rectificación, supresión) conforme a la
   Ley 18.331, en la medida de lo razonablemente posible dado el diseño del
   Servicio.

g. **Devolución/eliminación al finalizar**: al terminar la relación
   contractual, a elección del Responsable, devolver o eliminar todos los
   datos personales tratados en el marco de este Servicio, salvo obligación
   legal de conservación. Plazo: **[ej. 30 días corridos]**.

## 4. Transferencias internacionales

Cuando el Responsable habilite canales que involucren proveedores de IA
(Anthropic, OpenAI) o telefonía/mensajería (Twilio, Meta), los datos
enviados a esos servicios pueden procesarse en servidores fuera de Uruguay.
El Encargado informará, a pedido del Responsable, qué proveedores están
activos y sus mecanismos de transferencia internacional (cláusulas
contractuales tipo u otro mecanismo válido conforme a la normativa
aplicable). **El Responsable puede optar por el modo "traé tus propias
claves" (BYOK) para contratar esos servicios directamente a su nombre, si
prefiere no delegar esa relación en el Encargado.**

## 5. Auditoría

El Responsable podrá solicitar, con un preaviso razonable de
**[ej. 15 días hábiles]**, evidencia razonable del cumplimiento de este
acuerdo (por ejemplo, acceso al log de auditoría del Servicio referido a
su propia instancia).

## 6. Vigencia

Este acuerdo rige mientras esté vigente el contrato principal de
prestación del Servicio, y sus obligaciones de confidencialidad y
devolución/eliminación de datos sobreviven a su terminación.

---

**Por el Responsable**

Firma: _______________________  Fecha: __________

**Por el Encargado**

Firma: _______________________  Fecha: __________
