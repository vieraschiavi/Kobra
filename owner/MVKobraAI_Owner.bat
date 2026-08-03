@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - OWNER
rem Arranca el programa INSTALADO (MVKobraAI_Setup.exe) en modo owner:
rem sin licencia, sin trial, entra directo como Administrador.
set KOBRA_OWNER=1

rem App de escritorio Electron (instalador actual). electron-builder instala
rem por usuario en %LocalAppData%\Programs; per-machine en Program Files.
set "APP_USER=%LocalAppData%\Programs\MV Kobra AI\MV Kobra AI.exe"
set "APP_PF=%ProgramFiles%\MV Kobra AI\MV Kobra AI.exe"
set "APP_PF86=%ProgramFiles(x86)%\MV Kobra AI\MV Kobra AI.exe"

if exist "%APP_USER%" ( start "" "%APP_USER%" & exit /b )
if exist "%APP_PF%"   ( start "" "%APP_PF%"   & exit /b )
if exist "%APP_PF86%" ( start "" "%APP_PF86%" & exit /b )

rem Instalaciones viejas (Inno Setup, pre-Electron), por si quedaron.
set "EXE_PF=%ProgramFiles%\MV Kobra AI\MVKobraAI.exe"
set "EXE_PF86=%ProgramFiles(x86)%\MV Kobra AI\MVKobraAI.exe"
set "EXE_USER=%LocalAppData%\Programs\MV Kobra AI\MVKobraAI.exe"

if exist "%EXE_PF%"   ( start "" "%EXE_PF%"   & exit /b )
if exist "%EXE_PF86%" ( start "" "%EXE_PF86%" & exit /b )
if exist "%EXE_USER%" ( start "" "%EXE_USER%" & exit /b )

rem =========================================================================
rem  No esta instalado. Antes se caia EN SILENCIO al instalador de consola
rem  (MVKobraAI_Owner_desde_codigo.bat), y esa via -preguntas por texto,
rem  descarga de Python, minutos de pip- terminaba siendo la que veia el
rem  usuario, cuando existe un instalador de Windows de verdad publicado en
rem  Releases: asistente grafico, eleccion de carpeta y disco con boton
rem  Examinar, iconos, desinstalador y sin necesidad de Python.
rem  Ahora el instalador es la opcion por defecto y la consola queda como
rem  alternativa explicita.
rem =========================================================================
set "URL_INSTALADOR=https://github.com/vieraschiavi/Kobra/releases/latest"

echo ============================================================
echo   MV Kobra AI todavia no esta instalado en esta PC.
echo ============================================================
echo.
echo   [1] Descargar el instalador de Windows   ^(recomendado^)
echo       - Asistente grafico, en espanol.
echo       - Elegis carpeta Y DISCO con boton Examinar ^(ej. D:\^).
echo       - Icono en el Escritorio y en el Menu Inicio.
echo       - Desinstalador en "Agregar o quitar programas".
echo       - No necesita Python ni configurar nada.
echo.
echo   [2] Instalar desde el codigo, por consola
echo       Mas lento: descarga Python y las dependencias ^(~3 GB^).
echo       Sirve si no podes bajar el instalador.
echo.
set "OPCION=1"
set /p "OPCION=  Opcion [1]: "

if "!OPCION!"=="2" (
  echo.
  call "%~dp0MVKobraAI_Owner_desde_codigo.bat"
  exit /b
)

start "" "!URL_INSTALADOR!"
echo.
echo   Abri la pagina de descargas en el navegador.
echo   Bajate  MVKobraAI_Setup.exe , ejecutalo y segui el asistente.
echo.
echo   Si no se abrio solo, entra a:
echo   !URL_INSTALADOR!
echo.
pause
exit /b 0
