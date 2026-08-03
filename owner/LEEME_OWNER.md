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

Verificado levantando la misma app dos veces, owner y cliente, y golpeando
cada endpoint: **el owner llega a los 27/27**, la entrada directa responde 200
y la licencia informa `plan: owner` sin días. La copia de un cliente sin
licencia llega a 3/27 y esa misma entrada le devuelve 404. No queda ninguna
puerta cerrada del lado del dueño (`tests/test_owner_sin_restricciones.py`).
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

### 0) El instalador de Windows (`MVKobraAI_Setup.exe`) — lo más profesional

Es la vía recomendada y la que ve un cliente. **Asistente gráfico**, no consola:

```
https://github.com/vieraschiavi/Kobra/releases/latest   →   MVKobraAI_Setup.exe
```

| Trae | Detalle |
|---|---|
| Asistente en español/portugués/inglés | Selector de idioma, licencia, barra lateral con la marca |
| **Elección de carpeta y disco** | Página con botón **Examinar**: podés instalarlo en `D:\` |
| Iconos | Página propia con checkboxes: Escritorio y/o Menú Inicio |
| Desinstalador | Registrado en «Agregar o quitar programas» |
| Sin dependencias | **No necesita Python**: el motor va empaquetado con PyInstaller |

Lo construye solo el workflow `build-windows-installer` (Electron + NSIS vía
electron-builder) en cada push a `main` y en cada tag `vX.Y.Z`.

> Doble clic en `MVKobraAI_Owner.bat` abre el programa si ya está instalado; si
> no, ofrece **este** instalador como opción 1 y deja la instalación por
> consola como opción 2. Antes caía a la consola sin preguntar, y esa vía
> —preguntas por texto, descarga de Python, minutos de `pip`— terminaba siendo
> la cara del producto existiendo este asistente.

### 1) El ZIP de la edición Owner (para correr desde el código)

La edición Owner se publica como release **de este repositorio privado**:

```
https://github.com/vieraschiavi/Kobra/releases   →   MVKobraAI_Owner_vX.Y.Z.zip
```

Descomprimís y tenés dos opciones:

| Archivo | Qué hace |
|---|---|
| `INSTALAR.bat` | Deja el programa **instalado**: icono propio, acceso en el Escritorio, entrada en el Menú Inicio y desinstalador en «Agregar o quitar programas». No pide administrador. |
| `INICIAR_OWNER.bat` | Lo abre sin instalar nada. |

Al desinstalar, tus datos **no** se borran salvo que lo pidas expresamente.

Para generar el ZIP vos mismo (o publicar una versión nueva):

```
python packaging/build_release.py --edicion Owner     # queda en dist/
```

Y para publicarlo: Actions → **Release Owner** → Run workflow, o taguear
`owner-vX.Y.Z`.

> **Nunca en el repo público de descargas.** `mv-kobra-ai-releases` es público y
> es donde va el instalador de clientes. Esta edición arranca sin licencia y sin
> vencimiento: publicarla ahí sería regalar el producto completo. Por eso el
> workflow escribe solo en las releases de este repo privado y con
> `make_latest: false`, para no robarle el enlace `latest` al instalador de
> clientes.

### A) Desde el código, sin instalar NADA a mano → doble clic en `MVKobraAI_Owner_desde_codigo.bat`
**Esta es la vía recomendada si no tenés el instalador.** El .bat prepara
todo solo, sin que instales nada previo:
1. **Te pregunta dónde instalar** (Enter usa la sugerida; podés escribir
   cualquier ruta, por ejemplo `D:\MVKobraAI`). Ahí van Python, el entorno y
   tus datos. La elección se recuerda: la próxima vez alcanza con dar Enter.
2. **Mide el espacio libre de esa carpeta** y frena antes de empezar si no
   entra.
3. Si falta Python 3.11+, lo **descarga del sitio oficial e instala en
   silencio** usando PowerShell (incluido en todo Windows — **no depende de
   winget**). Se baja **y se instala** al disco que elegiste — no a `%TEMP%`
   ni a `%LocalAppData%`, que es donde el instalador de python.org lo pondría
   por defecto (siempre en `C:`, aunque hayas elegido otro disco para todo lo
   demás).
4. Crea un entorno virtual propio en esa carpeta (no toca tu Python).
5. Instala las dependencias (`requirements.txt`). Usa la interfaz **ya
   compilada** de `owner/ui_dist/` — **no necesita Node**.
6. **Deja el programa instalado**: icono propio, acceso directo en el
   Escritorio, entrada en el Menú Inicio y desinstalador en «Agregar o quitar
   programas». Todo en tu perfil de usuario y en `HKCU`, así que no pide
   permisos de administrador.
7. Arranca en modo owner y abre en una **ventana de app** (limpia, sin barra
   de navegador, se ve como app de escritorio — usa Chrome o Edge, sin sumar
   el peso de Electron). El puerto se elige **libre**: si otra aplicación ya
   usa el habitual, se pasa al siguiente en vez de pisarla.

> **Los pasos 1 y 2 van antes del 3 a propósito.** Antes Python se descargaba
> primero, a `%TEMP%` (que vive en `C:`). Con `C:` lleno la descarga fallaba
> por espacio y el .bat lo reportaba como **«No pude descargar Python (¿sin
> internet?)»** — a veces justo después de un «Espacio en disco insuficiente»,
> dos mensajes que se contradecían. Ahora primero elegís el disco, se mide, y
> todo lo que se baja va ahí; si aun así falla, se imprime el error real de
> PowerShell y se nombran las dos causas posibles.

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
