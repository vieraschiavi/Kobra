# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para kobra-api.exe: el motor de MV Kobra AI (kobra/,
backend_venta/, data/) servido por FastAPI, SIN Streamlit — es lo que
Electron levanta como proceso hijo en la app de escritorio.

A diferencia de packaging/kobra.spec (que empaqueta el panel Streamlit
completo), este .spec es liviano: nada de streamlit/plotly/altair.

Construir (en Windows, parado en INSTALADOR/app/pyapi/):
    pyinstaller kobra_api.spec --noconfirm
    # genera dist/kobra-api/kobra-api.exe (onedir)
"""
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

# ROOT = raíz del repo Kobra (4 niveles arriba de este .spec:
# pyapi -> app -> INSTALADOR -> Kobra)
ROOT = os.path.abspath(os.path.join(os.getcwd(), "..", "..", ".."))

_PAQUETES = ["fastapi", "starlette", "uvicorn", "pandas", "numpy", "sklearn", "scipy", "joblib"]
datas, binaries, hiddenimports = [], [], []
for _pkg in _PAQUETES:
    try:
        d, b, h = collect_all(_pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

for _pkg in ["pandas", "numpy", "scikit-learn"]:
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass


def _dir(nombre):
    ruta = os.path.join(ROOT, nombre)
    return (ruta, nombre) if os.path.isdir(ruta) else None


for _n in ["kobra", "backend_venta", "data"]:
    par = _dir(_n)
    if par:
        datas.append(par)

a = Analysis(
    ["server.py"],
    pathex=[ROOT, os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="kobra-api",
    console=False,
    icon=os.path.join(ROOT, "INSTALADOR", "app", "build", "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="kobra-api")
