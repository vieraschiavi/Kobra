@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - OWNER (instalacion automatica)
cd /d "%~dp0.."
set "CODIGO=%CD%"

echo ============================================================
echo   MV Kobra AI - Version OWNER
echo   Prepara TODO solo: Python, dependencias e interfaz.
echo   No necesitas instalar ni configurar nada a mano.
echo ============================================================
echo.

rem =========================================================================
rem  ORDEN DE LOS PASOS: primero la carpeta, despues el disco, y RECIEN AHI
rem  se descarga nada.
rem
rem  Antes Python se bajaba en el paso 1, a %TEMP% — que vive en C:. Con C:
rem  lleno la descarga fallaba y el script culpaba a la red ("sin internet?"),
rem  cuando el problema era espacio. El usuario veia "Espacio en disco
rem  insuficiente" y acto seguido "no pude descargar Python (sin internet?)":
rem  dos mensajes que se contradicen y ninguno accionable.
rem
rem  Ahora la carpeta se elige antes que nada, el espacio se mide sobre ESA
rem  carpeta, y todo lo que se descarga (instalador de Python incluido) va al
rem  disco elegido. Asi "elegi otro disco" resuelve de verdad.
rem =========================================================================

rem --- 1) Donde instalar (el usuario elige) ---------------------------------
rem     Aca van el entorno (~2 GB), los datos y los temporales, asi que la
rem     carpeta la elige el usuario — igual que el instalador .exe. La
rem     eleccion se recuerda: la 2a vez alcanza con dar Enter.
set "MEMORIA=%LocalAppData%\MV Kobra AI\owner_destino.txt"
set "SUGERIDO=%LocalAppData%\MV Kobra AI"
if exist "!MEMORIA!" (
  for /f "usebackq delims=" %%D in ("!MEMORIA!") do if not "%%D"=="" set "SUGERIDO=%%D"
)

echo [1/7] Carpeta de instalacion
echo       Ahi van Python, el entorno y tus datos ^(hacen falta ~3 GB^).
echo       El codigo del programa se queda donde esta: %CODIGO%
echo.
echo       Enter = usar:  !SUGERIDO!
set "DESTINO="
set /p "DESTINO=      O escribi otra ruta (ej. D:\MVKobraAI): "
if "!DESTINO!"=="" set "DESTINO=!SUGERIDO!"
rem Sacar comillas si el usuario arrastro la carpeta a la ventana.
set "DESTINO=!DESTINO:"=!"
rem Sacar la barra final: "D:\Kobra\" rompe cualquier ruta que se le concatene.
if "!DESTINO:~-1!"=="\" set "DESTINO=!DESTINO:~0,-1!"

mkdir "!DESTINO!" >nul 2>nul
if not exist "!DESTINO!\" (
  echo.
  echo   No pude crear ni abrir esa carpeta:
  echo     !DESTINO!
  echo   Revisa que la ruta sea valida y que tengas permiso de escritura.
  echo.
  pause & exit /b 1
)
rem Prueba de escritura real: una carpeta puede existir y ser de solo lectura.
echo ok> "!DESTINO!\.kobra_prueba" 2>nul
if not exist "!DESTINO!\.kobra_prueba" (
  echo.
  echo   Esa carpeta existe pero no puedo escribir en ella:
  echo     !DESTINO!
  echo   Elegi otra ^(o ejecuta como administrador si es del sistema^).
  echo.
  pause & exit /b 1
)
del "!DESTINO!\.kobra_prueba" >nul 2>nul

set "VENV=!DESTINO!\entorno"
set "DATOS=!DESTINO!\datos"
set "TRABAJO=!DESTINO!\temp"
mkdir "!DATOS!" >nul 2>nul
mkdir "!TRABAJO!" >nul 2>nul
mkdir "%LocalAppData%\MV Kobra AI" >nul 2>nul
>"!MEMORIA!" echo !DESTINO!
echo       Instalando en: !DESTINO!

