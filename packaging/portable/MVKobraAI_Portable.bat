@echo off
setlocal
title MV Kobra AI - Portable
cd /d "%~dp0"

rem MV Kobra AI, modo PORTABLE.
rem
rem No instala nada: no toca el registro, no crea servicios, no pide
rem administrador y no deja nada fuera de esta carpeta. Para la VM de un
rem cliente o una laptop corporativa donde no te dejan instalar software.
rem
rem Los datos van a la subcarpeta datos\ de aca al lado, y no al perfil del
rem usuario: asi la carpeta entera es el programa. Se copia, se mueve o se
rem borra de una pieza, y no queda nada disperso en la maquina del cliente
rem cuando termina el proyecto -- que es justo lo que pregunta el area de
rem seguridad antes de autorizarlo.
set "KOBRA_DATA_DIR=%~dp0datos"
set "KOBRA_CONFIG_DIR=%~dp0datos\config"

if not exist "%KOBRA_DATA_DIR%" mkdir "%KOBRA_DATA_DIR%" 2>nul
if not exist "%KOBRA_DATA_DIR%" (
  echo.
  echo   No puedo crear la carpeta de datos aca:
  echo     %KOBRA_DATA_DIR%
  echo.
  echo   Copia esta carpeta a una unidad donde puedas escribir
  echo   ^(por ejemplo tu carpeta de Documentos^) y volve a intentar.
  echo.
  pause & exit /b 1
)

echo.
echo   Iniciando MV Kobra AI ^(portable^)...
echo   Se abre solo en el navegador. Para cerrarlo, cerra esta ventana.
echo.
start "" "%~dp0MVKobraAI.exe"
