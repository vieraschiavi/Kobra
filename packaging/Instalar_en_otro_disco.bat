@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Instalar sin usar el disco C
echo.
echo   ============================================================
echo     MV Kobra AI - Instalacion en el disco que vos elijas
echo.
echo     Windows descomprime todo instalador en la carpeta temporal
echo     ^(normalmente en C:^) antes de abrir la primera pantalla.
echo     Si C: esta lleno o el antivirus la bloquea, falla ahi.
echo     Este archivo manda esa carpeta temporal al MISMO disco
echo     donde esta guardado.
echo   ============================================================
echo.

rem --- 1) Buscar el instalador ---------------------------------------
rem Se acepta arrastrado sobre este .bat, o al lado de este .bat.
set "SETUP="
if not "%~1"=="" if exist "%~1" set "SETUP=%~1"
if not defined SETUP for %%F in ("%~dp0MVKobraAI_Setup_OWNER.exe") do if exist "%%~F" set "SETUP=%%~F"
if not defined SETUP for %%F in ("%~dp0MVKobraAI_Setup.exe") do if exist "%%~F" set "SETUP=%%~F"

if not defined SETUP (
  echo   No encontre el instalador.
  echo.
  echo   Copia este archivo a la MISMA carpeta donde bajaste
  echo   MVKobraAI_Setup.exe ^(o el _OWNER^) y hace doble clic aca.
  echo   Tambien podes arrastrar el .exe sobre este archivo.
  echo.
  pause
  exit /b 1
)

rem --- 2) Carpeta temporal en ESTE disco ------------------------------
set "TRABAJO=%~dp0kobra_temp_instalacion"
if not exist "!TRABAJO!" mkdir "!TRABAJO!" 2>nul
if not exist "!TRABAJO!" (
  echo   No pude crear la carpeta de trabajo:
  echo     !TRABAJO!
  echo   Copia este archivo y el instalador a una carpeta donde
  echo   tengas permiso de escritura ^(por ejemplo D:\MVKobra^).
  echo.
  pause
  exit /b 1
)

rem Solo para ESTE proceso y sus hijos: no cambia la config de Windows.
set "TEMP=!TRABAJO!"
set "TMP=!TRABAJO!"

echo   Instalador : !SETUP!
echo   Temporales : !TEMP!
echo.
echo   Se abre el asistente. Cuando pregunte la carpeta de destino,
echo   elegi una de este mismo disco para no usar C: en absoluto.
echo.

rem --- 3) Correr el instalador y esperar ------------------------------
start "" /wait "!SETUP!"
set "CODIGO=!errorlevel!"

rem --- 4) Limpiar --------------------------------------------------
rd /s /q "!TRABAJO!" 2>nul

echo.
if "!CODIGO!"=="0" (
  echo   Listo. El instalador termino sin errores.
) else (
  echo   El instalador termino con codigo !CODIGO!.
  echo   Si volvio a fallar escribiendo archivos, revisa que el disco
  echo   donde esta este archivo tenga espacio libre, y agrega la
  echo   carpeta a las exclusiones del antivirus.
)
echo.
pause
