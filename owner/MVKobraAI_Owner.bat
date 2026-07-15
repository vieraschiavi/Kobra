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

echo [MV Kobra AI] No encuentro el programa instalado.
echo Instala MVKobraAI_Setup.exe primero, o usa MVKobraAI_Owner_desde_codigo.bat
echo si queres correrlo directo desde el codigo fuente.
pause
