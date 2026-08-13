@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - OWNER
rem Arranca el programa INSTALADO (MVKobraAI_Setup.exe) en modo owner:
rem sin licencia, sin trial, entra directo como Administrador.
set KOBRA_OWNER=1

rem App de escritorio Electron (instalador actual). electron-builder instala
rem por usuario en %LocalAppData%\Programs; per-machine en Program Files.
set "APP_USER=%LocalAppData%\Programs\MV Kobra AI\MV Kobra AI.exe"
set "APP_PF=%ProgramFiles%\MV Kobra AI\MV Kobra AI.exe"
set "APP_PF86=%ProgramFiles(x86)%\MV Kobra AI\MV Kobra AI.exe"

rem El build OWNER se instala con otro productName ("MV Kobra AI Owner"), asi
rem que deja la copia en OTRA carpeta. Sin esta linea, la copia del dueno solo
rem se encontraba por el registro. La lista de rutas por defecto sale de
rem packaging/deteccion_instalacion.py.
set "APP_USER_OWNER=%LocalAppData%\Programs\MV Kobra AI Owner\MV Kobra AI.exe"

if exist "%APP_USER%"       ( start "" "%APP_USER%"       & exit /b )
if exist "%APP_USER_OWNER%" ( start "" "%APP_USER_OWNER%" & exit /b )
if exist "%APP_PF%"         ( start "" "%APP_PF%"         & exit /b )
if exist "%APP_PF86%"       ( start "" "%APP_PF86%"       & exit /b )

rem Instalaciones viejas (Inno Setup, pre-Electron), por si quedaron.
set "EXE_PF=%ProgramFiles%\MV Kobra AI\MVKobraAI.exe"
set "EXE_PF86=%ProgramFiles(x86)%\MV Kobra AI\MVKobraAI.exe"
set "EXE_USER=%LocalAppData%\Programs\MV Kobra AI\MVKobraAI.exe"

if exist "%EXE_PF%"   ( start "" "%EXE_PF%"   & exit /b )
if exist "%EXE_PF86%" ( start "" "%EXE_PF86%" & exit /b )
if exist "%EXE_USER%" ( start "" "%EXE_USER%" & exit /b )

rem =========================================================================
rem  Las rutas de arriba son las POR DEFECTO. El asistente deja elegir la
rem  carpeta con el boton Examinar, asi que una instalacion en D:\MVKobraAI
rem  -exactamente lo que recomendamos cuando C: esta justo de espacio- no
rem  aparece en ninguna de ellas. Buscarla solo ahi hacia que el .bat diera
rem  el programa por NO instalado y ofreciera descargarlo de nuevo: abria el
rem  navegador en vez de abrir el programa que ya estaba en la maquina.
rem
rem  El instalador registra donde quedo (InstallLocation en la clave de
rem  desinstalacion, la misma que usa "Agregar o quitar programas"), asi que
rem  se lo preguntamos al registro en vez de adivinar.
rem =========================================================================
call :buscar_instalado APP_REG
if defined APP_REG ( start "" "!APP_REG!" & exit /b )

rem Y la carpeta que eligio el usuario en el instalador, que la deja anotada
rem para no volver a preguntar. Hay DOS convenciones de nombre vivas y se
rem prueban las dos: los .bat de cada edicion (build_release.py) escriben
rem destino_<edicion>.txt, y el instalador por consola
rem (MVKobraAI_Owner_desde_codigo.bat) escribe owner_destino.txt. Mirando
rem solo la primera, a quien instalaba por consola en otro disco no se lo
rem encontraba por esta via. La lista sale de packaging/deteccion_instalacion.py.
for %%M in ("destino_owner.txt" "destino_produccion.txt" "destino_pro.txt" "destino_starter.txt" "destino_basico.txt" "owner_destino.txt") do (
  set "MEM=%LocalAppData%\MV Kobra AI\%%~M"
  if exist "!MEM!" (
    for /f "usebackq delims=" %%D in ("!MEM!") do (
      if exist "%%D\MV Kobra AI.exe" ( start "" "%%D\MV Kobra AI.exe" & exit /b )
      if exist "%%D\MVKobraAI.exe"   ( start "" "%%D\MVKobraAI.exe"   & exit /b )
    )
  )
)

