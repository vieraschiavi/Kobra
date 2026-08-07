"""
MV Kobra AI · Armado del instalador de escritorio (Electron)
================================================================
Orquesta los 3 pasos para producir el .exe final. Tiene que correr en
Windows (PyInstaller no cruza de plataforma: un .exe de Windows se compila
en Windows) con Python y Node.js instalados.

Uso:
    python scripts/build_installer.py cliente
    python scripts/build_installer.py owner

Qué hace:
    1. pyinstaller kobra_api.spec              -> dist/kobra-api/ (motor Python, sin Streamlit)
    2. copia ese resultado a app/resources/kobra-api/
    3. npm install (primera vez) + node scripts/prep-edition.js <edicion>
    4. npx electron-builder --win nsis          -> dist/MV-Kobra-AI-<edicion>-Setup-*.exe
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # INSTALADOR/scripts
INSTALADOR = HERE.parent                        # INSTALADOR/
APP = INSTALADOR / "app"
PYAPI = APP / "pyapi"


def run(cmd, cwd):
    print(f"\n$ {' '.join(cmd)}   (en {cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("cliente", "owner"):
        print("Uso: python scripts/build_installer.py <cliente|owner>")
        sys.exit(1)
    edicion = sys.argv[1]

    print(f"== MV Kobra AI · armando instalador \"{edicion}\" ==")

    # 1) Motor Python -> exe standalone (sin Streamlit)
    run(["pyinstaller", "kobra_api.spec", "--noconfirm"], cwd=PYAPI)

    # 2) Copiar el resultado a los recursos de Electron
    origen = PYAPI / "dist" / "kobra-api"
    destino = APP / "resources" / "kobra-api"
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origen, destino)
    print(f"✔ Motor copiado a {destino}")

    # 3) Dependencias de Electron + config de edición
    if not (APP / "node_modules").exists():
        run(["npm", "install"], cwd=APP)
    run(["node", "scripts/prep-edition.js", edicion], cwd=APP)

    # 4) Empaquetar con electron-builder
    run(["npx", "electron-builder", "--win", "nsis", "--config", "electron-builder.yml"], cwd=APP)

    print(f"\n✔ Listo. Instalador en {APP / 'dist'}")


if __name__ == "__main__":
    main()
