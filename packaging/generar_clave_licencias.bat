@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Generar clave de licencias
cd /d "%~dp0.."

echo ============================================================
echo   MV Kobra AI - CLAVE DE FIRMA DE LICENCIAS
echo.
echo   Genera el par de claves con el que el servidor de ventas
echo   firma las licencias y el programa instalado las valida.
echo   Es UNA SOLA VEZ, para siempre - no hace falta correrlo de
echo   nuevo en cada venta.
echo ============================================================
echo.
echo   OJO antes de seguir: si ya vendiste algo, esa venta se
echo   firmo con el par ACTUAL (el que ya esta en el repo). Correr
echo   esto de nuevo genera un par DISTINTO e invalida esa
echo   licencia. Si no estas seguro, cancela con Ctrl+C.
echo.
pause

rem --- Python: usar el del sistema o instalarlo (mismo patron que
rem     construir_instalador.bat, para no repetir logica ya probada) -------
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"

if "!PYEXE!"=="" (
  echo [1/3] Python no encontrado. Descargando e instalando Python 3.11...
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
    echo   clic en este .bat una vez mas para que Windows lo tome.
    echo.
    pause & exit /b 0
  )
) else (
  echo [1/3] Python: OK
)

echo [2/3] Verificando la libreria de firma (cryptography)...
"!PYEXE!" -c "import cryptography" >nul 2>nul
if not !errorlevel!==0 (
  echo       Instalandola ^(una vez sola^)...
  "!PYEXE!" -m pip install --quiet cryptography>=42.0
)

echo [3/3] Generando el par nuevo...
echo.
set "SALIDA=%TEMP%\kobra_clave_licencias.txt"
"!PYEXE!" -m backend_venta.licencia_clave --nuevo-par > "!SALIDA!" 2>&1
if not !errorlevel!==0 (
  echo   Algo fallo generando la clave. Mensaje completo:
  echo.
  type "!SALIDA!"
  echo.
  pause & exit /b 1
)

echo ============================================================
echo   LISTO. Se abre un bloc de notas con las dos claves.
echo.
echo   1. Copia el bloque PRIVADA completo ^(incluidas las lineas
echo      -----BEGIN/END-----^) y pegalo en Vercel, proyecto kobra,
echo      Settings -^> Environment Variables, en:
echo         KOBRA_LICENSE_PRIVATE_KEY
echo      Nunca la guardes en un archivo de este repositorio.
echo.
echo   2. Copia el bloque PUBLICA y reemplaza con eso la constante
echo      PUBLICA de backend_venta\licencia_clave.py (ese archivo
echo      SI se sube al repo - la publica no es secreta).
echo ============================================================
echo.
notepad "!SALIDA!"
pause
