@echo off
setlocal enabledelayedexpansion
title MV Kobra AI - Generar el sello del dueno (una sola vez)
cd /d "%~dp0.."

echo ============================================================
echo   MV Kobra AI - SELLO DEL DUENO
echo   Se hace UNA sola vez. Despues de esto,
echo   construir_instalador_owner.bat anda de doble clic.
echo ============================================================
echo.

rem --- 1) La clave privada ---------------------------------------------------
rem Se acepta arrastrada sobre el .bat, ya puesta en el entorno, o tipeada.
rem El archivo es la via que de verdad funciona en Windows: una clave RSA
rem tiene saltos de linea y `set` no los conserva.
set "CLAVE=%~1"

if not defined CLAVE if defined KOBRA_LICENSE_PRIVATE_KEY (
  echo [1/3] Clave privada: la tomo de KOBRA_LICENSE_PRIVATE_KEY
  goto :clave_lista
)

if not defined CLAVE (
  rem Rutas donde suele quedar guardada, para no preguntar al que ya la dejo.
  for %%C in (
    "%USERPROFILE%\.kobra\privada.pem"
    "%USERPROFILE%\.kobra\kobra_privada.pem"
    "%USERPROFILE%\Documents\kobra_privada.pem"
  ) do if not defined CLAVE if exist "%%~C" set "CLAVE=%%~C"
  if defined CLAVE echo [1/3] Clave privada encontrada en: !CLAVE!
)

if not defined CLAVE (
  echo [1/3] No encontre la clave privada del dueno.
  echo.
  echo   Es la MISMA que firma las licencias que vendes. La tenes en el
  echo   servidor de ventas: Vercel - Settings - Environment Variables -
  echo   KOBRA_LICENSE_PRIVATE_KEY. Copiala a un archivo .pem en tu PC,
  echo   fuera de la carpeta del repositorio.
  echo.
  echo   Despues podes arrastrar ese .pem sobre este .bat y listo.
  echo.
  set /p "CLAVE=Ruta del archivo .pem (o Enter para salir): "
)

if not defined CLAVE (
  echo.
  echo   Sin la clave no se puede firmar nada. No se genero ningun sello.
  echo.
  pause & exit /b 1
)

if not exist "!CLAVE!" (
  echo.
  echo   No existe el archivo: !CLAVE!
  echo.
  pause & exit /b 1
)
:clave_lista
echo.

rem --- 2) Python -------------------------------------------------------------
rem Se prefiere el entorno del repo si ya existe: ahi estan PyJWT y
rem cryptography, que es lo que la firma necesita.
set "PYEXE="
if exist ".kobra_venv\Scripts\python.exe" set "PYEXE=.kobra_venv\Scripts\python.exe"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  echo [2/3] No encontre Python.
  echo.
  echo   Corre primero packaging\construir_instalador.bat una vez: deja el
  echo   entorno armado solo ^(instala Python y las dependencias^) y despues
  echo   este .bat lo usa.
  echo.
  pause & exit /b 1
)
echo [2/3] Python: OK

rem Que esten las dos librerias de la firma; si no, se instalan.
"!PYEXE!" -c "import jwt, cryptography" >nul 2>nul
if not !errorlevel!==0 (
  echo       Instalando lo necesario para firmar ^(PyJWT, cryptography^)...
  "!PYEXE!" -m pip install --no-cache-dir --quiet PyJWT cryptography
  if not !errorlevel!==0 (
    echo   No pude instalar PyJWT/cryptography. Revisa la conexion.
    pause & exit /b 1
  )
)
echo.

rem --- 3) Emitir y dejarlo apuntado ------------------------------------------
rem El token se escribe DIRECTO al archivo: no pasa por la pantalla ni por el
rem portapapeles, que es justo donde se cortaba al copiarlo a mano.
echo [3/3] Firmando el sello...
set "DESTINO=%USERPROFILE%\.kobra\sello_owner.txt"
if defined CLAVE if exist "!CLAVE!" (
  "!PYEXE!" packaging\emitir_sello_owner.py --clave "!CLAVE!" --destino "!DESTINO!"
) else (
  "!PYEXE!" packaging\emitir_sello_owner.py --destino "!DESTINO!"
)
if not !errorlevel!==0 (
  echo.
  pause & exit /b 1
)

rem setx y no set: tiene que seguir puesta la proxima vez que abra una consola,
rem que es cuando va a correr el build.
setx KOBRA_OWNER_SELLO_ARCHIVO "!DESTINO!" >nul
if not !errorlevel!==0 (
  echo   ^(aviso^) No pude dejar la variable puesta. Ponela a mano:
  echo       setx KOBRA_OWNER_SELLO_ARCHIVO "!DESTINO!"
)

echo.
echo ============================================================
echo   LISTO. El sello quedo guardado y apuntado.
echo.
echo   Ahora hace doble clic en:
echo     packaging\construir_instalador_owner.bat
echo.
echo   Eso genera MVKobraAI_Setup_OWNER.exe: tu copia, sin
echo   licencia, sin trial y sin vencimiento.
echo.
echo   El sello es una credencial: no lo subas al repo ni lo
echo   mandes por mail. Con el, cualquier instalacion pasa a ser
echo   la edicion sin limites.
echo ============================================================
echo.
pause
