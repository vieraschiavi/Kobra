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
  echo [1/4] Python no encontrado. Descargando e instalando Python 3.11...
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

rem --- 2) Entorno virtual propio (no toca el Python del sistema) ------------
if not exist ".kobra_venv\Scripts\python.exe" (
  echo [2/4] Creando entorno propio...
  "!PYEXE!" -m venv .kobra_venv
)
set "VPY=.kobra_venv\Scripts\python.exe"

rem --- 3) Dependencias (idempotente: la 2a vez es casi instantanea) ---------
echo [3/4] Instalando dependencias ^(la 1a vez tarda unos minutos^)...
"%VPY%" -m pip install --upgrade pip >nul 2>nul
"%VPY%" -m pip install -r requirements.txt
if not !errorlevel!==0 (
  echo   Fallo la instalacion. Revisa tu conexion y reintenta.
  pause & exit /b 1
)

rem --- 4) Arranque en modo OWNER (React + FastAPI, UI ya compilada) ---------
echo [4/4] Iniciando MV Kobra AI...
echo.
set KOBRA_OWNER=1
set KOBRA_UI_DIST=%CD%\owner\ui_dist
set KOBRA_APP_WINDOW=1
"%VPY%" packaging\kobra_launcher.py
pause