rem --- 2) Espacio en disco (sobre la carpeta elegida, antes de bajar nada) --
rem     El chequeo viejo miraba el disco del codigo y anunciaba, por ejemplo,
rem     "~523 GB libres" — pero pip descomprime cada wheel en %TEMP%, que vive
rem     en C:. Con C: lleno el chequeo daba OK y la instalacion moria igual con
rem     "[Errno 28] No space left on device" a mitad de bajar plotly. Se mide
rem     el disco de DESTINO y mas abajo se manda ahi todo lo que se descarga.
echo.
echo [2/7] Espacio en disco
call :libres "!DESTINO!" LIBRE_DESTINO
if "!LIBRE_DESTINO!"=="?" (
  echo       No pude medir el espacio libre. Sigo igual.
) else (
  echo       Disponible en !DESTINO!: ~!LIBRE_DESTINO! GB
  if !LIBRE_DESTINO! LSS 3 (
    echo.
    echo   ^(!^) Muy poco espacio ^(~!LIBRE_DESTINO! GB^). Python, el entorno y
    echo   las dependencias necesitan unos 3 GB para descargarse e instalarse.
    echo   Volve a ejecutar el .bat y elegi una carpeta en un disco con
    echo   mas lugar ^(ej. D:\MVKobraAI^).
    echo.
    pause & exit /b 1
  )
)

rem --- 3) Python: el del sistema, o descargarlo AL DISCO ELEGIDO ------------
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"

if not "!PYEXE!"=="" (
  echo.
  echo [3/7] Python: OK
) else (
  echo.
  echo [3/7] Python no encontrado. Descargando e instalando Python 3.11...
  echo       ^(usa PowerShell, incluido en Windows - no requiere winget^)
  rem El instalador baja a !TRABAJO! y no a %TEMP%: si C: esta lleno, bajarlo
  rem a %TEMP% falla con un mensaje de red que no tiene nada que ver.
  set "PYINST=!TRABAJO!\python311_kobra.exe"
  set "KOBRA_PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
  set "KOBRA_PY_DEST=!PYINST!"
  set "KOBRA_PY_ERR=!TRABAJO!\python_descarga_error.txt"
  del "!KOBRA_PY_ERR!" >nul 2>nul
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri $env:KOBRA_PY_URL -OutFile $env:KOBRA_PY_DEST -UseBasicParsing } catch { $_.Exception.Message ^| Set-Content -LiteralPath $env:KOBRA_PY_ERR }"
  if not exist "!PYINST!" (
    echo.
    echo   No pude descargar Python. Motivo exacto:
    if exist "!KOBRA_PY_ERR!" (type "!KOBRA_PY_ERR!") else (echo     ^(sin detalle^))
    echo.
    echo   Si habla de ESPACIO: libera lugar, o volve a ejecutar el .bat y
    echo   elegi una carpeta en un disco con mas lugar.
    echo   Si habla de RED: revisa la conexion, o instala Python a mano desde
    echo   https://www.python.org/downloads/ marcando "Add Python to PATH".
    echo.
    pause & exit /b 1
  )
  echo       Instalando Python en silencio ^(solo para tu usuario, sin admin^)...
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

rem --- 4) Entorno virtual propio (no toca el Python del sistema) ------------
if not exist "!VENV!\Scripts\python.exe" (
  echo.
  echo [4/7] Creando entorno propio...
  "!PYEXE!" -m venv "!VENV!"
) else (
  echo.
  echo [4/7] Entorno propio: OK
)
set "VPY=!VENV!\Scripts\python.exe"
if not exist "!VPY!" (
  echo.
  echo   No se pudo crear el entorno en !VENV!.
  echo   Proba elegir otra carpeta al volver a ejecutar el .bat.
  echo.
  pause & exit /b 1
)

