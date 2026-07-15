@echo off
title MV Kobra AI - OWNER (desde codigo)
rem Corre la app completa desde el codigo fuente del repo, en modo owner.
rem Requiere: Python 3.11+ con requirements.txt instalado, y el frontend
rem compilado una vez (cd webapp\frontend ^&^& npm ci ^&^& npm run build).
cd /d "%~dp0.."

where python >nul 2>nul
if not %errorlevel%==0 (
  echo [MV Kobra AI] Falta Python 3.11+ en el PATH.
  pause & exit /b 1
)

set KOBRA_OWNER=1
python packaging\kobra_launcher.py
pause
