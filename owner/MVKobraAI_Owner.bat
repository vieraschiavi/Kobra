@echo off
title MV Kobra AI - OWNER
rem Arranca el programa INSTALADO (MVKobraAI_Setup.exe) en modo owner:
rem sin licencia, sin trial, entra directo como Administrador.
set KOBRA_OWNER=1

set "EXE_PF=%ProgramFiles%\MV Kobra AI\MVKobraAI.exe"
set "EXE_PF86=%ProgramFiles(x86)%\MV Kobra AI\MVKobraAI.exe"
set "EXE_USER=%LocalAppData%\Programs\MV Kobra AI\MVKobraAI.exe"

if exist "%EXE_PF%"   ( start "" "%EXE_PF%"   & exit /b )
if exist "%EXE_PF86%" ( start "" "%EXE_PF86%" & exit /b )
if exist "%EXE_USER%" ( start "" "%EXE_USER%" & exit /b )

echo [MV Kobra AI] No encuentro el programa instalado (MVKobraAI_Setup.exe).
echo.
echo   Abriendo la version que NO necesita el instalador
echo   (MVKobraAI_Owner_desde_codigo.bat): prepara todo sola.
echo.
timeout /t 3 >nul
call "%~dp0MVKobraAI_Owner_desde_codigo.bat"