rem --- 5) Dependencias (idempotente: la 2a vez es casi instantanea) ---------
rem     --no-cache-dir: no guarda una copia extra de cada .whl descargado.
rem     TEMP/TMP: pip descomprime en el temp del sistema aunque no cachee, asi
rem     que se lo apunta al disco elegido (ver el comentario del paso 2).
echo.
echo [5/7] Instalando dependencias ^(la 1a vez tarda unos minutos^)...
set "TEMP=!TRABAJO!"
set "TMP=!TRABAJO!"
set "TMPDIR=!TRABAJO!"
"!VPY!" -m pip install --no-cache-dir --upgrade pip >nul 2>nul
"!VPY!" -m pip install --no-cache-dir -r "!CODIGO!\requirements.txt"
if not !errorlevel!==0 (
  echo.
  echo   Fallo la instalacion de dependencias.
  echo   Si dice "No space left on device": elegi al volver a ejecutar una
  echo   carpeta en un disco con mas lugar - todo (descarga incluida) va al
  echo   disco que elegis, asi que con eso alcanza.
  echo   Si es otro error, revisa tu conexion y reintenta: lo que ya se
  echo   instalo no se vuelve a bajar.
  echo.
  pause & exit /b 1
)

rem --- 6) Dejarlo instalado: icono, Menu Inicio y desinstalador ------------
rem     Antes el .bat solo ARRANCABA el programa: no quedaba instalado en
rem     ningun lado, asi que para abrirlo habia que volver a buscar el .bat, y
rem     "desinstalarlo" era borrar carpetas a mano. Todo va a HKCU y al perfil
rem     del usuario: no pide administrador.
echo.
echo [6/7] Dejando el programa instalado ^(icono, Menu Inicio, desinstalador^)...
set "PYW=!VENV!\Scripts\pythonw.exe"
if not exist "!PYW!" set "PYW=!VPY!"
powershell -NoProfile -ExecutionPolicy Bypass -File "!CODIGO!\packaging\instalar_windows.ps1" -Destino "!DESTINO!" -Codigo "!CODIGO!" -Python "!PYW!" -Datos "!DATOS!" -Owner
if errorlevel 1 (
  echo       ^(!^) No se pudieron crear los accesos. El programa igual funciona:
  echo           se abre volviendo a ejecutar este .bat.
)

rem --- 7) Arranque en modo OWNER (React + FastAPI, UI ya compilada) ---------
echo.
echo [7/7] Iniciando MV Kobra AI...
echo.
set KOBRA_OWNER=1
set "KOBRA_DATA_DIR=!DATOS!"
set "KOBRA_UI_DIST=!CODIGO!\owner\ui_dist"
set KOBRA_APP_WINDOW=1
"!VPY!" "!CODIGO!\packaging\kobra_launcher.py"
pause
exit /b 0

rem =========================================================================
rem  :libres <ruta> <variable>  -> GB libres en el volumen de <ruta>, o "?"
rem
rem  PowerShell y no `dir`: el parseo de `dir` depende del idioma de Windows y
rem  del separador de miles, y ya nos habia dado un numero que no era el del
rem  disco que importaba. DriveInfo devuelve los bytes del volumen real de la
rem  ruta (sirve tambien con unidades de red y con subst).
rem
rem  La respuesta pasa por un archivo en vez de leerse con `for /f (`...`)`:
rem  el comando de PowerShell lleva parentesis y comillas, y meterlo dentro de
rem  un `for /f` deja el resultado a merced del parser de cmd. Leer un archivo
rem  con `for /f "usebackq"` no tiene esa ambiguedad.
rem =========================================================================
rem  La ruta viaja por variable de entorno y no incrustada en el comando: asi
rem  no hay que escapar comillas, espacios ni parentesis de "C:\Program Files".
:libres
set "%~2=?"
set "KOBRA_RUTA_MEDIR=%~1"
set "KOBRA_RESP_MEDIR=%~1\.kobra_libres.txt"
del "!KOBRA_RESP_MEDIR!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $p = (Get-Item -LiteralPath $env:KOBRA_RUTA_MEDIR).FullName; $d = New-Object System.IO.DriveInfo $p; [math]::Floor($d.AvailableFreeSpace/1GB) | Set-Content -LiteralPath $env:KOBRA_RESP_MEDIR } catch { }" >nul 2>nul
if exist "!KOBRA_RESP_MEDIR!" (
  for /f "usebackq delims= " %%G in ("!KOBRA_RESP_MEDIR!") do if not "%%G"=="" set "%~2=%%G"
)
del "!KOBRA_RESP_MEDIR!" >nul 2>nul
set "KOBRA_RUTA_MEDIR="
set "KOBRA_RESP_MEDIR="
exit /b 0
