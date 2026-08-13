# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Genera `packaging/Instalar_en_otro_disco.bat`
===========================================================
Instala el programa SIN tocar el disco C:, ni siquiera para archivos
temporales.

El problema que resuelve
------------------------
Un instalador de Windows hecho con NSIS —el nuestro y el de casi todo el
mundo— se auto-descomprime en `%TEMP%` antes de mostrar la primera pantalla:
ahí van sus plugins (`LangDLL.dll`, etc.) y ahí se apoya para descomprimir el
payload. Si `%TEMP%` apunta a C: y C: está sin espacio, o el antivirus bloquea
esa carpeta, el instalador muere con:

    Extrayendo: error escribiendo al archivo
    C:\\Users\\<usuario>\\AppData\\Local\\Temp\\nsXXXX.tmp\\LangDLL.dll

y nunca llega a preguntar dónde instalar. Por eso elegir la carpeta de destino
—que el instalador SÍ permite— no alcanza: el problema es anterior.

No se puede compilar un .exe que no use `%TEMP%`; es cómo funciona el
auto-extractor. Lo que sí se puede es **apuntar `%TEMP%` a otro disco antes de
lanzarlo**, que es exactamente lo que hace este .bat: crea una carpeta de
trabajo al lado de sí mismo, define `TEMP`/`TMP` ahí, corre el instalador y
después limpia. Si el .bat y el .exe están en D:, el disco C: no se toca en
ningún momento del proceso.

Uso:
    python packaging/generar_instalar_bat.py
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(ROOT, "packaging", "Instalar_en_otro_disco.bat")

# Nombre de la carpeta temporal, al lado del .bat. Se borra al terminar.
CARPETA_TMP = "kobra_temp_instalacion"


def _bat() -> str:
    return (
        "@echo off\n"
        "setlocal enabledelayedexpansion\n"
        "title MV Kobra AI - Instalar sin usar el disco C\n"
        "echo.\n"
        "echo   ============================================================\n"
        "echo     MV Kobra AI - Instalacion en el disco que vos elijas\n"
        "echo.\n"
        "echo     Windows descomprime todo instalador en la carpeta temporal\n"
        "echo     ^(normalmente en C:^) antes de abrir la primera pantalla.\n"
        "echo     Si C: esta lleno o el antivirus la bloquea, falla ahi.\n"
        "echo     Este archivo manda esa carpeta temporal al MISMO disco\n"
        "echo     donde esta guardado.\n"
        "echo   ============================================================\n"
        "echo.\n"
        "\n"
        "rem --- 1) Buscar el instalador ---------------------------------------\n"
        "rem Se acepta arrastrado sobre este .bat, o al lado de este .bat.\n"
        "set \"SETUP=\"\n"
        "if not \"%~1\"==\"\" if exist \"%~1\" set \"SETUP=%~1\"\n"
        "if not defined SETUP for %%F in (\"%~dp0MVKobraAI_Setup_OWNER.exe\") do "
        "if exist \"%%~F\" set \"SETUP=%%~F\"\n"
        "if not defined SETUP for %%F in (\"%~dp0MVKobraAI_Setup.exe\") do "
        "if exist \"%%~F\" set \"SETUP=%%~F\"\n"
        "\n"
        "if not defined SETUP (\n"
        "  echo   No encontre el instalador.\n"
        "  echo.\n"
        "  echo   Copia este archivo a la MISMA carpeta donde bajaste\n"
        "  echo   MVKobraAI_Setup.exe ^(o el _OWNER^) y hace doble clic aca.\n"
        "  echo   Tambien podes arrastrar el .exe sobre este archivo.\n"
        "  echo.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "\n"
        "rem --- 2) Carpeta temporal en ESTE disco ------------------------------\n"
        f"set \"TRABAJO=%~dp0{CARPETA_TMP}\"\n"
        "if not exist \"!TRABAJO!\" mkdir \"!TRABAJO!\" 2>nul\n"
        "if not exist \"!TRABAJO!\" (\n"
        "  echo   No pude crear la carpeta de trabajo:\n"
        "  echo     !TRABAJO!\n"
        "  echo   Copia este archivo y el instalador a una carpeta donde\n"
        "  echo   tengas permiso de escritura ^(por ejemplo D:\\MVKobra^).\n"
        "  echo.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "\n"
        "rem Solo para ESTE proceso y sus hijos: no cambia la config de Windows.\n"
        "set \"TEMP=!TRABAJO!\"\n"
        "set \"TMP=!TRABAJO!\"\n"
        "\n"
        "echo   Instalador : !SETUP!\n"
        "echo   Temporales : !TEMP!\n"
        "echo.\n"
        "echo   Se abre el asistente. Cuando pregunte la carpeta de destino,\n"
        "echo   elegi una de este mismo disco para no usar C: en absoluto.\n"
        "echo.\n"
        "\n"
        "rem --- 3) Correr el instalador y esperar ------------------------------\n"
        "start \"\" /wait \"!SETUP!\"\n"
        "set \"CODIGO=!errorlevel!\"\n"
        "\n"
        "rem --- 4) Limpiar --------------------------------------------------\n"
        "rd /s /q \"!TRABAJO!\" 2>nul\n"
        "\n"
        "echo.\n"
        "if \"!CODIGO!\"==\"0\" (\n"
        "  echo   Listo. El instalador termino sin errores.\n"
        ") else (\n"
        "  echo   El instalador termino con codigo !CODIGO!.\n"
        "  echo   Si volvio a fallar escribiendo archivos, revisa que el disco\n"
        "  echo   donde esta este archivo tenga espacio libre, y agrega la\n"
        "  echo   carpeta a las exclusiones del antivirus.\n"
        ")\n"
        "echo.\n"
        "pause\n")


def main() -> None:
    # ascii + newline CRLF: un .bat con BOM no lo abre cmd.exe, y escribir
    # \r\n a mano sobre newline="" deja \r\r\n. Mismo criterio que Owner.bat.
    with open(SALIDA, "w", encoding="ascii", newline="\r\n") as f:
        f.write(_bat())
    print(f"[OK] {SALIDA}  ({os.path.getsize(SALIDA)} bytes)")


if __name__ == "__main__":
    main()
