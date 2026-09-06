@echo off
setlocal
title MV Kobra AI - Diagnostico del entorno
cd /d "%~dp0"

rem Contesta, ANTES de instalar nada, si esta maquina va a dejar correr el
rem programa. Cuando algo falla dice que pedirle a IT, que es la parte que
rem convierte una semana de idas y vueltas en un mail.
rem
rem Se puede correr sobre la carpeta portable sin instalar nada.

echo.
"%~dp0MVKobraAI.exe" --diagnostico
if errorlevel 1 (
  echo.
  echo   Faltan permisos. Copia el texto de arriba y mandaselo a IT.
) else (
  echo.
  echo   Esta maquina puede correr MV Kobra AI.
)
echo.
pause
