# 📦 Distribución del instalador de Windows a clientes finales

## Construirlo GRATIS en tu propia PC (sin GitHub Actions)

Si la cuota gratuita de minutos de GitHub Actions está agotada (se renueva el
día 1 de cada mes) y no querés pagar, el instalador se construye igual, gratis,
en cualquier PC con Windows:

1. Bajá/actualizá el código del repo en tu PC (o usá la carpeta que ya tenés).
2. Doble clic en **`packaging\construir_instalador.bat`**.
3. El script prepara todo solo (Python, Node portátil, dependencias, interfaz,
   motor) y al final deja **`MVKobraAI_Setup_vX.Y.Z.exe`** en
   `electron\dist_installer\` **y una copia en tu Escritorio**.

La primera vez tarda un buen rato (descarga ~2 GB de dependencias y compila
todo); las siguientes son mucho más rápidas porque reusa lo ya instalado.
Necesita ~6 GB de disco libres e internet. El `.exe` resultante es idéntico al
que generaría GitHub Actions: la app Electron con desinstalador incluido.

## Y el instalador OWNER (el tuyo, sin licencia)

Misma tubería, un argumento distinto:

1. **Una sola vez**, dejá a mano el sello firmado del dueño. Se emite en una
   PC que tenga la privada (`KOBRA_LICENSE_PRIVATE_KEY`):

   ```
   python -c "from backend_venta import licencias as l; print(l.emitir_sello_owner())"
   ```

   Guardá esa salida en un archivo **fuera del repo** y apuntalo:

   ```
   setx KOBRA_OWNER_SELLO_ARCHIVO C:\ruta\sello_owner.txt
   ```

2. Doble clic en **`packaging\construir_instalador_owner.bat`**.
3. Sale **`MVKobraAI_Setup_OWNER.exe`** en `electron\dist_installer_owner\`
   (y una copia en el Escritorio).

Esa copia **entra directo: sin licencia, sin trial y sin vencimiento**. Se
instala con nombre y carpeta propios (`MV Kobra AI Owner`), así que convive
con la copia de cliente en la misma máquina — que es lo que hace falta para
ver qué ve un comprador sin perder la tuya.

Sin el sello el `.bat` **no construye nada**: avisa en el segundo cero, no
después de veinte minutos. Y si el token está cortado, lo detecta antes de
compilar, porque lo valida con el mismo código que corre al arrancar el
programa.

> **Nunca** subas este `.exe` a `mv-kobra-ai-releases`: ese repo es público y
> esta edición no pide licencia. Publicarla ahí es regalar el producto.

Si el programa **ya está instalado** y solo querés sacarle las trabas, no hace
falta recompilar: generá `packaging\Owner.bat` (con `KOBRA_OWNER_SELLO` puesta,
`python packaging/generar_owner_bat.py`), copialo a la carpeta del programa y
doble clic.

## El problema que resuelve esto

Este repo (`vieraschiavi/Kobra`) es **privado**. El instalador de Windows
(`MVKobraAI_Setup.exe`) se construye solo con GitHub Actions y queda publicado
en la sección **Releases** de este mismo repo — pero un cliente que compró el
plan Starter/Pro **no tiene acceso a este repo**, así que ese link de descarga
le da error (o le pide loguearse) aunque el archivo exista.

**La solución:** un segundo repositorio, **público**, que solo recibe el
`.exe` ya compilado en cada build — nunca el código fuente. El workflow
(`.github/workflows/build_windows.yml`) ya está listo para publicar ahí
automáticamente; falta un paso manual único de configuración de tu parte.

## Pasos (una sola vez)

1. **Creá el repositorio público** en tu cuenta de GitHub:
   - Nombre: `mv-kobra-ai-releases` (o el que prefieras — si usás otro nombre,
     avisame para actualizar el workflow y `landing/descarga.html`).
   - Visibilidad: **Public**.
   - No hace falta inicializarlo con nada — el workflow crea el primer
     release solo.

2. **Creá un token de acceso** con permiso para publicar releases ahí:
   - Preferible: un **fine-grained personal access token**
     (`Settings → Developer settings → Personal access tokens → Fine-grained
     tokens`), con acceso **solo** al repo `mv-kobra-ai-releases`, y permiso
     **Contents: Read and write** (eso alcanza para crear releases y subir
     archivos). Así el token no puede tocar nada de tu repo privado ni de
     ningún otro.

3. **Agregá el token como secret en ESTE repo** (`vieraschiavi/Kobra`):
   - `Settings → Secrets and variables → Actions → New repository secret`.
   - Nombre exacto: `RELEASES_TOKEN`.
   - Valor: el token que generaste en el paso 2.

4. Listo — el próximo push a `main` (o el próximo tag `vX.Y.Z`) va a:
   - Seguir publicando en este repo privado (como ya hacía, sin cambios).
   - **Además** publicar una copia en `mv-kobra-ai-releases`, con el nombre
     estable `MVKobraAI_Setup.exe` (sin número de versión), para que el link
     de la landing (`.../releases/latest/download/MVKobraAI_Setup.exe`)
     **nunca necesite actualizarse** en futuras versiones.

Si el secret `RELEASES_TOKEN` no está configurado, ese paso del workflow se
salta solo (no rompe el build ni la Release del repo privado) — simplemente
el instalador seguirá sin estar accesible para clientes hasta que lo
configures.

## Por qué no alcanza con hacer público este repo directamente

Se evaluó y se descartó a propósito: este repo tiene todo el código fuente
del producto (`kobra/`, `webapp/`, prompts, lógica de negociación). Hacerlo
público expondría esa propiedad intelectual completa a cualquiera — ver
`docs/GUIA_REGISTRO_LEGAL_URUGUAY.md` sobre por qué eso importa. El repo
separado de releases resuelve la descarga pública sin ese costo.
