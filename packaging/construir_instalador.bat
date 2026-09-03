@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

rem Una sola tuberia de compilacion para las DOS ediciones. Se elige con el
rem primer argumento ("owner" o nada). Antes de esto el instalador del dueno
rem solo lo armaba .github/workflows/release_owner.yml, y con las Actions sin
rem cupo no habia forma de generarlo; duplicar este .bat entero para cambiar
rem tres lineas habria dejado dos tuberias que se separan sola.
rem
rem Lo que cambia entre ediciones:
rem   * el bundle lleva edicion.json firmado (sin el, el .exe pide licencia);
rem   * electron-builder usa electron-builder.owner.yml (appId, nombre y
rem     carpeta propios, para que las dos copias convivan en la misma PC);
rem   * la salida es dist_installer_owner\MVKobraAI_Setup_OWNER.exe.
set "EDICION=cliente"
if /i "%~1"=="owner" set "EDICION=owner"

if "!EDICION!"=="owner" (
  title MV Kobra AI - Construir instalador OWNER (en esta PC)
  echo ============================================================
  echo   MV Kobra AI - CONSTRUIR EL INSTALADOR *OWNER* EN ESTA PC
  echo   Genera MVKobraAI_Setup_OWNER.exe: la copia del dueno,
  echo   sin licencia, sin trial y sin vencimiento.
  echo   Necesita el sello firmado ^(ver KOBRA_OWNER_SELLO abajo^).
  echo ============================================================
) else (
  title MV Kobra AI - Construir instalador (gratis, en esta PC)
  echo ============================================================
  echo   MV Kobra AI - CONSTRUIR EL INSTALADOR EN ESTA PC
  echo   Genera MVKobraAI_Setup.exe ^(Electron + React, con
  echo   desinstalador^) sin usar GitHub Actions ni pagar nada.
  echo   Prepara TODO solo: Python, Node, dependencias y compilado.
  echo ============================================================
)
echo.

rem El sello del dueno es lo unico que separa las dos ediciones, asi que se
rem mira ANTES de compilar nada. La validacion criptografica va mas abajo
rem (necesita las dependencias instaladas); esto de aca solo ataja el olvido,
rem que es el caso comun, en el segundo cero y no a los veinte minutos.
if "!EDICION!"=="owner" (
  if not defined KOBRA_OWNER_SELLO if not defined KOBRA_OWNER_SELLO_ARCHIVO (
    echo   Falta el sello del dueno.
    echo.
    echo   El instalador OWNER lleva un token firmado con tu clave privada.
    echo   Sin el saldria pidiendo licencia igual que el de un cliente, asi
    echo   que este .bat no lo construye a medias.
    echo.
    echo   Si ya lo tenes emitido, antes de correr este .bat:
    echo     set KOBRA_OWNER_SELLO_ARCHIVO=C:\ruta\sello_owner.txt
    echo.
    echo   Si todavia no lo emitiste, una sola vez y en una PC con la privada:
    rem Los parentesis van escapados: sin el ^, cmd los toma como el cierre
    rem del bloque `if (` y el script se rompe justo en el caso que este
    rem mensaje existe para explicar.
    echo     python -c "from backend_venta import licencias as l; print^(l.emitir_sello_owner^(^)^)"
    echo   ^(con KOBRA_LICENSE_PRIVATE_KEY puesta^) y guardas la salida en ese archivo.
    echo.
    pause & exit /b 1
  )
)

rem --- 1) Python: usar el del sistema o instalarlo (igual que el owner) -----
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"

if "!PYEXE!"=="" (
  echo [1/7] Python no encontrado. Descargando e instalando Python 3.11...
  set "PYINST=%TEMP%\python311_kobra.exe"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python311_kobra.exe' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"
  if not !errorlevel!==0 (
    echo.
    echo   No pude descargar Python automaticamente ^(sin internet?^).
    echo   Instalalo a mano desde https://www.python.org/downloads/
    echo   marcando "Add Python to PATH", y volve a ejecutar este .bat.
    echo.
    pause & exit /b 1
  )
  echo       Instalando en silencio ^(solo para tu usuario, sin admin^)...
  "!PYINST!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1
  for %%P in (
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%ProgramFiles%\Python311\python.exe"
  ) do if exist "%%~P" set "PYEXE=%%~P"
  del "!PYINST!" >nul 2>nul
  if "!PYEXE!"=="" (
    echo.
    echo   Python quedo instalado. Cerra esta ventana y volve a hacer doble
    echo   clic en el .bat una vez mas para que Windows lo tome. ^(solo la 1a vez^)
    echo.
    pause & exit /b 0
  )
) else (
  echo [1/7] Python: OK
)

