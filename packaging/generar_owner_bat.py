"""
MV Kobra AI · Genera `packaging/Owner.bat`
==========================================
`Owner.bat` convierte una instalación YA HECHA de MV Kobra AI en la edición
del dueño: sin clave, sin trial y sin vencimiento. No recompila nada.

Por qué alcanza con eso
-----------------------
El instalador de clientes y el de owner salen del mismo bundle de PyInstaller.
Lo único que los diferencia es un archivo de 55 bytes que el workflow inyecta
antes de empaquetar:

    <instalación>\\resources\\backend\\_internal\\edicion.json
    {"edition":"Owner","plan":null,"dias":null,"owner":true}

`_internal` es lo que PyInstaller expone como `sys._MEIPASS`, que es de donde
`kobra/edicion.py::activar` lee el sello al arrancar. Poniendo ese archivo, la
copia instalada pasa a ser la del dueño. `tests/test_sello_owner.py` fija esa
equivalencia y que el sello sea idéntico al que produce el CI.

El .bat se GENERA desde acá en vez de escribirse a mano por dos motivos que ya
rompieron .bat de este repo antes: el encoding (un BOM y `cmd.exe` no abre el
archivo) y los saltos de línea (hacen falta CRLF, y escribir `\\r\\n` a mano
sobre un `newline=""` deja `\\r\\r\\n`). Acá se controlan los dos.

Es batch PURO a propósito. La primera versión embebía el trabajo como
PowerShell en base64 (`-EncodedCommand`), que resuelve el escapado de comillas
pero tiene dos costos que no valen la pena para esto: los antivirus tratan ese
patrón como sospechoso —es el que usa medio malware de Windows— y deja un
archivo que nadie puede leer para saber qué hace. Para una herramienta que
convierte una copia en la edición sin límites, ser auditable de un vistazo
importa más que la elegancia. Y el escapado no hace falta: el JSON del sello
no tiene ningún carácter que batch interprete (`>`, `<`, `|`, `&`, `%`, `^`).

Uso:
    python packaging/generar_owner_bat.py
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(ROOT, "packaging", "Owner.bat")

# El MISMO sello que inyecta .github/workflows/release_owner.yml.
# `tests/test_sello_owner.py` compara los dos y falla si se separan.
SELLO = '{"edition":"Owner","plan":null,"dias":null,"owner":true}'

# Dónde puede estar instalado. `perMachine: false` en electron-builder deja la
# copia en %LOCALAPPDATA%\Programs\<productName>; el Owner usa otro
# productName, y quedan las dos de Program Files por si alguien instaló ahí.
_CANDIDATAS = [
    r"%LOCALAPPDATA%\Programs\MV Kobra AI",
    r"%LOCALAPPDATA%\Programs\MV Kobra AI Owner",
    r"%ProgramFiles%\MV Kobra AI",
    r"%ProgramFiles(x86)%\MV Kobra AI",
]


def _bat() -> str:
    busqueda = "".join(
        f'if not defined INTERNO call :probar "{ruta}"\n' for ruta in _CANDIDATAS)
    return (
        "@echo off\n"
        "setlocal enabledelayedexpansion\n"
        "title MV Kobra AI - Pasar esta copia a edicion OWNER\n"
        "echo.\n"
        "echo   ============================================================\n"
        "echo     MV Kobra AI - Edicion OWNER\n"
        "echo     Convierte la copia YA INSTALADA en la del dueno:\n"
        "echo     sin clave, sin trial y sin vencimiento.\n"
        "echo.\n"
        "echo     Lo mas simple: copia este archivo a la carpeta donde esta\n"
        "echo     el programa y hace doble clic.\n"
        "echo   ============================================================\n"
        "echo.\n"
        "\n"
        "set \"INTERNO=\"\n"
        "\n"
        "rem 1) La carpeta donde esta ESTE archivo. Es el caso normal: se copia\n"
        "rem    el .bat junto al programa y se hace doble clic. Se contemplan\n"
        "rem    las tres alturas posibles de la instalacion.\n"
        "if not defined INTERNO call :probar \"%~dp0.\"\n"
        "if not defined INTERNO if exist \"%~dp0_internal\\\" "
        "set \"INTERNO=%~dp0_internal\"\n"
        "if not defined INTERNO if exist \"%~dp0base_library.zip\" "
        "set \"INTERNO=%~dp0.\"\n"
        "\n"
        "rem 2) Una carpeta arrastrada sobre el .bat.\n"
        "if not defined INTERNO if not \"%~1\"==\"\" call :probar \"%~1\"\n"
        "\n"
        "rem 3) Y por ultimo las rutas donde instala el .exe por defecto.\n"
        + busqueda +
        "\n"
        "if not defined INTERNO (\n"
        "  echo   No encontre la instalacion de MV Kobra AI.\n"
        "  echo.\n"
        "  echo   Copia este archivo a la carpeta donde esta el programa\n"
        "  echo   ^(la que tiene \"MV Kobra AI.exe\"^) y hace doble clic ahi.\n"
        "  echo   Tambien podes arrastrar esa carpeta sobre este archivo.\n"
        "  echo.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "\n"
        "echo   Instalacion encontrada:\n"
        "echo     !INTERNO!\n"
        "echo.\n"
        "\n"
        "rem El sello es lo unico que separa la copia del dueno de la de un\n"
        "rem cliente. Va en _internal porque eso es sys._MEIPASS del bundle\n"
        "rem congelado, que es de donde kobra\\edicion.py lo lee al arrancar.\n"
        "rem Se escribe con redireccion cruda: sin BOM (json.load falla con BOM)\n"
        "rem y sin que batch tenga que escapar nada del JSON.\n"
        f">\"!INTERNO!\\edicion.json\" echo {SELLO}\n"
        "\n"
        "rem Verificar lo que quedo escrito. Sin esto, un permiso denegado o el\n"
        "rem programa abierto terminarian en un \"listo\" que no es cierto.\n"
        "findstr /i /c:\"owner\" \"!INTERNO!\\edicion.json\" >nul 2>&1\n"
        "if errorlevel 1 (\n"
        "  echo   ERROR: no pude escribir el sello.\n"
        "  echo   Cerra MV Kobra AI si esta abierto y proba de nuevo.\n"
        "  echo.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "\n"
        "echo   Listo: esta copia quedo en edicion OWNER.\n"
        "echo   Abrila normalmente: entra directo, sin pedir ninguna clave.\n"
        "echo.\n"
        "pause\n"
        "exit /b 0\n"
        "\n"
        ":probar\n"
        "if exist \"%~1\\resources\\backend\\_internal\\\" "
        "set \"INTERNO=%~1\\resources\\backend\\_internal\"\n"
        "goto :eof\n")


def main() -> None:
    # newline="" + \n en el contenido: `_write` de build_release.py hace lo
    # mismo. Escribir \r\n a mano acá dejaría \r\r\n y cmd.exe se confunde.
    with open(SALIDA, "w", encoding="ascii", newline="\r\n") as f:
        f.write(_bat())
    print(f"[OK] {SALIDA}  ({os.path.getsize(SALIDA)} bytes)")


if __name__ == "__main__":
    main()
