@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Pasar esta copia a edicion OWNER
echo.
echo   ============================================================
echo     MV Kobra AI - Edicion OWNER
echo     Convierte la copia YA INSTALADA en la del dueno:
echo     sin clave, sin trial y sin vencimiento.
echo   ============================================================
echo.

rem La carpeta puede venir como argumento (arrastrando la carpeta de
rem instalacion sobre este archivo) o salir de las rutas por defecto.
set "INTERNO="
if not "%~1"=="" call :probar "%~1"
if not defined INTERNO call :probar "%LOCALAPPDATA%\Programs\MV Kobra AI"
if not defined INTERNO call :probar "%LOCALAPPDATA%\Programs\MV Kobra AI Owner"
if not defined INTERNO call :probar "%ProgramFiles%\MV Kobra AI"
if not defined INTERNO call :probar "%ProgramFiles(x86)%\MV Kobra AI"

if not defined INTERNO (
  echo   No encontre ninguna instalacion de MV Kobra AI.
  echo.
  echo   Opciones:
  echo     - Instala el programa ^(MVKobraAI_Setup.exe^) y volve a correr esto.
  echo     - O arrastra la CARPETA de instalacion sobre este archivo.
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
