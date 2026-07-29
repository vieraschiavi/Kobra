@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Construir instalador (gratis, en esta PC)
cd /d "%~dp0.."

echo ============================================================
echo   MV Kobra AI - CONSTRUIR EL INSTALADOR EN ESTA PC
echo   Genera MVKobraAI_Setup.exe (Electron + React, con
echo   desinstalador) sin usar GitHub Actions ni pagar nada.
echo   Prepara TODO solo: Python, Node, dependencias y compilado.
echo ============================================================
echo.

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
call npx electron-builder --win nsis --publish never
if not exist "dist_installer\MVKobraAI_Setup.exe" (
  popd & echo   Fallo la construccion del instalador. & pause & exit /b 1
)
popd

copy /y "electron\dist_installer\MVKobraAI_Setup.exe" "%USERPROFILE%\Desktop\" >nul 2>nul

echo.
echo ============================================================
echo   LISTO. Instalador generado:
echo.
echo   electron\dist_installer\MVKobraAI_Setup.exe
echo.
echo   (tambien te deje una copia en el Escritorio)
echo.
echo   Ese .exe es el que se le da a los CLIENTES: instala la app
echo   de escritorio con accesos directos a eleccion y desinstalador
echo   en "Agregar o quitar programas".
echo ============================================================
echo.
pause