rem --- 2) Node.js 18+: usar el del sistema o bajar uno local (zip, sin admin)
rem     Todo lineal y con expansion retardada (!var!): un %var% que se define
rem     dentro del mismo bloque entre parentesis se expande VACIO al parsear
rem     y rompe el script entero (la ventana "se abre y se cierra").
set "NODEOK="
set "NODEMAJOR="
where node >nul 2>nul
if !errorlevel!==0 (
  for /f "tokens=1 delims=." %%v in ('node -v 2^>nul') do set "NODEMAJOR=%%v"
)
if defined NODEMAJOR set "NODEMAJOR=!NODEMAJOR:v=!"
if defined NODEMAJOR if !NODEMAJOR! GEQ 18 set "NODEOK=1"
if exist ".kobra_node\node.exe" (
  set "PATH=!CD!\.kobra_node;!PATH!"
  set "NODEOK=1"
)
if not "!NODEOK!"=="" (
  echo [2/7] Node.js: OK
  goto :node_listo
)
echo [2/7] Node.js no encontrado. Descargando Node 20 ^(portatil, sin admin^)...
set "NODEZIP=%TEMP%\node20_kobra.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Invoke-WebRequest -Uri 'https://nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip' -OutFile '%TEMP%\node20_kobra.zip' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"
if not !errorlevel!==0 (
  echo.
  echo   No pude descargar Node automaticamente. Instalalo desde
  echo   https://nodejs.org ^(version LTS^) y volve a ejecutar este .bat.
  echo.
  pause & exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -Path '%TEMP%\node20_kobra.zip' -DestinationPath (Join-Path (Get-Location) '.kobra_node_tmp') -Force"
move ".kobra_node_tmp\node-v20.18.1-win-x64" ".kobra_node" >nul
rmdir /s /q ".kobra_node_tmp" >nul 2>nul
del "!NODEZIP!" >nul 2>nul
set "PATH=!CD!\.kobra_node;!PATH!"
:node_listo

rem --- 3) Espacio en disco: dependencias + compilados pesan unos 5 GB -------
rem     findstr /c:"bytes" y no "bytes free": en Windows en espanol la linea
rem     dice "bytes libres" (en portugues "bytes disponiveis") - el numero es
rem     siempre el 3er token de la ultima linea que contiene "bytes".
set "FREEBYTES="
for /f "tokens=3" %%a in ('dir /-c "%CD%" 2^>nul ^| findstr /c:"bytes"') do set "FREEBYTES=%%a"
set "FREEGB="
if defined FREEBYTES set "FREEGB=!FREEBYTES:~0,-9!"
if not defined FREEGB set "FREEGB=SIN_DATO"
if "!FREEGB!"=="" set "FREEGB=0"
if "!FREEGB!"=="SIN_DATO" goto :disco_listo
echo   Espacio libre en disco: ~!FREEGB! GB
if !FREEGB! LSS 6 (
  echo.
  echo   ^(!^) Muy poco espacio libre ^(~!FREEGB! GB^). Construir el instalador
  echo   necesita unos 6 GB libres. Libera espacio y volve a intentar.
  echo.
  pause & exit /b 1
)
:disco_listo

rem --- 4) Dependencias de Python (venv propio, idempotente) -----------------
if not exist ".kobra_venv\Scripts\python.exe" (
  echo [4/7] Creando entorno propio...
  "!PYEXE!" -m venv .kobra_venv
)
set "VPY=.kobra_venv\Scripts\python.exe"
echo [4/7] Instalando dependencias de Python ^(la 1a vez tarda unos minutos^)...
"%VPY%" -m pip install --no-cache-dir --upgrade pip >nul 2>nul
"%VPY%" -m pip install --no-cache-dir -r requirements.txt
if not !errorlevel!==0 (
  echo.
  echo   Fallo la instalacion de dependencias. Revisa conexion/espacio y reintenta.
  echo.
  pause & exit /b 1
)
"%VPY%" -m pip install --no-cache-dir pyinstaller==6.11.1
if not !errorlevel!==0 ( echo   Fallo instalando PyInstaller. & pause & exit /b 1 )

rem Ahora si se puede VALIDAR el sello (hace falta PyJWT, recien instalado).
rem Un token cortado al copiar produce un edicion.json de aspecto perfecto que
rem el programa rechaza al arrancar: el .exe saldria pidiendo licencia despues
rem de veinte minutos de compilacion. Se comprueba con el mismo codigo que
rem corre en el arranque, y aca todavia no se compilo nada.
if "!EDICION!"=="owner" (
  echo [4/7] Verificando el sello del dueno...
  "%VPY%" packaging\sellar_bundle_owner.py --solo-verificar
  if not !errorlevel!==0 ( echo. & pause & exit /b 1 )
)

