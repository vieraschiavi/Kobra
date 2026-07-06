# Kobra IA — Whitepaper de seguridad (borrador)

> **Este documento es un borrador de referencia**, pensado para responder el
> cuestionario de seguridad que pide el área de compras/InfoSec de un banco,
> financiera o cooperativa antes de aprobar un proveedor. Describe el estado
> **real** del sistema a la fecha de este documento — no promete nada que el
> código no haga. Revisalo con quien vaya a firmar el contrato antes de
> entregarlo a un cliente: puede haber cosas que quieras aclarar, matizar o
> ampliar según el trato puntual (on-premise, VPC dedicada, etc.).
>
> Fecha de referencia: julio 2026 · Versión del producto: ver `README.md`.

---

## 1. Qué es Kobra y cómo se despliega

Kobra IA es un sistema de cobranzas inteligentes con dos superficies:

1. **Dashboard operativo** (`app/app.py`, Streamlit): corre **local**, en la
   máquina del cliente o en un servidor propio del cliente — no es un SaaS
   multi-tenant hosteado por nosotros. El cliente controla dónde vive el
   dato en todo momento.
2. **Landing + demo pública** (`kobra-ia.vercel.app`): sitio de marketing y
   demo con **datos 100% sintéticos** — nunca procesa datos reales de
   deudores de ningún cliente.
3. **Backend de licencias/gateway** (`backend_venta/`, opcional): solo se usa
   si el cliente elige la modalidad "Edición Venta" con APIs medidas en vez
   de traer sus propias claves (BYOK). Ver sección 6.

## 2. Datos que procesa Kobra

- **Cartera de deudores**: identificador, segmento, producto, tramo de mora,
  monto de deuda, departamento. En la instalación estándar, estos datos
  **no salen de la máquina/servidor del cliente** salvo que el propio
  cliente configure una integración de exportación (ver sección 5).
- **Grabaciones/transcripciones de llamadas o WhatsApp**: si el cliente activa
  voz real (Twilio) o WhatsApp, el contenido de esas conversaciones se
  procesa para negociar y tipificar el resultado. Se envían a proveedores de
  IA de terceros (ver sección 4) solo si el cliente configura esas claves.
- **Ninguna base de datos con nombres/teléfonos reales viaja en este
  repositorio.** El dataset de demostración es 100% sintético (ver
  "Honestidad de los números" en `README.md`).

## 3. Autenticación y control de acceso

- El dashboard exige **login** desde el primer uso (`kobra/autenticacion.py`):
  no hay acceso anónimo. Contraseñas en hash **PBKDF2-HMAC-SHA256 + salt**
  (200.000 iteraciones) — nunca en texto plano.
- **Dos roles**: `admin` (todo, incluida la configuración de API keys) y
  `gestor` (operación diaria, sin acceso a configuración ni secretos).
- **Limitación conocida, declarada**: no hay SSO/SAML/OIDC contra un
  directorio corporativo (Azure AD, Okta, etc.) todavía — es autenticación
  local propia del producto. Si tu política exige SSO federado, es un punto
  a conversar antes de contratar.

## 4. Secretos y claves de API

- Las API keys (Anthropic, OpenAI, Twilio, ERP) se guardan con una cadena de
  respaldo automática (`kobra/config.py`): **keyring del sistema operativo**
  (Windows Credential Manager / macOS Keychain / Secret Service en Linux de
  escritorio) cuando está disponible → si no, **archivo cifrado** (Fernet/
  AES-128, clave separada con permisos restringidos) → texto plano **solo**
  si ninguna librería de cifrado está instalada (caso degradado, se avisa
  explícitamente en la propia interfaz).
- Ninguna clave de API real ni credencial de terceros se guarda en este
  repositorio de código en ningún caso.

## 5. Integración con sistemas del cliente (ERP/CRM)

- `kobra/integracion.py` exporta o sincroniza los resultados de gestión a
  **cualquier sistema que el cliente elija**: archivo (CSV/Excel/JSON), API
  REST propia (Bearer token) o base de datos SQL directa (Postgres, MySQL,
  SQL Server, SQLite, vía SQLAlchemy). La URL/credenciales de esa conexión
  las define y controla el cliente; nunca quedan en este repositorio.
- Las URLs de conexión a base de datos **no se registran en texto plano** en
  el log de auditoría (se guarda solo el host, nunca usuario/contraseña).

## 6. Log de auditoría

- `kobra/auditoria.py`: registro **append-only** con cadena de hashes (cada
  entrada referencia el hash de la anterior) — editar o borrar una línea por
  fuera de la aplicación rompe la verificación de integridad, detectable
  con `verificar_integridad()` y visible en la pestaña Configuración.
- Registra: logins/logouts, cambios de configuración y contraseñas,
  gestiones registradas, y envíos/sincronizaciones al ERP del cliente.
- **Limitación declarada**: es un log de archivo local con cadena de hashes,
  no un SIEM/WORM storage certificado de nivel enterprise. Para una entidad
  que exija retención regulatoria de logs en almacenamiento inmutable
  externo, hay que exportar/reenviar este log a esa plataforma (no está
  automatizado hoy).

## 7. Backend de licencias/gateway (`backend_venta/`, opcional)

Solo aplica si el cliente elige la modalidad de APIs medidas en vez de BYOK:

- Licencias firmadas **JWT (HS256)** con cupo mensual y features por plan.
- El gateway de Claude valida la licencia y el cupo en cada llamada antes de
  invocar la API real; mide tokens de entrada/salida por cliente.
- Los gateways de TTS/Twilio/WhatsApp tienen el mismo circuito de
  licencia+cupo+medición armado, pero **no hay un proveedor real conectado
  todavía** (devuelven `501` explícito) — no se ofrece esa modalidad hasta
  que se conecte.
- El webhook de pago **nunca confía en el cuerpo del webhook**: vuelve a
  consultar el estado del pago contra la API real de MercadoPago antes de
  emitir una licencia.

## 8. Cumplimiento normativo de la operación de cobranza

- `kobra/cumplimiento.py`: franja horaria permitida (configurable, default
  09–20 L–S Uruguay), feriados nacionales, tope de frecuencia de contacto
  por deudor (anti-hostigamiento), y lista de "No Contactar"/opt-out que se
  respeta automáticamente en llamadas y WhatsApp.
- Esto es una **herramienta de apoyo al cumplimiento, no asesoría legal** —
  cada empresa fija su política según su marco regulatorio y su asesoría
  jurídica; Kobra provee el mecanismo para hacerla cumplir.

## 9. Qué NO incluye hoy (declarado explícitamente)

Para que la evaluación de compras no dependa de asumir nada:

- No hay multi-tenancy (una instalación = un cliente).
- No hay SSO/SAML/OIDC corporativo.
- No hay un compromiso de SLA de uptime — el dashboard corre en la
  infraestructura que el cliente elija; el uptime es responsabilidad de esa
  infraestructura, no de un servicio hosteado por nosotros.
- No hay certificación formal (ISO 27001, SOC 2) de la organización.
- No hay backup/DR automatizado del lado nuestro — los datos viven donde el
  cliente los aloja, y el backup de esa infraestructura es responsabilidad
  del cliente (o se puede conversar como servicio adicional).
- El log de auditoría es un archivo local con cadena de hashes, no un
  servicio de logging externo gestionado.

## 10. Contacto

Para preguntas de seguridad específicas de tu evaluación, o para acordar
controles adicionales (VPC dedicada, revisión de código, pentest previo a
la firma), contactar directamente al equipo de Kobra IA.
