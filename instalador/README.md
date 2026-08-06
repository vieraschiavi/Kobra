# 📦 MV Kobra AI · Instalador de Windows

Todo lo necesario para instalar MV Kobra AI como **programa de escritorio**.

## Bajarlo

| Cómo | Qué hacés |
|---|---|
| **Automático** | Doble clic en `DESCARGAR_INSTALADOR.bat` — lo baja acá al lado y te muestra el SHA256 para verificar |
| **A mano** | [github.com/vieraschiavi/Kobra/releases/latest](https://github.com/vieraschiavi/Kobra/releases/latest) → `MVKobraAI_Setup.exe` |

> **Por qué el `.exe` no está commiteado en esta carpeta.** GitHub rechaza
> archivos de más de 100 MB dentro de un repositorio, y el instalador pesa
> ~267 MB. Git LFS lo permitiría, pero su cuota gratis (1 GB/mes de tráfico) se
> agota en tres descargas y después se factura. El binario vive en **Releases**,
> que es el lugar de GitHub hecho exactamente para esto y no tiene ese límite.
> Esta carpeta es el atajo hacia allá.

## Qué instala

Un **programa de escritorio de verdad**, no una página web ni una consola:

- **Ventana propia de aplicación** (Electron), con su ícono, su barra de tareas
  y su entrada en el Menú Inicio. No abre el navegador.
- **Motor embebido**: React + FastAPI empaquetados con PyInstaller.
  **No necesita Python** ni instalar nada previo.
- **No es Streamlit.** El `.exe` arranca `kobra_launcher.py`, que levanta
  `webapp.backend.api` (FastAPI) y sirve el build de React. El dashboard
  Streamlit sigue existiendo en el repo para uso interno, pero no es lo que
  abre este instalador.
- **Puerto sin conflictos**: el puerto lo pide al sistema operativo
  (`listen(0)`), que devuelve uno libre de su rango dinámico. Por definición no
  puede darte uno que ya esté ocupado por otra aplicación.

## Instalar

1. Ejecutá `MVKobraAI_Setup.exe`.
2. El asistente te deja **elegir carpeta y disco** con el botón **Examinar**
   (por ejemplo `D:\MVKobraAI`, si `C:` está justo de espacio).
3. Marcá si querés acceso directo en el **Escritorio** y en el **Menú Inicio**.
4. Al terminar, el programa abre solo.

Queda registrado en **«Agregar o quitar programas»** con su desinstalador.
Al desinstalar, tus datos **no** se borran salvo que lo pidas expresamente.

## Dos instaladores, y para qué sirve cada uno

| Instalador | Dónde | Quién lo usa | Cómo entra |
|---|---|---|---|
| `MVKobraAI_Setup.exe` | [Releases](https://github.com/vieraschiavi/Kobra/releases/latest) (y el repo público de descargas) | Clientes **y el dueño** | Cliente: token de licencia. Dueño: su credencial `mail\|código` |
| `MVKobraAI_Setup_OWNER.exe` | Release `owner-vX.Y.Z`, **solo en este repo privado** | Solo el dueño | Entra directo, sin licencia ni activación |

**Conviven en la misma PC.** Tienen `appId`, nombre, carpeta y accesos
distintos, así que instalar uno no pisa al otro. Eso es a propósito: te deja
tener tu copia de trabajo y, al lado, una copia de cliente para ver
exactamente qué recibe quien paga.

### Cuál usar

- **Para trabajar**: el `_OWNER.exe`. Abre y ya está, sin escribir nada.
- **Para probar qué ve un comprador**: el normal, con un token de licencia de
  prueba. Es el mismo binario que se publica, así que lo que ves es lo que
  recibe el cliente — bit a bit.

> **El `_OWNER.exe` no se redistribuye.** Arranca sin licencia y sin
> vencimiento: quien lo tenga usa el producto completo sin pagar. Por eso se
> publica únicamente en las releases de este repositorio **privado**, con tag
> `owner-vX.Y.Z` y nunca marcado como `latest` — el enlace
> `/releases/latest/download/` tiene que seguir sirviendo el instalador de
> clientes.

### Cómo se construye

`Actions → Release Owner → Run workflow` (o taguear `owner-vX.Y.Z`). El job
`instalador` usa el mismo pipeline que el de clientes y, antes de publicar,
verifica dos cosas que fallarían en silencio:

1. Que `edicion.json` con `owner: true` **entró al bundle**. Si no viajó, el
   instalador "Owner" pediría licencia como el de un cliente: el mismo
   producto con otro nombre.
2. Que el motor **arranca en modo owner** — no alcanza con que responda 200:
   `/api/licencia/estado` tiene que devolver `owner: true`.

## Cómo se construye y se verifica

Lo arma el workflow `build-windows-installer` en cada push a `main` y en cada
tag `vX.Y.Z`:

1. PyInstaller empaqueta el motor → `dist/MVKobraAI/MVKobraAI.exe`
2. **Prueba de humo**: se *ejecuta* ese motor y se le pega a
   `/api/licencia/estado`. Si no responde 200, el build falla y **no se publica
   nada**.
3. electron-builder arma el instalador NSIS con asistente, iconos y
   desinstalador.

> El paso 2 existe por un bug real: `packaging/kobra.spec` listaba a mano los
> módulos de `kobra/` y la lista se desfasó. Faltaban `kobra.owner` y
> `kobra.limitador`, que el backend importa al arrancar. El instalador se
> construía y publicaba sin problema — el archivo existía — pero al abrirlo el
> motor moría en silencio y la ventana quedaba en el splash hasta que Electron
> cortaba a los 120 s. Ahora los módulos se enumeran del paquete, y el CI
> ejecuta el motor antes de publicar.

## Si algo falla

| Síntoma | Qué mirar |
|---|---|
| La ventana se queda en el splash y sale «El motor no respondió a tiempo» | El bundle está roto. Fijate si el último `build-windows-installer` pasó la prueba de humo |
| No arranca nada al hacer clic | Probá desde `%LocalAppData%\Programs\MV Kobra AI\` (o la carpeta que elegiste) ejecutando `MV Kobra AI.exe` directo |
| Dice que la licencia es inválida | Copiá el token completo, sin espacios de más |
