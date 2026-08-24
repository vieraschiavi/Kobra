# Activar las llamadas y el WhatsApp — guía para el cliente

> Esta guía es para **vos, que usás MV Kobra AI en tu empresa**. Es lo que hay
> que hacer una sola vez para que el Gestor IA llame por teléfono de verdad y
> escriba por WhatsApp.
>
> Todo el resto del programa —cartera, ProbPago, copiloto, informes— funciona
> sin nada de esto. Esta configuración habilita solo los canales de voz y
> WhatsApp.

---

## Lo primero: la cuenta de teléfono es tuya

MV Kobra AI **no revende minutos**. Vos abrís tu propia cuenta en Twilio (el
proveedor de telefonía), y Twilio te factura a vos directamente lo que consumís.

Eso significa tres cosas concretas:

- **Nadie más ve tus llamadas ni tus grabaciones.** La cuenta es tuya.
- **Podés cambiar de proveedor o cortar cuando quieras.** No dependés de que
  alguien te habilite nada.
- **Tus credenciales no salen de tu empresa.** Se cargan en la pantalla
  **Configuración** de tu propio programa y quedan guardadas en tu máquina.

> ### ⚠️ Nunca mandes el Auth Token por mail ni por WhatsApp
>
> Ni a nosotros, ni a tu consultor, ni a nadie. El Auth Token de Twilio permite
> **hacer llamadas, comprar números y escuchar las grabaciones** de tu cuenta —
> y lo que se gaste lo pagás vos.
>
> Si alguien te lo pide por mensaje, ese pedido está mal, venga de donde venga.
> Se carga en tu programa, en tu computadora, y ahí se queda.

---

## Paso 1 · Crear la cuenta en Twilio

Entrá a <https://www.twilio.com/try-twilio> y registrate.

**Salí del modo de prueba antes de usarlo con clientes reales.** La cuenta
arranca en *trial*, y el trial:

- reproduce **un mensaje grabado de Twilio antes de cada llamada** — arruina
  cualquier llamada a un deudor real;
- solo permite llamar a números que verificaste a mano.

Para salir del trial hay que cargar saldo (*Upgrade*). Es el mismo panel, botón
**Upgrade**.

---

## Paso 2 · Conseguir un número con capacidad de **voz**

En el panel: **Phone Numbers → Buy a number**, con la casilla **Voice** marcada.

> ### Este es el paso que más se traba, y no es técnico
>
> La disponibilidad de números y los requisitos cambian **según el país**. En
> Uruguay y en varios países de la región, para un número local te piden
> **documentación de la empresa** (constancia de domicilio, datos del titular)
> y la aprobación puede demorar días.
>
> Si necesitás salir a operar ya, hay dos caminos mientras tanto:
>
> - un número de otro país habilitado para llamar al tuyo (el deudor ve un
>   número extranjero — sirve para probar, no para producción);
> - empezar solo con WhatsApp, que no necesita número telefónico local.
>
> Averiguá los requisitos **antes** de prometer una fecha de salida.

---

## Paso 3 · Apuntar el número a tu programa

Twilio necesita saber a qué dirección avisarle cuando entra una llamada.

En el panel, entrá al número comprado y buscá:

**Voice Configuration → "A call comes in" → Webhook**

Ahí va la dirección de tu servicio de voz, terminada en `/voz/entrante`, con el
método **HTTP POST**.

Si no sabés cuál es esa dirección, está en la pantalla **Configuración** de tu
programa: es la que figura como *URL pública del servicio de voz*. Si esa
pantalla dice que falta configurarla, ese es el paso previo — sin dirección
pública, Twilio no tiene adónde avisar y las llamadas entrantes no llegan nunca.

> **Este es el paso que casi todas las guías se saltean**, y es la razón número
> uno por la que "las llamadas salientes funcionan pero las entrantes no".

---

## Paso 4 · Cargar las credenciales en tu programa

En el panel de Twilio, en la portada, están el **Account SID** y el **Auth
Token**.

Copialos y pegalos en **tu programa → pestaña ⚙️ Configuración**. Quedan
guardados en tu máquina, cifrados, y no viajan a ningún lado.

Con eso el botón de llamar ya funciona.

---

## Paso 5 (opcional) · WhatsApp

WhatsApp tiene una regla propia de Meta que **no se puede saltear**: para que
una empresa **inicie** una conversación (que es justo lo que hace una gestión de
cobranza), hay que usar una **plantilla de mensaje aprobada** por Meta.

Entonces necesitás:

1. Una cuenta de **WhatsApp Business** vinculada a Twilio.
2. Al menos **una plantilla aprobada**. La aprobación la da Meta y demora.
3. Cargar en Configuración el identificador de esa plantilla.

Sin plantilla aprobada, el programa **no manda nada y te dice por qué** — no es
un error del sistema, es el requisito de Meta.

Responder a un mensaje que inició el deudor no necesita plantilla. La plantilla
es solo para arrancar la conversación vos.

---

## Qué cuesta y quién lo paga

Todo esto lo facturás vos directamente con Twilio, con tu tarjeta:

| Concepto | Orden de magnitud |
|---|---|
| Número telefónico | unos pocos dólares por mes |
| Minutos de llamada | centavos de dólar por minuto, según el destino |
| Voz *neural* (más natural) | un costo chico por caracter leído |
| Mensajes de WhatsApp | por conversación, según el país |

Los valores cambian y dependen del país: **confirmalos en el tarifario de
Twilio antes de estimar un presupuesto.** No los tomes de esta tabla, que es
solo para que sepas qué conceptos se cobran.

---

## Preguntas que aparecen siempre

**¿Puedo probar sin comprar un número?**
Sí, con el trial: verificás tu propio celular y el Gestor IA te llama a vos.
Escuchás el mensaje de Twilio antes, pero alcanza para ver cómo negocia.

**Las llamadas salientes andan pero las entrantes no.**
Casi siempre es el Paso 3: el webhook del número no está apuntado, o apunta a
una dirección que ya no existe.

**Las llamadas entrantes se cortan apenas atienden.**
Falta el Auth Token cargado, o la URL pública configurada no coincide con la
que pusiste en Twilio. El programa verifica que cada aviso venga realmente de
Twilio, y esa verificación se hace sobre la dirección exacta: si no coinciden,
se rechaza. Es a propósito — sin esa verificación, cualquiera podría meter
respuestas falsas en una llamada en curso.

**¿Puedo usar mi central telefónica en vez de Twilio?**
Sí. Si ya tenés Avaya, Asterisk, Genesys o Cisco, MV Kobra AI se conecta a esa
central y no hace falta Twilio. Preguntanos por ese camino.

**¿Y si no quiero llamadas, solo el dashboard?**
No configures nada de esto. El programa funciona igual: cartera, ProbPago,
priorización, copiloto sobre grabaciones que subas a mano, e informes.
