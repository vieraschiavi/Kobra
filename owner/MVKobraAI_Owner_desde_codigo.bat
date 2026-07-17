@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - OWNER (instalacion automatica)
cd /d "%~dp0.."

echo ============================================================
echo   MV Kobra AI - Version OWNER
echo   Prepara TODO solo: Python, dependencias e interfaz.
echo   No necesitas instalar ni configurar nada a mano.
echo ============================================================
echo.

rem --- 1) Python: usar el del sistema, o el venv ya armado, o instalarlo ----
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"

if "!PYEXE!"=="" (
  echo [1/5] Python no encontrado. Descargando e instalando Python 3.11...
  echo       (usa PowerShell, incluido en Windows - no requiere winget)
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
  rem El PATH nuevo no aplica a esta consola: buscar el python recien puesto.
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
)

rem --- 2) Espacio en disco: las dependencias pesan ~1.5-2 GB descargadas ----
rem     Chequeo best-effort con comandos nativos (dir + findstr). Lineal y
rem     con expansion retardada (!var!): un %var% definido dentro del mismo
rem     bloque entre parentesis se expande VACIO al parsear y el "if" roto
rem     aborta el .bat entero (la ventana "se abre y se cierra").
rem     findstr /c:"bytes" y no "bytes free": en Windows en espanol la linea
rem     dice "bytes libres" - el numero es siempre el 3er token.
set "FREEBYTES="
for /f "tokens=3" %%a in ('dir /-c "%CD%" 2^>nul ^| findstr /c:"bytes"') do set "FREEBYTES=%%a"
set "FREEGB="
if defined FREEBYTES set "FREEGB=!FREEBYTES:~0,-9!"
if not defined FREEGB set "FREEGB=SIN_DATO"
if "!FREEGB!"=="" set "FREEGB=0"
if "!FREEGB!"=="SIN_DATO" goto :disco_listo
echo   Espacio libre en disco: ~!FREEGB! GB
if !FREEGB! LSS 3 (
  echo.
  echo   ^(!^) Muy poco espacio libre ^(~!FREEGB! GB^). Las dependencias
  echo   necesitan unos 3 GB libres para descargarse e instalarse bien.
  echo   Libera espacio ^(o move esta carpeta a un disco con mas lugar^)
  echo   y volve a ejecutar este .bat.
  echo.
  pause & exit /b 1
)
:disco_listo

rem --- 3) Entorno virtual propio (no toca el Python del sistema) ------------
if not exist ".kobra_venv\Scripts\python.exe" (
  echo [3/5] Creando entorno propio...
  "!PYEXE!" -m venv .kobra_venv
)
set "VPY=.kobra_venv\Scripts\python.exe"

rem --- 4) Dependencias (idempotente: la 2a vez es casi instantanea) ---------
rem     --no-cache-dir: no guarda una copia extra de cada .whl descargado,
rem     usa bastante menos disco durante la instalacion.
echo [4/5] Instalando dependencias ^(la 1a vez tarda unos minutos^)...
"%VPY%" -m pip install --no-cache-dir --upgrade pip >nul 2>nul
"%VPY%" -m pip install --no-cache-dir -r requirements.txt
if not !errorlevel!==0 (
  echo.
  echo   Fallo la instalacion. Si el error dice "No space left on device" o
  echo   similar, libera espacio en disco y volve a intentar - lo que ya se
  echo   instalo no hace falta bajarlo de nuevo.
  echo   Si es otro error, revisa tu conexion y reintenta.
  echo.
  pause & exit /b 1
)

rem --- 5) Arranque en modo OWNER (React + FastAPI, UI ya compilada) ---------
echo [5/5] Iniciando MV Kobra AI...
echo.
set KOBRA_OWNER=1
set KOBRA_UI_DIST=%CD%\owner\ui_dist
set KOBRA_APP_WINDOW=1
"%VPY%" packaging\kobra_launcher.py
pause
