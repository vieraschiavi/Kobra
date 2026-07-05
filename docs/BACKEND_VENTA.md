# Kobra IA — Backend de venta (licencias, gateway de APIs y descarga)

Diseño y andamiaje para comercializar Kobra de forma profesional: entregar el
programa con las APIs **embebidas y medidas**, cobrando por uso y quedando cubierto
en costos. Complementa el plan comercial (ver el dossier de negocio).

> **Nota de datos/seguridad:** ninguna clave de API real ni número de cuenta
> bancaria se guarda en este repositorio. Las claves viven como variables de
> entorno/secretos del servidor; la cuenta de cobro se configura en el panel de la
> pasarela de pago, nunca en el código.

---

## 1. Panorama

```
  Cliente compra en la landing
        │  (tarjeta · MercadoPago · transferencia)
        ▼
  Pasarela de pago  ──webhook──►  Backend de venta
        │                              │
        │  deposita a tu cuenta        ├─ emite LICENCIA firmada (JWT)
        │  Itaú USD (config panel)     ├─ habilita DESCARGA del instalador
        ▼                              └─ crea registro de USO (cupo del plan)
  (dinero a tu banco)

  App de PC (Edición Venta)
        │  cada gestión → POST /gateway/*  con la licencia
        ▼
  GATEWAY de APIs  ── inyecta claves reales (server-side) ──►  Claude / TTS / Twilio / WhatsApp
        │
        └─ MIDE tokens/gestiones por licencia → cupo + excedente facturable
```

Tres servicios (pueden vivir en un mismo proceso FastAPI):

1. **Licencias** — emite y valida tokens firmados atados a plan y cupo.
2. **Gateway de APIs** — proxy que inyecta las claves y **mide el uso**.
3. **Descarga + webhooks de pago** — libera el instalador tras el pago.

---

## 2. Licencias (JWT firmado)

- Al confirmarse el pago, el backend emite un JWT firmado (HS256/RS256) con:
  `sub` (cliente), `plan` (`starter|pro|enterprise`), `edition` (`venta`),
  `cupo_mensual`, `exp`, `features` (voz, whatsapp, twilio, erp).
- La app guarda la licencia (ya existe `kobra/config.py` para persistir claves/opciones).
- El gateway valida la firma y el cupo en cada request. Sin licencia válida →
  la Edición Venta no habilita las funciones pagas.

```python
# firma/verificación (esbozo)
import jwt, time
def emitir_licencia(cliente_id, plan, cupo, features, secreto):
    return jwt.encode({
        "sub": cliente_id, "plan": plan, "edition": "venta",
        "cupo_mensual": cupo, "features": features,
        "iat": int(...), "exp": int(...) + 30*24*3600,   # 1 mes
    }, secreto, algorithm="HS256")

def validar(token, secreto):
    return jwt.decode(token, secreto, algorithms=["HS256"])  # lanza si inválida/expirada
```

> Los timestamps se inyectan desde el entorno de ejecución del servidor (no se
> hardcodean).

### 2.1 Demo completa · 3 días por usuario registrado

Cada usuario que se registra obtiene acceso **full a la demo por 3 días**. En la web
esto hoy es un gate cliente-side (registro → `localStorage` → 72 h; ver
`landing/index.html` y `dashboard_estatico/index.html`) que sirve para captar el lead
y dejar probar sin fricción. La versión de producción lo hace del lado servidor:

```python
def emitir_trial(cliente_id, email):
    return emitir_licencia(cliente_id, plan="trial", cupo=CUPO_TRIAL,
                           features=FEATURES_FULL, secreto=SECRETO,
                           dias=3)                    # exp = ahora + 3 días
# al registrarse: guardar el lead (email/tel/empresa) + emitir_trial(...)
# la app/demo valida la licencia; vencida → pide comprar un plan
```

