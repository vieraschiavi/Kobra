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

rem 1) La carpeta donde esta ESTE archivo. Es el caso normal: se copia
rem    el .bat junto al programa y se hace doble clic. Se contemplan
rem    las tres alturas posibles de la instalacion.
if not defined INTERNO call :probar "%~dp0."
if not defined INTERNO if exist "%~dp0_internal\" set "INTERNO=%~dp0_internal"
if not defined INTERNO if exist "%~dp0base_library.zip" set "INTERNO=%~dp0."

rem 2) Una carpeta arrastrada sobre el .bat.
if not defined INTERNO if not "%~1"=="" call :probar "%~1"

rem 3) Y por ultimo las rutas donde instala el .exe por defecto.
if not defined INTERNO call :probar "%LOCALAPPDATA%\Programs\MV Kobra AI"
if not defined INTERNO call :probar "%LOCALAPPDATA%\Programs\MV Kobra AI Owner"
if not defined INTERNO call :probar "%ProgramFiles%\MV Kobra AI"
if not defined INTERNO call :probar "%ProgramFiles(x86)%\MV Kobra AI"

if not defined INTERNO (
  echo   No encontre la instalacion de MV Kobra AI.
  echo.
  echo   Copia este archivo a la carpeta donde esta el programa
  echo   ^(la que tiene "MV Kobra AI.exe"^) y hace doble clic ahi.
  echo   Tambien podes arrastrar esa carpeta sobre este archivo.
  echo.
  pause
  exit /b 1
)

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

:probar
if exist "%~1\resources\backend\_internal\" set "INTERNO=%~1\resources\backend\_internal"
goto :eof
