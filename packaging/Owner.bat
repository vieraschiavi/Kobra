@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Pasar esta copia a edicion OWNER
echo.
echo   ============================================================
echo     MV Kobra AI - Edicion OWNER
echo     Convierte la copia YA INSTALADA en la del dueno:
echo     sin clave, sin trial y sin vencimiento.
echo.
echo     Lo mas simple: copia este archivo a la carpeta donde esta
echo     el programa y hace doble clic.
echo   ============================================================
echo.

set "INTERNO="
set "PARCIAL="
set "DIAG=%TEMP%\kobra_owner_rutas.txt"
del "!DIAG!" >nul 2>nul

rem 1) La carpeta donde esta ESTE archivo. Es el caso normal: se copia
rem    el .bat junto al programa y se hace doble clic. Se contemplan
rem    las tres alturas posibles de la instalacion.
if not defined INTERNO call :probar "%~dp0."
if not defined INTERNO if exist "%~dp0_internal\" set "INTERNO=%~dp0_internal"
if not defined INTERNO if exist "%~dp0base_library.zip" set "INTERNO=%~dp0."

rem 2) Una carpeta arrastrada sobre el .bat.
if not defined INTERNO if not "%~1"=="" call :probar "%~1"

rem 3) Y si no, se busca la instalacion sola (rutas por defecto,
rem    registro de Windows y la carpeta que quedo anotada).
rem a) Las rutas donde instala el .exe cuando nadie toca Examinar.
if not defined INTERNO call :probar "%LOCALAPPDATA%\Programs\MV Kobra AI"
if not defined INTERNO call :probar "%LOCALAPPDATA%\Programs\MV Kobra AI Owner"
if not defined INTERNO call :probar "%ProgramFiles%\MV Kobra AI"
if not defined INTERNO call :probar "%ProgramFiles%\MV Kobra AI Owner"
if not defined INTERNO call :probar "%ProgramFiles(x86)%\MV Kobra AI"
if not defined INTERNO call :probar "%ProgramFiles(x86)%\MV Kobra AI Owner"

rem b) El registro. Es la unica via que aguanta el boton Examinar:
rem    el instalador anota ahi la carpeta que eligio el usuario, asi
rem    que una instalacion en D:\MVKobraAI tambien aparece.
if not defined INTERNO (
  call :buscar_en_registro RAIZ_REG
  if defined RAIZ_REG call :probar "!RAIZ_REG!"
)

rem c) La carpeta que el instalador dejo anotada al preguntar el
rem    destino. Se prueban los dos nombres que se usan hoy: los .bat
rem    de cada edicion escriben destino_<edicion>.txt y el instalador
rem    por consola escribe owner_destino.txt.
for %%M in ("destino_owner.txt" "destino_produccion.txt" "destino_pro.txt" "destino_starter.txt" "destino_basico.txt" "owner_destino.txt") do (
  set "MEM=%LocalAppData%\MV Kobra AI\%%~M"
  if not defined INTERNO if exist "!MEM!" (
    for /f "usebackq delims=" %%D in ("!MEM!") do if not "%%D"=="" call :probar "%%D"
  )
)

if not defined INTERNO if defined PARCIAL (
  echo   Encontre MV Kobra AI instalado en:
  echo     !PARCIAL!
  echo.
  echo   Pero le falta la carpeta resources\backend\_internal, que es
  echo   el motor del programa. La instalacion quedo a medias.
  echo.
  echo   Volve a correr MVKobraAI_Setup.exe y dejalo terminar. Si se
  echo   corta siempre en el mismo punto, suele ser falta de espacio
  echo   en disco o el antivirus borrando archivos recien copiados.
  echo.
  pause
  exit /b 1
)

if not defined INTERNO (
  echo   No encontre la instalacion de MV Kobra AI.
  echo.
  echo   Busque en estas carpetas:
  if exist "!DIAG!" type "!DIAG!"
  echo.
  echo   Si el programa esta instalado en otro lado: copia este
  echo   archivo a la carpeta donde esta el programa
  echo   ^(la que tiene "MV Kobra AI.exe"^) y hace doble clic ahi.
  echo   Tambien podes arrastrar esa carpeta sobre este archivo.
  echo.
  echo   Si NO esta instalado: corre primero MVKobraAI_Setup.exe.
  echo.
  del "!DIAG!" >nul 2>nul
  pause
  exit /b 1
)
del "!DIAG!" >nul 2>nul

echo   Instalacion encontrada:
echo     !INTERNO!
echo.

rem El sello es lo unico que separa la copia del dueno de la de un
rem cliente. Va en _internal porque eso es sys._MEIPASS del bundle
rem congelado, que es de donde kobra\edicion.py lo lee al arrancar.
rem Se escribe con redireccion cruda: sin BOM (json.load falla con BOM)
rem y sin que batch tenga que escapar nada del JSON.
>"!INTERNO!\edicion.json" echo {"edition":"Owner","plan":null,"dias":null,"owner":true}

rem Verificar lo que quedo escrito. Sin esto, un permiso denegado o el
rem programa abierto terminarian en un "listo" que no es cierto.
findstr /i /c:"owner" "!INTERNO!\edicion.json" >nul 2>&1
if errorlevel 1 (
  echo   ERROR: no pude escribir el sello.
  echo   Cerra MV Kobra AI si esta abierto y proba de nuevo.
  echo.
  pause
  exit /b 1
)

echo   Listo: esta copia quedo en edicion OWNER.
echo   Abrila normalmente: entra directo, sin pedir ninguna clave.
echo.
pause
exit /b 0

rem Una carpeta candidata sirve si adentro tiene el bundle congelado:
rem ahi es donde va el sello. Cada script comprueba lo suyo (el
rem lanzador busca el .exe), por eso la deteccion recibe esta rutina.
rem
rem Anota lo que probo y, si encuentra el .exe pero NO el motor, deja
rem la carpeta en PARCIAL: esa es una instalacion a medias y merece
rem otro mensaje que "no esta instalado".
:probar
if "%~1"=="" goto :eof
>>"!DIAG!" echo     %~1
if exist "%~1\resources\backend\_internal\" set "INTERNO=%~1\resources\backend\_internal"
if not defined INTERNO if exist "%~1\MV Kobra AI.exe" set "PARCIAL=%~1"
goto :eof

rem :buscar_en_registro <variable>  -> carpeta de instalacion, o vacio
:buscar_en_registro
set "%~1="
set "KOBRA_RESP_DIR=%TEMP%\kobra_instalacion.txt"
del "!KOBRA_RESP_DIR!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $r=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'); foreach($p in (Get-ItemProperty $r | Where-Object { $_.DisplayName -like 'MV Kobra AI*' -and $_.InstallLocation } | Select-Object -ExpandProperty InstallLocation)){ if(Test-Path -LiteralPath $p){ Set-Content -LiteralPath $env:KOBRA_RESP_DIR -Value $p; exit } }" >nul 2>nul
if exist "!KOBRA_RESP_DIR!" (
  for /f "usebackq delims=" %%A in ("!KOBRA_RESP_DIR!") do if not "%%A"=="" set "%~1=%%A"
)
del "!KOBRA_RESP_DIR!" >nul 2>nul
set "KOBRA_RESP_DIR="
exit /b 0
