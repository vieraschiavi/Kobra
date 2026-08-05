@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Descargar instalador
cd /d "%~dp0"

rem =========================================================================
rem  Baja el instalador de Windows (MVKobraAI_Setup.exe) y lo deja al lado
rem  de este archivo.
rem
rem  Por que el .exe no esta commiteado aca: GitHub rechaza archivos de mas
rem  de 100 MB en un repositorio, y el instalador pesa ~267 MB. Git LFS lo
rem  permitiria pero su cuota gratis (1 GB/mes de trafico) se agota en tres
rem  descargas. El binario vive en Releases, que es el lugar de GitHub hecho
rem  para esto y no tiene ese limite; este .bat lo trae de ahi.
rem
rem  La URL apunta a /releases/latest/: siempre baja el ultimo publicado,
rem  sin tener que actualizar este archivo en cada version.
rem =========================================================================
set "URL=https://github.com/vieraschiavi/Kobra/releases/latest/download/MVKobraAI_Setup.exe"
set "DESTINO=%~dp0MVKobraAI_Setup.exe"

echo ============================================================
echo   MV Kobra AI - Instalador de Windows
echo ============================================================
echo.
echo   Bajando el instalador mas reciente ^(~267 MB^)...
echo   Puede tardar unos minutos segun tu conexion.
echo.

rem El repositorio es PRIVADO: sin credenciales, la descarga directa devuelve
rem 404. Se prueba igual y, si falla, se abre la pagina en el navegador, donde
rem la sesion de GitHub del dueno si tiene acceso.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri $env:URL -OutFile $env:DESTINO -UseBasicParsing; exit 0 } catch { exit 1 }"

if exist "!DESTINO!" (
  echo.
  echo   Listo: !DESTINO!
  echo.
  echo   Verificacion ^(compara con el SHA256 que muestra la pagina de la
  echo   release^):
  powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath $env:DESTINO).Hash.ToLower()"
  echo.
  echo   Ahora ejecuta MVKobraAI_Setup.exe y segui el asistente.
  echo.
  pause
  exit /b 0
)

echo.
echo   No pude bajarlo directo ^(el repositorio es privado^).
echo   Abro la pagina de descargas: entra con tu cuenta de GitHub y baja
echo   MVKobraAI_Setup.exe a mano.
echo.
start "" "https://github.com/vieraschiavi/Kobra/releases/latest"
pause
exit /b 0
