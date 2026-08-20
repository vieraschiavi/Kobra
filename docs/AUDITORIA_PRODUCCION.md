# MV Kobra AI — Auditoría de producción (agosto 2026)

> Método: **evidencia ejecutada o no cuenta.** Cada verificación de abajo se
> corrió de verdad en esta auditoría; lo que no se pudo correr desde este
> entorno está marcado PARCIAL con el motivo y el paso exacto que falta.
> Guion reproducible: `python3 auditoria_e2e.py` (34 verificaciones E2E).

## Resumen

| Área | Verificación | Resultado |
|---|---|---|
| Suite completa | 4 gates de CI locales (`verificar.py`) | ✅ 1327 tests, ruff, 70 tests Node, dataset |
| Recorrido comercial | 34 checks E2E contra el backend real | ✅ 34/34 |
| Seguridad | Secretos, eval, auth de 88 endpoints, npm audit, pip check | ✅ sin hallazgos |
| Instalador | 102 tests (incluye compilación real con makensis) | ✅ |
| Servidor real | uvicorn arranca, /api/health, frontend servido | ✅ |
| Web | Precios coherentes en 3 fuentes, i18n completa 3 idiomas | ✅ (en suite) |
| **Windows real** | Instalar el .exe en una máquina Windows | ⚠️ PARCIAL |
| **Pago real** | Una compra con dinero real por MercadoPago | ⚠️ PARCIAL |
| **CI en GitHub** | Actions con cuota agotada: 8 corridas sin runner | ⚠️ PARCIAL |

## El recorrido comercial, verificado end-to-end

Los 34 checks corren contra el backend real (FastAPI + los firmadores de Node
de producción), con una instalación limpia por escenario:

1. **Instalación limpia** — pide licencia, nada expuesto sin sesión (401),
   `owner-login` no existe en la copia del cliente (404).
2. **Demo** — el trial activa, dura 7 días, y con él se trabaja (KPIs 200
   sobre la cartera scoreada real del pipeline).
3. **Trial vencido** — rechazado con "venció", distinto de "inválida": uno
   manda a comprar, el otro a soporte.
4. **Compra** — `api/_license.js` (el firmador real de producción, ejecutado
   con Node) emite; la copia instalada valida con PyJWT y activa. Plan pro,
   sin trial, usa el producto.
5. **Módulo suelto** — Node emite la licencia de Logística; activa, Logística
   responde y Gobernanza sigue cortada (no vino de regalo).
6. **Gateo por plan** — 12 combinaciones plan×módulo dan exactamente el HTTP
   esperado: Básico 403 en todo, Pro solo gobernanza, Starter +medidas,
   Enterprise los tres.
7. **Owner** — la credencial `mail|código` activa por el campo de licencia,
   queda sin vencimiento, persiste, entra como admin; un código equivocado
   NO desbloquea. (El mecanismo se probó con un par scrypt inyectado: el
   código real no está en el repo, que es lo correcto.)

## Seguridad

* **Sin claves privadas ni secretos versionados** (git grep con patrones
  partidos; el `.env` no está trackeado).
* **Sin `eval`/`exec`** en código de producto — el único match es el
  comentario de `kobra/medidas.py` explicando por qué NO se usa. El parser de
  fórmulas es lista blanca sobre `ast`, verificado ejecutando los ataques
  contra ambas implementaciones.
* **88 endpoints**: 77 exigen sesión; 11 son públicos por diseño (salud,
  login/setup, activación de licencia, portal público de pago del deudor);
  `/api/erp/imputaciones` autentica por API key con `hmac.compare_digest`.
* **`npm audit --omit=dev`: 0 vulnerabilidades. `pip check`: sin conflictos.**
* Nota de método: la primera pasada de esta auditoría reportó DOS falsos
  hallazgos ("clave privada" y "secreto hardcodeado") por un error de shell
  (`| head` se traga el código de salida de git grep). Se reverificó sin el
  pipe: limpios. Queda anotado para que la próxima auditoría no repita el
  error — y como recordatorio de que un FAIL también hay que verificarlo.

## Lo que separa esto de un 10, con honestidad

La nota del código y las pruebas es alta. Lo que NO se pudo verificar desde
este entorno, y sin lo cual "listo para producción" es una afirmación a
medias:

1. **El .exe en Windows real.** Acá no hay Windows: la compilación NSIS y los
   102 tests del instalador pasan, y la prueba de humo de CI (que arranca el
   motor PyInstaller de verdad) existe — pero la cuota de Actions la tiene
   frenada, y la última instalación real reportada por el dueño falló al
   extraer (antivirus o descarga corrupta; para eso se publicó el SHA256 y
   `Instalar_en_otro_disco.bat`). **Hasta instalar en una máquina real, no
   se declara.**
2. **`KOBRA_LICENSE_PRIVATE_KEY` en Vercel.** El cruce Node→Python está
   probado con las dos firmas, pero en producción la copia instalada NO
   comparte secreto con el servidor: una compra real solo activa por RS256,
   y eso requiere la clave privada cargada en Vercel. **Es EL paso que
   decide si "el que paga puede entrar" en producción.** Está entregada; hay
   que pegarla.
3. **Una compra real con dinero real.** El webhook está probado contra mocks
   de MercadoPago (69 casos, incluidos reintentos e idempotencia) y el
   checkout crea preferencias reales — pero el circuito con plata de verdad
   y el mail de la licencia llegando a una casilla real no se ejecutó nunca.
4. **CI verde en GitHub.** Los mismos 4 gates pasan localmente; Actions lleva
   8 corridas muertas en <5s con 0 runners (cuota/spending limit).

## Nota final: 8.5/10

**Por qué no 9:** los cuatro puntos de arriba son exactamente los que un
comprador empresarial va a ejercitar el primer día, y ninguno es verificable
desde este entorno — son pasos del dueño. **Con (1) y (2) hechos, la nota
sube a 9; con (3) verificada, a 9.5.** Lo que falta no es código: es la
verificación en el mundo real que ningún test sustituye.

Lo que sí se afirma sin reservas: no se conoce ningún bug abierto; cada bug
encontrado en este ciclo (14 en total, del validador SQL al precio que
cobraba el doble de lo mostrado) está arreglado con un test que impide que
vuelva; y las tres ediciones —demo, paga y owner— hacen lo estipulado en
todos los escenarios ejecutables por software.
