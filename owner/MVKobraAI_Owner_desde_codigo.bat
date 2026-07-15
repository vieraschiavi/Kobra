@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - OWNER (instalacion automatica)
cd /d "%~dp0.."

echo ============================================================
echo   MV Kobra AI - Version OWNER (arranque desde codigo)
echo   Prepara todo solo: Python, dependencias e interfaz.
echo   No necesitas instalar nada a mano.
echo ============================================================
echo.

rem --- 1) Python: si no esta, instalarlo con winget (Win10/11) --------------
set "PYEXE=python"
where python >nul 2>nul
if not %errorlevel%==0 (
  echo [1/4] Python no encontrado. Instalando Python 3.11...
  where winget >nul 2>nul
  if not %errorlevel%==0 (
    echo.
    echo   No tengo winget para instalar Python automaticamente.
    echo   Instala Python 3.11+ desde https://www.python.org/downloads/
    echo   ^(marca "Add Python to PATH" al instalar^) y volve a ejecutar este .bat.
    echo.
    pause & exit /b 1
  )
  winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
  rem winget no refresca el PATH de esta consola: buscar el python recien instalado
  set "PYEXE="
  for %%P in ("%LocalAppData%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python311\python.exe") do (
    if exist "%%~P" set "PYEXE=%%~P"
  )
  if "!PYEXE!"=="" (
    echo.
    echo   Python quedo instalado pero hay que reabrir esta ventana para que
    echo   Windows lo tome. Cerra este .bat y volve a ejecutarlo. ^(una sola vez^)
    echo.
    pause & exit /b 0
  )
) else (
  echo [1/4] Python detectado.
)

rem --- 2) Entorno virtual propio (no ensucia el Python del sistema) ---------
if not exist ".kobra_venv\Scripts\python.exe" (
  echo [2/4] Creando entorno virtual...
  "!PYEXE!" -m venv .kobra_venv
)
set "VPY=.kobra_venv\Scripts\python.exe"

rem --- 3) Dependencias (idempotente: si ya estan, es casi instantaneo) ------
echo [3/4] Instalando/verificando dependencias ^(puede tardar la 1a vez^)...
"%VPY%" -m pip install --upgrade pip >nul 2>nul
"%VPY%" -m pip install -r requirements.txt
if not %errorlevel%==0 (
  echo   Fallo la instalacion de dependencias. Revisa tu conexion y reintenta.
  pause & exit /b 1
)

rem --- 4) Arranque en modo OWNER (usa la UI ya compilada en owner\ui_dist) ---
echo [4/4] Iniciando MV Kobra AI (modo OWNER)...
echo.
set KOBRA_OWNER=1
set KOBRA_UI_DIST=%CD%\owner\ui_dist
"%VPY%" packaging\kobra_launcher.py
pause