Así el registro queda trazado (lead real), el trial es infalsificable (token firmado
con expiración) y al vencer se ofrece la compra. El gate cliente-side es la versión
demo; producción usa este token.

---

## 3. Gateway de APIs con medición

El gateway es un proxy fino delante de cada proveedor. La app **nunca** ve las
claves reales; manda su licencia y el gateway agrega la clave del lado servidor.

```python
# esbozo FastAPI
from fastapi import FastAPI, Header, HTTPException
app = FastAPI()

@app.post("/gateway/claude")
async def claude(payload: dict, authorization: str = Header(...)):
    lic = validar(authorization.removeprefix("Bearer ").strip(), SECRETO)
    consumido = uso_mes(lic["sub"])                      # gestiones usadas este mes
    if consumido >= lic["cupo_mensual"] and not plan_permite_excedente(lic):
        raise HTTPException(402, "Cupo agotado")
    # Claude embebida (clave del servidor, nunca en la app):
    resp = anthropic_client.messages.create(model="claude-sonnet-5", **payload)
    registrar_uso(lic["sub"], canal="claude",
                  tok_in=resp.usage.input_tokens,
                  tok_out=resp.usage.output_tokens)       # medición para facturar
    return resp.model_dump()
```

Endpoints análogos para `/gateway/tts`, `/gateway/twilio`, `/gateway/whatsapp`.
Cada uno inyecta su clave (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, credenciales
Twilio/WhatsApp) desde variables de entorno del servidor.

### Esquema de uso (para facturar)

| columna         | descripción                                   |
|-----------------|-----------------------------------------------|
| `cliente_id`    | de la licencia                                |
| `fecha`         | timestamp del servidor                        |
| `canal`         | claude / tts / twilio / whatsapp              |
| `gestion_id`    | id de gestión (correlaciona con la sábana)    |
| `tok_in/out`    | tokens (Claude)                               |
| `unidades`      | minutos (voz/telefonía) o mensajes (WhatsApp) |
| `costo_est`     | costo estimado (para margen)                  |

Fin de mes: `base + max(0, usado − cupo) × precio_excedente` por cliente.

---

## 4. Descarga post-pago + webhook de la pasarela

```python
@app.post("/webhooks/pago")                # lo llama la pasarela (Lemon Squeezy / MercadoPago / dLocal)
async def pago(evt: dict):
    verificar_firma(evt)                   # HMAC del proveedor
    if evt["status"] == "paid":
        lic = emitir_licencia(evt["cliente"], evt["plan"], cupo_de(evt["plan"]), features_de(evt["plan"]), SECRETO)
        token_descarga = crear_token_descarga(evt["cliente"])   # un solo uso, corto
        enviar_email(evt["email"], link_descarga(token_descarga), lic)
    return {"ok": True}

@app.get("/descargar/{token}")
async def descargar(token: str):
    validar_token_descarga(token)          # un uso
    return FileResponse("dist/KobraIA_Setup.exe")   # instalador Edición Venta
```

La cuenta bancaria de cobro se configura **una sola vez** en el panel de la
pasarela; no aparece en este código ni en la landing.

---

## 5. Dos ediciones (mismo código base)

Un flag de compilación decide la edición:

| Flag / build            | `KOBRA_EDITION=venta`         | `KOBRA_EDITION=propio`      |
|-------------------------|-------------------------------|-----------------------------|
| Licencia                | requerida (valida contra JWT) | omitida                     |
| APIs                    | vía gateway (medido) o BYO    | claves propias, sin límite  |
| Medición / cupos        | activada                      | desactivada                 |
| Marca                   | "Un producto de MV" + white-label opcional | interna       |

El instalador Windows ya existe (`packaging/`); solo se parametriza por edición.

### Combo B — "Traé tus APIs" (BYO-keys)

Ya soportado hoy: el cliente pega sus propias claves en la pestaña
**Configuración** de la app (`kobra/config.py`). En ese combo el gateway se
saltea y el cliente paga su propio uso; el software se vende más barato
(o perpetuo) y vos no asumís costo de API.

