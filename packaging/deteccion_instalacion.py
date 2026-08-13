# © 2026 Martín Viera. Todos los derechos reservados.

r"""
MV Kobra AI · Dónde quedó instalado el programa (metodología única)
====================================================================
Varios scripts necesitan responder la misma pregunta —¿en qué carpeta está
instalado MV Kobra AI?— y hasta acá cada uno la respondía a su manera:

* `owner/MVKobraAI_Owner.bat` (abrir el programa) tenía la respuesta buena:
  rutas por defecto, después el registro de Windows, después la carpeta que
  el instalador de consola dejó anotada.
* `packaging/Owner.bat` (pasar la copia a edición Owner) solo probaba cuatro
  rutas fijas. El asistente deja elegir la carpeta con **Examinar**, así que
  una instalación en `D:\MVKobraAI` —justo lo que recomendamos cuando C: está
  justo de espacio— no aparecía en ninguna, y el .bat daba el programa por no
  instalado.

Este módulo deja esa metodología en UN solo lugar y la emite como batch, para
que todos los scripts detecten igual. El orden es de más barato a más caro:

  1. **Rutas por defecto** de electron-builder. Un `if exist`, sin procesos.
  2. **Registro de Windows** (`InstallLocation` de las tres ramas de "Agregar
     o quitar programas"). Es la única vía que aguanta el botón Examinar,
     porque el instalador anota ahí dónde quedó.
  3. **La carpeta anotada** por los instaladores que preguntan el destino.

Sobre los nombres de la memoria (paso 3): hay DOS convenciones vivas y por eso
`NOMBRES_MEMORIA` las lista a las dos. Los .bat de cada edición que genera
`build_release.py` escriben `destino_<edicion>.txt`; el instalador por consola
(`owner/MVKobraAI_Owner_desde_codigo.bat`) escribe `owner_destino.txt`, que es
también el que borra `packaging/desinstalar_windows.ps1`. El lanzador leía solo
la primera, así que quien instalaba por consola en otro disco no era
encontrado por esa vía. Probar las dos sale gratis —son `if exist`— y evita
tener que migrar archivos ya escritos en las máquinas de los clientes.

El batch se genera desde Python, como el resto de los .bat del repo
(`generar_owner_bat.py`, `build_release.py`): así se controlan el encoding sin
BOM y los CRLF, que ya rompieron .bat de este repo antes. Y se emite batch
PURO, legible de un vistazo: son herramientas que tocan una instalación, y
poder auditarlas leyéndolas importa más que la elegancia.

Todo el texto que sale de acá es ASCII: los .bat se escriben con
`encoding="ascii"` y una tilde los haría fallar al generarse.
"""
from __future__ import annotations

# Dónde instala el .exe cuando el usuario NO toca Examinar. `perMachine: false`
# en electron-builder deja la copia en %LOCALAPPDATA%\Programs\<productName>;
# el Owner usa otro productName, y quedan las dos de Program Files por si
# alguien instaló ahí.
RUTAS_DEFAULT = (
    r"%LOCALAPPDATA%\Programs\MV Kobra AI",
    r"%LOCALAPPDATA%\Programs\MV Kobra AI Owner",
    r"%ProgramFiles%\MV Kobra AI",
    r"%ProgramFiles(x86)%\MV Kobra AI",
)

# Los dos nombres con que se anota el destino elegido (ver el docstring).
# `destino_<edicion>.txt` los escribe build_release.py; `owner_destino.txt`,
# el instalador por consola.
EDICIONES = ("owner", "produccion", "pro", "starter", "basico")
NOMBRES_MEMORIA = tuple(f"destino_{e}.txt" for e in EDICIONES) + ("owner_destino.txt",)

# Carpeta donde viven esos archivos de memoria.
DIR_MEMORIA = r"%LocalAppData%\MV Kobra AI"

# Nombres del ejecutable: el actual (Electron) y el viejo (Inno Setup,
# pre-Electron), por si quedó alguna instalación de aquella época.
EXES = ("MV Kobra AI.exe", "MVKobraAI.exe")