rem =========================================================================
rem  No esta instalado. Antes se caia EN SILENCIO al instalador de consola
rem  (MVKobraAI_Owner_desde_codigo.bat), y esa via -preguntas por texto,
rem  descarga de Python, minutos de pip- terminaba siendo la que veia el
rem  usuario, cuando existe un instalador de Windows de verdad publicado en
rem  Releases: asistente grafico, eleccion de carpeta y disco con boton
rem  Examinar, iconos, desinstalador y sin necesidad de Python.
rem  Ahora el instalador es la opcion por defecto y la consola queda como
rem  alternativa explicita.
rem =========================================================================
set "URL_INSTALADOR=https://github.com/vieraschiavi/Kobra/releases/latest"

echo ============================================================
echo   MV Kobra AI todavia no esta instalado en esta PC.
echo ============================================================
echo.
echo   [1] Descargar el instalador de Windows   ^(recomendado^)
echo       - Asistente grafico, en espanol.
echo       - Elegis carpeta Y DISCO con boton Examinar ^(ej. D:\^).
echo       - Icono en el Escritorio y en el Menu Inicio.
echo       - Desinstalador en "Agregar o quitar programas".
echo       - No necesita Python ni configurar nada.
echo.
echo   [2] Instalar desde el codigo, por consola
echo       Mas lento: descarga Python y las dependencias ^(~3 GB^).
echo       Sirve si no podes bajar el instalador.
echo.
set "OPCION=1"
set /p "OPCION=  Opcion [1]: "

if "!OPCION!"=="2" (
  echo.
  call "%~dp0MVKobraAI_Owner_desde_codigo.bat"
  exit /b
)

start "" "!URL_INSTALADOR!"
echo.
echo   Abri la pagina de descargas en el navegador.
echo   Bajate  MVKobraAI_Setup.exe , ejecutalo y segui el asistente.
echo.
echo   Si no se abrio solo, entra a:
echo   !URL_INSTALADOR!
echo.
pause
exit /b 0

rem =========================================================================
rem  :buscar_instalado <variable>  -> ruta del .exe instalado, o vacio
rem
rem  Le pregunta al REGISTRO donde quedo instalado en vez de adivinar rutas:
rem  el asistente deja elegir la carpeta, asi que las rutas por defecto no
rem  alcanzan. Mira las tres ramas de "Agregar o quitar programas" (usuario,
rem  maquina, y 32-bit en Windows de 64) y se queda con InstallLocation.
rem
rem  La respuesta pasa por un archivo y no por `for /f (`...`)`: el comando de
rem  PowerShell lleva comillas, comodines y parentesis, y meterlo dentro de un
rem  `for /f` deja el resultado a merced del parser de cmd.
rem =========================================================================
:buscar_instalado
set "%~1="
set "KOBRA_RESP_APP=%TEMP%\kobra_app_instalada.txt"
del "!KOBRA_RESP_APP!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $r=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'); foreach($p in (Get-ItemProperty $r | Where-Object { $_.DisplayName -like 'MV Kobra AI*' -and $_.InstallLocation } | Select-Object -ExpandProperty InstallLocation)){ foreach($n in @('MV Kobra AI.exe','MVKobraAI.exe')){ $f=Join-Path $p $n; if(Test-Path -LiteralPath $f){ Set-Content -LiteralPath $env:KOBRA_RESP_APP -Value $f; exit } } }" >nul 2>nul
if exist "!KOBRA_RESP_APP!" (
  for /f "usebackq delims=" %%A in ("!KOBRA_RESP_APP!") do if not "%%A"=="" set "%~1=%%A"
)
del "!KOBRA_RESP_APP!" >nul 2>nul
set "KOBRA_RESP_APP="
exit /b 0
