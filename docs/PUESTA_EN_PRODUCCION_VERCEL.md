# Poner a vender: Vercel Pro + MercadoPago, paso a paso

> Todo lo que hay que tocar **fuera del repo** para que la web cobre de verdad.
> Los precios y límites de este documento se verificaron contra la documentación
> de Vercel el 24/08/2026 — si pasó tiempo, confirmalos antes de decidir.

---

## 1. El número que cambia la decisión

Vercel Pro **no se cobra por proyecto**. Se cobra por *asiento que despliega*:

| Concepto | Precio |
|---|---|
| Plataforma Pro | **US$20/mes**, incluye 1 asiento que despliega **y US$20 de crédito de uso** |
| Asiento adicional (Owner/Member) | US$20/mes cada uno |
| Asiento Viewer (solo lectura) | **Gratis, ilimitados** |

Uso incluido por mes, **antes** de tocar el crédito:

- **1 TB** de Fast Data Transfer
- **10.000.000** de Edge Requests

Recién cuando se pasa de eso se descuenta de los US$20 de crédito, y recién
cuando el crédito se agota se factura por uso.

**Lo que esto significa acá:** un titular solo, con N proyectos que son landings
y funciones serverless, paga **US$20/mes en total** — el crédito ni se toca. La
cantidad de proyectos no entra en la cuenta en ningún lado.

> Antes de migrar nada para ahorrar, mirá **Settings → Billing** de tu equipo:
> si el número que ves ahí no es este, algo más está pasando (add-ons, asientos
> de más) y conviene entenderlo antes de mover proyectos.

### Poné un techo de gasto el primer día

Vercel activa avisos de gasto en US$200 por ciclo **por defecto**. Eso es un
aviso, no un tope. En **Settings → Billing → Spend Management** se define un
monto y qué hacer al llegar (avisar, o pausar). Ponelo apenas creás el equipo:
es la diferencia entre "me llegó un mail" y "me llegó una factura".

### Add-ons que NO hacen falta

Aparecen en la misma pantalla y son caros: SAML SSO (US$300/mes), HIPAA BAA
(US$350), Advanced Deployment Protection (US$150), Flags Explorer (US$250),
Static IPs (US$100 por proyecto), Speed Insights (US$10 por proyecto). Ninguno
es necesario para vender. No los actives "por las dudas".

### El dominio gratis no aplica a este caso

Pro regala un dominio el primer año, pero solo en `.online`, `.site`, `.space`,
`.store`, `.tech` y `.website`. `mvkobranzaia.com` no está en esa lista.

---

## 2. Por qué Pro y no Hobby

El plan Hobby de Vercel es para uso **personal y no comercial**. Una tienda con
checkout de MercadoPago publicada es uso comercial desde que está en línea — no
desde la primera venta, y no desde que alguien toca Comprar.

O sea: mientras la landing con precios esté deployada y cobrando, Hobby no
corresponde. Con Pro a US$20/mes eso deja de ser un tema.

---

## 3. Consolidar los proyectos en un equipo

Orden que evita downtime:

1. **Crear el equipo Pro.** Dashboard → selector de equipo → *Create Team* →
   elegir Pro. Ahí mismo se paga.
2. **Poner el techo de gasto** (arriba). Antes de mover nada.
3. **Transferir cada proyecto**, de a uno: entrar al proyecto → **Settings →
   General → Transfer Project** → elegir el equipo nuevo.
4. **Revisar el dominio** del proyecto que lo tenga. Los dominios acompañan al
   proyecto, pero es lo primero que hay que verificar después de cada
   transferencia — es lo único cuya rotura se ve desde afuera.
5. **Volver a cargar las variables de entorno** que no hayan viajado (ver
   abajo) y **redesplegar** para que tomen efecto.

> Si algo tiene Stores (KV, Postgres, Blob) conectados, esos se transfieren
> aparte: Vercel no los arrastra solo.

---

## 4. Variables de entorno para cobrar

Se cargan en **Settings → Environment Variables** del proyecto, alcance
**Production**. Después de cargarlas hay que **redesplegar**: una función
serverless lee el entorno al arrancar, no en cada request.

