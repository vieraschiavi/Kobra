# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para el programa standalone de MV Kobra AI (Windows, onedir).
Empaqueta el intérprete Python, todas las dependencias (Streamlit, scikit-learn,
plotly, pandas, FastAPI…) y el código/datos de MV Kobra AI en dist/MVKobraAI/, que
luego el instalador Inno Setup convierte en MVKobraAI_Setup.exe.

Construir (en Windows):
    pyinstaller packaging/kobra.spec --noconfirm
"""
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = os.path.abspath(os.getcwd())

# --- Dependencias que necesitan recolección completa (datos + submódulos) ---
_PAQUETES = [
    "streamlit", "plotly", "altair", "pandas", "numpy", "sklearn",
    "scipy", "pyarrow", "xlsxwriter", "openpyxl", "joblib",
    "fastapi", "starlette", "uvicorn", "pptx", "soundfile", "apscheduler",
]
datas, binaries, hiddenimports = [], [], []
for _pkg in _PAQUETES:
    try:
        d, b, h = collect_all(_pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Metadata que algunas libs leen en runtime (importlib.metadata)
for _pkg in ["streamlit", "altair", "plotly", "pandas", "numpy",
             "scikit-learn", "pyarrow"]:
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

# --- Código y recursos propios de MV Kobra AI ---
def _dir(nombre):
    ruta = os.path.join(ROOT, nombre)
    return (ruta, nombre) if os.path.isdir(ruta) else None

for _n in ["app", "kobra", "realtime", "data", "assets",
           "dashboard_estatico", "outputs", "presentation", "docs"]:
    par = _dir(_n)
    if par:
        datas.append(par)

hiddenimports += [
    "kobra", "kobra.probpago", "kobra.negociador", "kobra.copiloto",
    "kobra.analitica", "kobra.cumplimiento", "kobra.explicabilidad",
    "kobra.roi", "kobra.cartera_manual", "kobra.registro", "kobra.config",
    "kobra.gestor_ia", "kobra.pipeline", "kobra.voz", "kobra.train",
    "kobra.consulta_bd", "kobra.seguimiento", "kobra.voz_tts", "kobra.campana",
    "kobra.twilio_setup",
    "realtime.mi_cartera", "realtime.voicebot", "sklearn.utils._typedefs",
    "sklearn.neighbors._partition_nodes", "sklearn.utils._heap",
]

_ICON = os.path.join(ROOT, "assets", "brand", "mv.ico")
_icon = _ICON if os.path.exists(_ICON) else None

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "packaging", "kobra_launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "referencia_R"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MVKobraAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # muestra una consola con el log del server
    icon=_icon,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="MVKobraAI",
)
