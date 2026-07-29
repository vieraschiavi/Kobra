# Instalador de Windows

`MVKobraAI_Setup.exe` — instalador NSIS con asistente, elección de carpeta y
desinstalador registrado en «Agregar o quitar programas».

## Qué ve el cliente

1. **Selector de idioma** — español, portugués o inglés.
2. **Licencia (EULA)** — hay que aceptarla para continuar.
3. **Para quién se instala** — todos los usuarios (pide permisos de
   administrador, va a `C:\Archivos de programa`) o solo el usuario actual (sin
   permisos, va a `%LOCALAPPDATA%`).
4. **Carpeta de instalación** — editable, con botón «Examinar».
5. **Accesos directos** — Escritorio y Menú Inicio, a elección, con casillas.
6. **Instalación** y opción de abrir el programa al terminar.

Al desinstalar, los datos del usuario **no** se borran
(`deleteAppDataOnUninstall: false`): quien reinstala no pierde su configuración.

## Construirlo

### En una PC con Windows (no necesita GitHub Actions)

```
packaging\construir_instalador.bat
```

Instala solo lo que falte —Python, Node, dependencias—, compila el motor con
PyInstaller y la app React, regenera las licencias y arma el `.exe`. Deja una
copia en el Escritorio.

Es el camino recomendado hoy: el workflow de Actions solo corre en `main` y en
tags, y los minutos de Windows facturan al doble.

### En GitHub Actions

`.github/workflows/build_windows.yml`, en `main` o al taguear `vX.Y.Z`. Publica
el `.exe` en la Release de este repo y, si está el secret `RELEASES_TOKEN`, una
copia en el repo público de descargas (ver `DISTRIBUCION_INSTALADOR.md`).

## El nombre del archivo tiene que quedarse quieto

La landing descarga desde:

```
https://github.com/vieraschiavi/mv-kobra-ai-releases/releases/latest/download/MVKobraAI_Setup.exe
```

Ese enlace pide un **nombre fijo**. Cuando el artefacto se llamaba
`MVKobraAI_Setup_v1.3.0.exe`, el enlace daba **404** — el producto quedaba sin
instalador descargable sin que nadie se enterara. Por eso `artifactName` es
`MVKobraAI_Setup.exe`, sin versión: la versión va en el tag de la release, en
las propiedades del `.exe` y en el propio asistente.

`tests/test_instalador_windows.py` verifica que el nombre del artefacto, el que
busca el workflow y el que pide la landing sigan siendo el mismo.

## Piezas del asistente

| Archivo | Qué es | Cómo se regenera |
|---|---|---|
| `electron/build/icon.ico` | Icono del programa | a mano |
| `electron/build/installerSidebar.bmp` | Franja lateral (164×314) | `python3 -m marketing.instalador_marca` |
| `electron/build/installerHeader.bmp` | Banda superior (150×57) | ídem |
| `electron/build/license_{es,pt,en}.txt` | EULA por idioma | `python3 packaging/licencias_instalador.py` |
| `electron/build/installer.nsh` | Página de accesos directos | a mano |

Las imágenes **tienen que ser BMP** del tamaño exacto: NSIS no escala, recorta,
y un PNG renombrado hace fallar la compilación. Las licencias van en CRLF y con
BOM: el visor de NSIS es un RichEdit de Windows y con saltos de línea de Unix
muestra todo en un solo renglón.

## Lo que falta para un producto comercial pleno

**Firma de código.** Sin certificado, Windows SmartScreen muestra «Windows
protegió su PC» y el cliente tiene que entrar en «Más información → Ejecutar de
todas formas». Es la diferencia más visible que queda contra un instalador
comercial, y no se arregla con configuración: hay que comprar un certificado de
firma (OV o EV) y cargarlo como secret. El build ya corre con
`CSC_IDENTITY_AUTO_DISCOVERY=false` para no fallar buscándolo.
