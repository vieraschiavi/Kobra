@echo off
REM Arma el instalador privado "Owner": acceso completo, nunca pide
REM licencia. NO subir/compartir este .exe salvo para vos mismo.
cd /d "%~dp0.."
python scripts\build_installer.py owner
pause
