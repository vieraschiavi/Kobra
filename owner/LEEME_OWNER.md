# 🔑 MV Kobra AI · Versión OWNER (solo para el dueño del producto)

Esta carpeta **no se distribuye nunca**: no entra en el instalador de clientes
(`packaging/kobra.spec` no la empaqueta), no entra en los ZIP de release
(`packaging/build_release.py` no la copia) y está excluida del deploy web
(`.vercelignore`). Es tu copia personal, sin las restricciones comerciales
de la copia de un cliente.

## Qué hace el modo owner

- **Sin licencia, sin trial, sin vencimiento**: arranca directo, sin pedir
  activación ni contraseña — entra como Administrador automáticamente.
- **Acceso completo**: todas las empresas (tenants), todas las pantallas,
  todas las funciones de admin.
- Lo activa la variable de entorno `KOBRA_OWNER=1` sobre el modo standalone.
  El server escucha **solo en 127.0.0.1** (tu propia máquina) — el endpoint
  de entrada directa devuelve 404 en cualquier otro modo, así que la copia
  de un cliente no lo tiene aunque conozca la URL.

> Nota honesta: lo que este modo NO desactiva es el motor de cumplimiento
> (horarios de contacto, feriados, pedidos de no-contactar). Eso no es una
> "restricción de empresa": es lo que hace legal usar el producto con
> deudores reales (Ley 18.331 y equivalentes), y es un argumento de venta.
> Sacarlo te expondría a vos, no a nadie más.

## Cómo usarla

### A) Sin instalar NADA a mano → doble clic en `MVKobraAI_Owner_desde_codigo.bat`
**Esta es la vía recomendada si no tenés el instalador.** El .bat prepara
todo solo, sin que instales nada previo:
1. Si falta Python 3.11+, lo **descarga del sitio oficial e instala en
   silencio** usando PowerShell (incluido en todo Windows — **no depende de
   winget**).
2. **Te pregunta dónde instalar** (Enter usa la sugerida; podés escribir
   cualquier ruta, por ejemplo `D:\MVKobraAI`). Ahí van el entorno y tus
   datos. La elección se recuerda: la próxima vez alcanza con dar Enter.
3. Crea un entorno virtual propio en esa carpeta (no toca tu Python).
4. Instala las dependencias (`requirements.txt`).
5. Usa la interfaz **ya compilada** que viene en `owner/ui_dist/` — **no
   necesita Node**.
6. Arranca en modo owner y abre en una **ventana de app** (limpia, sin barra
   de navegador, se ve como app de escritorio — usa Chrome o Edge, sin sumar
   el peso de Electron).

El código del programa se queda donde está el .bat; lo que se mueve a la
carpeta elegida es lo que pesa: el entorno (~2 GB), los datos y los archivos
temporales de la instalación.

La primera vez tarda (baja Python + dependencias); las siguientes son
instantáneas. Si Python se instaló recién, quizás tengas que cerrar y reabrir
el .bat una vez (Windows necesita reabrir la consola para tomarlo).

> **Necesitás ~3 GB libres** en el disco que elijas. El .bat mide el espacio
> de **esa** carpeta y avisa antes de empezar.
>
> Esto último tiene historia. Antes el chequeo miraba el disco donde está el
> código y decía, por ejemplo, «~523 GB libres» — pero pip descomprime cada
> paquete en `%TEMP%`, que vive en `C:`. Con `C:` lleno, el chequeo daba OK y
> la instalación se moría igual con `[Errno 28] No space left on device` a
> mitad de bajar plotly: el número que mostraba no era el número que
> importaba. Ahora **todo va al disco que elegís** —entorno, datos y
> temporales de pip—, así que elegir un disco con lugar alcanza para
> resolverlo.

> La interfaz es **React + FastAPI** (la webapp profesional), NO el dashboard
> Streamlit viejo. Ese dashboard clásico sigue en el paquete pero no es lo
> que abre esta vía.

### B) Con el programa ya instalado (MVKobraAI_Setup.exe) → `MVKobraAI_Owner.bat`
Busca el .exe instalado y lo arranca en modo owner. Si no lo encuentra, llama
solo a la vía A. El instalador es el MISMO que el de clientes — lo que cambia
es cómo lo arrancás: con el acceso directo normal pide licencia (modo
cliente); con este .bat entra directo (modo owner).

### C) Linux/Mac → `./mvkobraai_owner.sh`
Mismo tratamiento que A (venv + dependencias + UI compilada), requiere que
Python 3.11+ ya esté disponible.

En los tres casos se abre el navegador solo en `http://localhost:<puerto>`.

> **Mantenimiento de `owner/ui_dist/`**: es un build del frontend versionado
> a propósito, para que la vía A no dependa de Node. Si tocás el frontend
> (`webapp/frontend/src`), regeneralo con:
> `cd webapp/frontend && npm run build && cp -r dist ../../owner/ui_dist`
