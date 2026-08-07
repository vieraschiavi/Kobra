@echo off
REM Arma el instalador público "Cliente" (arranca en modo demo, se activa
REM con la licencia que el backend de venta emite al confirmarse el pago).
cd /d "%~dp0.."
python scripts\build_installer.py cliente
pause
