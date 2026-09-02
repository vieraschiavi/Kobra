@echo off
rem MV Kobra AI - Resuelve el sello del dueno en KOBRA_OWNER_TOKEN.
rem
rem Se llama con  call "%~dp0sello_owner.bat"  desde los lanzadores owner.
rem
rem Por que existe: hasta la version anterior los lanzadores hacian
rem     set KOBRA_OWNER=1
rem y eso YA NO DESBLOQUEA NADA. Un "1" en una variable lo escribia cualquiera
rem en diez segundos, asi que la edicion del dueno paso a exigir un token
rem firmado con la privada (kobra\edicion.py::sello_owner_valido). Los .bat
rem quedaron prometiendo "entra directo, sin licencia" y entregando la pantalla
rem de licencia: el peor final posible, porque parece que el programa se rompio.
rem
rem De donde sale el token, en orden:
rem   1. KOBRA_OWNER_TOKEN ya puesto  -> no se toca;
rem   2. KOBRA_OWNER_SELLO            -> el token pegado a mano;
rem   3. KOBRA_OWNER_SELLO_ARCHIVO    -> un archivo con el token adentro.
rem
rem El archivo es lo comodo: un JWT de 700 caracteres pegado en una consola
rem queda en el historial de cmd. Se deja una vez, fuera del repo:
rem     setx KOBRA_OWNER_SELLO_ARCHIVO C:\ruta\sello_owner.txt

if defined KOBRA_OWNER_TOKEN goto :eof

if defined KOBRA_OWNER_SELLO (
  set "KOBRA_OWNER_TOKEN=%KOBRA_OWNER_SELLO%"
  goto :eof
)

if defined KOBRA_OWNER_SELLO_ARCHIVO (
  if exist "%KOBRA_OWNER_SELLO_ARCHIVO%" (
    rem usebackq + delims= : la ruta puede llevar espacios y el token no se
    rem puede partir por ningun separador.
    for /f "usebackq delims=" %%T in ("%KOBRA_OWNER_SELLO_ARCHIVO%") do (
      if not defined KOBRA_OWNER_TOKEN set "KOBRA_OWNER_TOKEN=%%T"
    )
    goto :eof
  )
  echo   ^(!^) No existe el archivo del sello: %KOBRA_OWNER_SELLO_ARCHIVO%
)
goto :eof