rem --- 5) Datos de demo + interfaz React ------------------------------------
echo [5/7] Generando datos de demo y compilando la interfaz...
"%VPY%" -m kobra.pipeline
if not !errorlevel!==0 ( echo   Fallo generando la demo. & pause & exit /b 1 )
pushd webapp\frontend
call npm ci --no-audit --no-fund
if not !errorlevel!==0 ( popd & echo   Fallo npm ci del frontend. & pause & exit /b 1 )
call npm run build
if not !errorlevel!==0 ( popd & echo   Fallo el build del frontend. & pause & exit /b 1 )
popd

rem --- 6) Motor empaquetado (PyInstaller) ------------------------------------
echo [6/7] Empaquetando el motor ^(PyInstaller, tarda varios minutos^)...
"%VPY%" -m PyInstaller packaging\kobra.spec --noconfirm --clean
if not exist "dist\MVKobraAI\MVKobraAI.exe" (
  echo   Fallo el empaquetado del motor ^(no aparecio dist\MVKobraAI^).
  pause & exit /b 1
)

rem El sello va DENTRO del bundle, antes de que electron-builder lo copie a
rem resources\backend: asi el .exe nace owner en vez de quedar convertible.
rem Es el mismo paso que hace el workflow release_owner.yml, y el script
rem relee lo que escribio para que un "listo" no sea de mentira.
if "!EDICION!"=="owner" (
  echo       Sellando el motor como edicion OWNER...
  "%VPY%" packaging\sellar_bundle_owner.py --bundle dist\MVKobraAI
  if not !errorlevel!==0 ( echo. & pause & exit /b 1 )
)

rem --- 7) Instalador Electron (NSIS con desinstalador) -----------------------
echo [7/7] Construyendo el instalador ^(electron-builder^)...
rem VPY es ruta relativa sin espacios: va SIN comillas a proposito - con mas
rem de dos comillas en el comando, el for /f las recorta y lo rompe.
for /f "delims=" %%v in ('%VPY% -c "import kobra;print(kobra.__version__)"') do set "KVER=%%v"
if not defined KVER (
  echo   No pude leer la version del paquete. & pause & exit /b 1
)
rem --- Piezas de marca y licencias del asistente -------------------------
rem Sin esto el instalador sale con las imagenes genericas de electron-builder
rem y sin pantalla de terminos. Se regeneran siempre: son deterministas.
echo [6/7] Generando marca y licencias del instalador...
"!PYEXE!" packaging/licencias_instalador.py
if not !errorlevel!==0 echo   (aviso) No pude regenerar las licencias; uso las que ya estaban.

pushd electron
call npm pkg set version=!KVER!
call npm ci --no-audit --no-fund
if not !errorlevel!==0 ( popd & echo   Fallo npm ci de electron. & pause & exit /b 1 )
set "CSC_IDENTITY_AUTO_DISCOVERY=false"
rem Identidad propia para el owner: mismo appId significaria misma entrada en
rem "Agregar o quitar programas", misma carpeta y mismos accesos directos, o
rem sea que instalar el owner PISARIA la copia de cliente. Con el config
rem aparte las dos conviven, que es lo que hace falta para ver que ve un
rem comprador sin perder la propia.
if "!EDICION!"=="owner" (
  call npx electron-builder --win nsis --config electron-builder.owner.yml --publish never
  set "SALIDA=dist_installer_owner\MVKobraAI_Setup_OWNER.exe"
) else (
  call npx electron-builder --win nsis --publish never
  set "SALIDA=dist_installer\MVKobraAI_Setup.exe"
)
if not exist "!SALIDA!" (
  popd & echo   Fallo la construccion del instalador. & pause & exit /b 1
)
popd

copy /y "electron\!SALIDA!" "%USERPROFILE%\Desktop\" >nul 2>nul

echo.
echo ============================================================
echo   LISTO. Instalador generado:
echo.
echo   electron\!SALIDA!
echo.
echo   ^(tambien te deje una copia en el Escritorio^)
echo.
if "!EDICION!"=="owner" (
  echo   Ese .exe es TUYO, no se le da a nadie: entra directo, sin
  echo   licencia, sin trial y sin vencimiento. Se instala aparte del
  echo   de clientes ^(otro nombre y otra carpeta^), asi que podes tener
  echo   las dos copias en la misma PC y ver que ve un comprador.
  echo.
  echo   NO lo subas a mv-kobra-ai-releases: ese repo es publico y
  echo   esta version no pide licencia.
) else (
  echo   Ese .exe es el que se le da a los CLIENTES: instala la app
  echo   de escritorio con accesos directos a eleccion y desinstalador
  echo   en "Agregar o quitar programas".
)
echo ============================================================
echo.
pause
