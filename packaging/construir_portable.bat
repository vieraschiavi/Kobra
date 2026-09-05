@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Construir la carpeta PORTABLE
cd /d "%~dp0.."

echo ============================================================
echo   MV Kobra AI - CARPETA PORTABLE
echo   Genera MVKobraAI_Portable.zip: el programa completo
echo   SIN instalador, para la VM de un cliente o una laptop
echo   corporativa donde no te dejan instalar software.
echo ============================================================
echo.

rem Reusa la misma tuberia que el instalador: Python, Node, dependencias,
rem datos de demo, interfaz React y el motor de PyInstaller. Lo unico que NO
rem hace es el paso de electron-builder/NSIS, que es justamente lo que
rem convierte al programa en algo que "se instala".
rem
rem Por que reusa y no duplica: dos tuberias de compilacion en paralelo se
rem separan a la primera correccion que se haga en una sola, y ahi el portable
rem empieza a ser una version distinta del producto sin que nadie lo note.
call "%~dp0construir_instalador.bat" solo-motor
if not !errorlevel!==0 (
  echo   Fallo la preparacion del motor.
  pause & exit /b 1
)

if not exist "dist\MVKobraAI\MVKobraAI.exe" (
  echo   No aparecio dist\MVKobraAI: no hay nada que empaquetar.
  pause & exit /b 1
)

echo.
echo   Armando la carpeta portable...
set "SALIDA=dist\MVKobraAI_Portable"
if exist "!SALIDA!" rmdir /s /q "!SALIDA!"
mkdir "!SALIDA!"

rem El bundle de PyInstaller YA es portable: es una carpeta que se copia y
rem corre. Lo unico que se le agrega es el lanzador, el diagnostico y el LEEME.
xcopy "dist\MVKobraAI" "!SALIDA!\" /E /I /Q /Y >nul
copy /y "packaging\portable\MVKobraAI_Portable.bat"    "!SALIDA!\" >nul
copy /y "packaging\portable\MVKobraAI_Diagnostico.bat" "!SALIDA!\" >nul
copy /y "packaging\portable\LEEME.txt"                 "!SALIDA!\" >nul

echo   Comprimiendo...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path 'dist\MVKobraAI_Portable\*' -DestinationPath 'dist\MVKobraAI_Portable.zip' -Force"
if not exist "dist\MVKobraAI_Portable.zip" (
  echo   Fallo al comprimir.
  pause & exit /b 1
)

copy /y "dist\MVKobraAI_Portable.zip" "%USERPROFILE%\Desktop\" >nul 2>nul

echo.
echo ============================================================
echo   LISTO. Carpeta portable generada:
echo.
echo   dist\MVKobraAI_Portable.zip
echo   ^(tambien te deje una copia en el Escritorio^)
echo.
echo   COMO SE USA en la maquina del cliente:
echo     1. Descomprimir en una carpeta donde se pueda escribir.
echo     2. Doble clic en MVKobraAI_Diagnostico.bat  ^(30 segundos^).
echo     3. Si dio verde: doble clic en MVKobraAI_Portable.bat.
echo.
echo   No instala nada, no toca el registro y no pide administrador.
echo   Los datos quedan en la subcarpeta datos\ de la propia carpeta:
echo   se borra la carpeta y no queda rastro en esa maquina.
echo ============================================================
echo.
pause