---

## 6. Stack de pagos sugerido

- **Merchant of Record** (Lemon Squeezy / Paddle): venta global de software,
  manejan IVA/impuestos y depositan a tu banco. Punto de partida recomendado.
- **MercadoPago / dLocal**: medios locales de LATAM (tarjeta en cuotas,
  transferencia, redes de cobranza). dLocal es uruguaya.
- **Stripe**: tarjetas globales (requiere resolver el payout a UY).

Todos exponen un webhook `pago confirmado` que dispara la emisión de licencia y
la descarga (sección 4).

### 6.1 MercadoPago (configurado) — combos: ambos

Cuenta de cobro (collector): **MercadoPago 1007782272006**. El **Access Token es
secreto** y va como variable de entorno del servidor (`MP_ACCESS_TOKEN`), nunca en
el repo ni en la landing. El dinero cae en la cuenta dueña de ese token.

Flujo **Checkout Pro**: el backend crea una *preferencia* → devuelve `init_point`
→ la landing redirige al usuario → paga (tarjeta, cuotas, dinero en cuenta,
transferencia) → MercadoPago manda el webhook → se emite la licencia y se libera
la descarga.

```python
import os, mercadopago                      # pip install mercadopago
sdk = mercadopago.SDK(os.environ["MP_ACCESS_TOKEN"])   # secreto, del entorno
PRECIOS = {"pro": 149.0, "starter": 490.0}             # USD; ajustar por plan/combo

@app.post("/checkout/mercadopago")
async def checkout_mp(plan: str, email: str):
    pref = {
        "items": [{"title": f"Kobra IA · {plan}", "quantity": 1,
                   "unit_price": PRECIOS[plan], "currency_id": "USD"}],
        "payer": {"email": email},
        "back_urls": {"success": f"{BASE}/gracias", "failure": f"{BASE}/precios",
                      "pending": f"{BASE}/pendiente"},
        "auto_return": "approved",
        "notification_url": f"{BASE}/webhooks/mercadopago",
        "metadata": {"plan": plan, "email": email},
    }
    r = sdk.preference().create(pref)
    return {"init_point": r["response"]["init_point"]}   # la landing redirige acá

@app.post("/webhooks/mercadopago")
async def wh_mp(evt: dict):
    if evt.get("type") == "payment":
        pago = sdk.payment().get(evt["data"]["id"])["response"]
        if pago["status"] == "approved":
            md = pago["metadata"]
            lic = emitir_licencia(md["email"], md["plan"],
                                  cupo_de(md["plan"]), features_de(md["plan"]), SECRETO)
            enviar_email(md["email"], link_descarga(crear_token_descarga(md["email"])), lic)
    return {"ok": True}
```

**Combo BYO** (traé tus APIs): mismo checkout, pero la licencia emitida marca
`mode="byo"` y la app usa las claves que el cliente carga en Configuración; el
gateway medido se saltea.

**dLocal / MoR**: se suman igual — cada uno crea su “preferencia/checkout” y
apunta su webhook a `/webhooks/<pasarela>`, que reutiliza la misma emisión de
licencia. Empezá con MercadoPago para LATAM y sumá dLocal para más métodos locales.

---

## 7. Checklist para poner en marcha

- [ ] Cargar claves reales como secretos del servidor (Claude, OpenAI, Twilio, WhatsApp).
- [ ] Definir `SECRETO` de firma de licencias (rotable).
- [ ] Abrir cuenta en la pasarela y cargar la cuenta Itaú USD en su panel.
- [ ] Conectar el webhook de la pasarela a `/webhooks/pago`.
- [ ] Compilar instalador `Edición Venta` y publicarlo detrás de `/descargar/{token}`.
- [ ] Definir precios de excedente por canal (3–5× costo).
