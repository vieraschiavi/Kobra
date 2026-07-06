# MV Kobra AI — Whitepaper de seguridad (borrador)

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

## 1. Qué es MV Kobra AI y cómo se despliega

MV Kobra AI es un sistema de cobranzas inteligentes con dos superficies:

1. **Dashboard operativo** (`app/app.py`, Streamlit): corre **local**, en la
   máquina del cliente o en un servidor propio del cliente — no es un SaaS
   multi-tenant hosteado por nosotros. El cliente controla dónde vive el
   dato en todo momento.
2. **Landing + demo pública** (`mvkobranzaia.com`): sitio de marketing y
   demo con **datos 100% sintéticos** — nunca procesa datos reales de
   deudores de ningún cliente.
3. **Backend de licencias/gateway** (`backend_venta/`, opcional): solo se usa
   si el cliente elige la modalidad "Edición Venta" con APIs medidas en vez
   de traer sus propias claves (BYOK). Ver sección 6.

## 2. Datos que procesa MV Kobra AI

- **Cartera de deudores**: identificador, segmento, producto, tramo de mora,
  monto de deuda, departamento. En la instalación estándar, estos datos
  **no salen de la máquina/servidor del cliente** salvo que el propio
  cliente configure una integración de exportación (ver sección 5).
- **Grabaciones/transcripciones de llamadas o WhatsApp**: si el cliente activa
  voz real (Twilio) o WhatsApp, el contenido de esas conversaciones se
  procesa para negociar y tipificar el resultado. Se envían a proveedores de
  IA de terceros (ver sección 4) solo si el cliente configura esas claves.
- **Voz premium opcional (ElevenLabs)**: si se configura `ELEVENLABS_API_KEY`
  y se elige una voz, el **texto que el Gestor IA va a decir** (no lo que
  dice el deudor) se envía a ElevenLabs para sintetizar el audio de la
  llamada — solo si el cliente activa esto explícitamente; por default las
  llamadas siguen usando Twilio/Polly, sin este envío adicional.
- **Ninguna base de datos con nombres/teléfonos reales viaja en este
  repositorio.** El dataset de demostración es 100% sintético (ver
  "Honestidad de los números" en `README.md`).
- **Consultas en lenguaje natural sobre la base del cliente** (`kobra/consulta_bd.py`,
  opcional): si el cliente conecta su propia base de datos para preguntarle en
  español, a la API de Claude **solo le llega el esquema** (nombres de tabla/
  columna/tipo y unas pocas muestras de valores de texto para dar contexto de
  dominio) — **nunca los datos reales de las filas**. La conexión es de solo
  lectura a nivel de aplicación: el validador bloquea cualquier SQL que no sea
  `SELECT`/`WITH` antes de ejecutarlo. La URL de conexión nunca se loguea
  completa (solo el host, igual que en `kobra/integracion.py`).

## 3. Autenticación y control de acceso

- El dashboard exige **login** desde el primer uso (`kobra/autenticacion.py`):
  no hay acceso anónimo. Contraseñas en hash **PBKDF2-HMAC-SHA256 + salt**
  (200.000 iteraciones) — nunca en texto plano.
- **Dos roles**: `admin` (todo, incluida la configuración de API keys) y
  `gestor` (operación diaria, sin acceso a configuración ni secretos).
- **SSO corporativo real vía OIDC** (`kobra/sso_oidc.py`), opcional: compatible
  con cualquier proveedor estándar (Microsoft Entra ID/Azure AD, Okta, Google
  Workspace, Auth0, Keycloak...). Authorization Code flow, verificación del
  ID token contra el JWKS del proveedor (firma + emisor + audiencia — nunca
  se confía en un token sin verificar), y mapeo de rol por lista de emails
  administradores. Convive con el login local, no lo reemplaza. Se activa
  solo, cargando el issuer/client id/secret propios en la pestaña
  Configuración — no hace falta tocar código.
- **Limitación conocida, declarada**: el SSO es autenticación (quién sos),
  no aprovisionamiento automático de usuarios (SCIM) ni grupos de Azure
  AD/Okta mapeados a roles — el mapeo de admin/gestor es una lista plana de
  emails, no una integración con grupos del directorio.

## 4. Secretos y claves de API

- Las API keys (Anthropic, OpenAI, Twilio, ElevenLabs, ERP) se guardan con una cadena de
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
  jurídica; MV Kobra AI provee el mecanismo para hacerla cumplir.

## 9. Qué NO incluye hoy (declarado explícitamente)

Para que la evaluación de compras no dependa de asumir nada:

- **Multi-tenancy**: el dashboard Streamlit es de **instalación única por
  cliente** (por diseño — cada empresa corre su propia instancia con sus
  propios datos, no hay aislamiento "lógico" de varios clientes en un mismo
  proceso porque no comparten proceso). El **backend de licencias/gateway**
  (`backend_venta/`, opcional) sí es multi-cliente de fábrica: cada licencia
  JWT está atada a un `cliente_id`, con cupo y uso medidos por separado por
  cliente (`backend_venta/uso.py`) — eso es lo que se usa si varios clientes
  comparten ese servicio hosteado.
- **SSO**: sí disponible (sección 3) — OIDC genérico, no específicamente
  SAML. Sin aprovisionamiento SCIM ni mapeo de grupos del directorio.
- No hay un compromiso de SLA de uptime — el dashboard corre en la
  infraestructura que el cliente elija; el uptime es responsabilidad de esa
  infraestructura, no de un servicio hosteado por nosotros. (Plantilla en
  `docs/PLANTILLA_SLA.md`, para completar con números reales si se ofrece.)
- **Residencia de datos**: no hay un compromiso de dónde se alojan los datos
  porque, en la instalación estándar, **los aloja el propio cliente** — la
  pregunta de residencia se resuelve con dónde el cliente elige correr el
  dashboard (su propio servidor en Uruguay, una VM en una región de AWS/Azure
  específica, etc.), no con una decisión nuestra. Si se usa el backend de
  licencias/gateway hosteado, ahí sí aplica preguntar dónde se despliega.
- No hay certificación formal (ISO 27001, SOC 2) de la organización.
- **Backup/DR**: `kobra/backup.py` (`python -m kobra.backup crear`) empaqueta
  cartera, gestiones, lista de no-contactar, log de auditoría, config
  cifrada y la base de uso del backend de licencias en un ZIP con fecha, al
  destino que el cliente elija (carpeta local, o una ya sincronizada a la
  nube). **No lo automatiza solo** — programarlo (Programador de tareas en
  Windows, cron en Linux/macOS) y elegir dónde se guarda el backup (fuera de
  esta misma máquina, para que sirva de verdad como DR) es responsabilidad
  del cliente, o se puede conversar como servicio adicional.
- El log de auditoría es un archivo local con cadena de hashes, no un
  servicio de logging externo gestionado.

## 10. Contacto

Para preguntas de seguridad específicas de tu evaluación, o para acordar
controles adicionales (VPC dedicada, revisión de código, pentest previo a
la firma), contactar directamente al equipo de MV Kobra AI.