> **Antes de mirar la tabla, corré esto:**
>
> ```bash
> python3 verificar_configuracion.py
> ```
>
> Te dice cuáles están puestas, cuáles faltan y **qué se rompe exactamente**
> sin cada una. Nunca imprime el valor de ninguna, así que se puede correr
> compartiendo pantalla.
>
> La plantilla con todas las variables está en **`env.example`**: copiala a
> `.env` para desarrollo local (`.env` está en `.gitignore`; la plantilla no,
> y por eso no lleva ningún valor real).

| Variable | Para qué | Sin ella |
|---|---|---|
| `MP_ACCESS_TOKEN` | Crear la preferencia de pago contra MercadoPago | El checkout devuelve 503 `medio_pago_no_configurado`, o cae al link fijo si hay uno |
| `KOBRA_LICENSE_PRIVATE_KEY` | Firmar la licencia RS256 que recibe el comprador | El pago entra y **no se emite licencia** |
| `RESEND_API_KEY` | Mandar la licencia al comprador y los avisos al dueño | El pago entra, la licencia se emite, **y nadie se entera** (queda solo en el log) |
| `RESEND_FROM` | Remitente propio | Se usa el compartido de prueba de Resend, que **solo entrega a la casilla del titular de la cuenta**: al comprador no le llega |
| `RELEASES_TOKEN` | Bajar el instalador desde el release privado | **Nadie puede descargar el producto** aunque haya pagado |

Opcionales, con default razonable: `MP_CURRENCY` (default `UYU` — la cuenta de
cobro es uruguaya y solo acepta UYU) y `MP_TASA_UYU` (default `40`, el mismo
tipo de cambio de referencia que muestra la landing).

### `RESEND_FROM` es el que más se pasa por alto

Con la clave de Resend puesta pero sin dominio verificado, los mails salen desde
el remitente compartido de prueba y **solo llegan a tu propia casilla**. El
comprador paga y no recibe la licencia, y desde tu lado se ve todo bien porque
a vos sí te llegó la copia.

Para arreglarlo: verificar `mvkobranzaia.com` en Resend (te da unos registros
DNS para cargar donde tengas el dominio) y después poner
`RESEND_FROM="MV Kobra AI <licencias@mvkobranzaia.com>"`.

---

## 5. Qué avisa cada cosa

Hay dos avisos y son señales distintas. No los confundas: uno es plata, el otro
es interés.

| Cuándo | Qué lo dispara | Adónde llega |
|---|---|---|
| **Alguien toca Comprar** | `api/checkout.js`, recién cuando MercadoPago aceptó la preferencia | Mail al dueño, con plan, monto, referencia y país |
| **El pago se acredita** | `api/webhook-mercadopago.js`, aviso server-to-server de MercadoPago | Mail al comprador **con la licencia**, con copia al dueño |

El primero se deduplica: **un aviso por visitante y plan cada 30 minutos**.
Comprar software no es un click — es mirar el precio, dudar, volver — y cinco
mails iguales enseñan a ignorar los mails.

Ese dedupe es de mejor esfuerzo: vive en la memoria de la instancia serverless,
así que si el mismo visitante cae en dos instancias distintas te llegan dos
avisos. Es aceptable a propósito; una base compartida para no repetir un mail es
más pieza de la que el problema justifica.

**El aviso nunca puede costar una venta.** Si Resend está caído o sin
configurar, el comprador recibe igual su URL de pago. Está fijado con tests.

---

## 6. Orden para probarlo sin gastar

1. Cargá `RESEND_API_KEY` y redesplegá. Tocá Comprar en la landing: **te tiene
   que llegar el mail de intención**. Todavía no pagaste nada.
2. Verificá el dominio en Resend y poné `RESEND_FROM`. Repetí el paso 1 y
   confirmá que el remitente ya es el tuyo.
3. Con las credenciales de **prueba** de MercadoPago, hacé un pago completo con
   una tarjeta de test. Tienen que llegar los dos mails: el de intención y el de
   licencia.
4. Recién ahí pasá a las credenciales productivas.
5. `RELEASES_TOKEN` **antes** de la primera venta real: sin eso, alguien te paga
   y no puede bajar el producto.

---

## 7. Lo que este documento no cubre

- **El servicio de tiempo real** (`realtime/server.py`) no vive en Vercel: es
  un proceso propio, y solo hace falta si vas a usar voz con Twilio. Ver
  `docs/GUIA_LLAMADA_REAL_TWILIO.md`.
- **El producto instalado** corre en la máquina del cliente. No necesita tu
  infraestructura para funcionar.