def bloque_registro() -> str:
    """Subrutina `:buscar_en_registro <variable>`, que deja en esa variable la
    carpeta de instalación según el registro, o vacío.

    Le pregunta a las tres ramas de "Agregar o quitar programas" (usuario,
    máquina, y 32-bit en Windows de 64) por `InstallLocation`.

    La respuesta pasa por un archivo temporal y no por ``for /f (`...`)``: el
    comando de PowerShell lleva comillas, comodines y paréntesis, y meterlo
    dentro de un `for /f` deja el resultado a merced del parser de cmd.
    """
    ramas = ("'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
             "'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
             "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'")
    ps = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$r=@({ramas}); "
        "foreach($p in (Get-ItemProperty $r | "
        "Where-Object { $_.DisplayName -like 'MV Kobra AI*' -and $_.InstallLocation } | "
        "Select-Object -ExpandProperty InstallLocation)){ "
        "if(Test-Path -LiteralPath $p){ "
        "Set-Content -LiteralPath $env:KOBRA_RESP_DIR -Value $p; exit } }"
    )
    return (
        "rem :buscar_en_registro <variable>  -> carpeta de instalacion, o vacio\n"
        ":buscar_en_registro\n"
        'set "%~1="\n'
        'set "KOBRA_RESP_DIR=%TEMP%\\kobra_instalacion.txt"\n'
        'del "!KOBRA_RESP_DIR!" >nul 2>nul\n'
        f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{ps}" >nul 2>nul\n'
        'if exist "!KOBRA_RESP_DIR!" (\n'
        '  for /f "usebackq delims=" %%A in ("!KOBRA_RESP_DIR!") do '
        'if not "%%A"=="" set "%~1=%%A"\n'
        ')\n'
        'del "!KOBRA_RESP_DIR!" >nul 2>nul\n'
        'set "KOBRA_RESP_DIR="\n'
        "exit /b 0\n"
    )


def bloque_busqueda(destino: str, comprobar: str,
                    indentar: str = "") -> str:
    """Batch que deja en `!destino!` la carpeta de instalación, o vacío.

    `comprobar` es el nombre de una subrutina `:etiqueta` que recibe una
    carpeta candidata y, si le sirve, define `destino`. Se delega así porque
    cada script busca algo distinto dentro de la instalación: el lanzador
    quiere el `.exe`, y `Owner.bat` quiere `resources\\backend\\_internal`,
    la carpeta donde va el sello de la edición.

    Requiere `setlocal enabledelayedexpansion` y que exista la subrutina
    `:buscar_en_registro` (ver `bloque_registro`).
    """
    i = indentar
    partes = [
        f"{i}rem a) Las rutas donde instala el .exe cuando nadie toca Examinar.\n"
    ]
    for ruta in RUTAS_DEFAULT:
        partes.append(f'{i}if not defined {destino} call :{comprobar} "{ruta}"\n')

    partes.append(
        f"\n{i}rem b) El registro. Es la unica via que aguanta el boton Examinar:\n"
        f"{i}rem    el instalador anota ahi la carpeta que eligio el usuario, asi\n"
        f"{i}rem    que una instalacion en D:\\MVKobraAI tambien aparece.\n"
        f"{i}if not defined {destino} (\n"
        f"{i}  call :buscar_en_registro RAIZ_REG\n"
        f'{i}  if defined RAIZ_REG call :{comprobar} "!RAIZ_REG!"\n'
        f"{i})\n"
    )

    partes.append(
        f"\n{i}rem c) La carpeta que el instalador dejo anotada al preguntar el\n"
        f"{i}rem    destino. Se prueban los dos nombres que se usan hoy: los .bat\n"
        f"{i}rem    de cada edicion escriben destino_<edicion>.txt y el instalador\n"
        f"{i}rem    por consola escribe owner_destino.txt.\n"
    )
    nombres = " ".join(f'"{n}"' for n in NOMBRES_MEMORIA)
    partes.append(
        f"{i}for %%M in ({nombres}) do (\n"
        f'{i}  set "MEM={DIR_MEMORIA}\\%%~M"\n'
        f"{i}  if not defined {destino} if exist \"!MEM!\" (\n"
        f'{i}    for /f "usebackq delims=" %%D in ("!MEM!") do '
        f'if not "%%D"=="" call :{comprobar} "%%D"\n'
        f"{i}  )\n"
        f"{i})\n"
    )
    return "".join(partes)
