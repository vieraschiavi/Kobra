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
           "dashboard_estatico", "outputs", "presentation", "docs",
           "backend_venta"]:
    par = _dir(_n)
    if par:
        datas.append(par)

# webapp/: solo el backend (código) y el build compilado del frontend —
# NUNCA webapp/frontend/node_modules ni src/ (fuente sin compilar, cientos de
# MB innecesarios). El build (`npm run build`) corre antes en el workflow de
# CI; si no existe todavía (build local sin haber compilado el frontend),
# el backend sigue funcionando como API pura, solo sin servir la UI.
_webapp_backend = _dir(os.path.join("webapp", "backend"))
if _webapp_backend:
    datas.append(_webapp_backend)
_webapp_dist = os.path.join(ROOT, "webapp", "frontend", "dist")
if os.path.isdir(_webapp_dist):
    datas.append((_webapp_dist, os.path.join("webapp", "frontend", "dist")))

# README.md suelto: es la fuente principal del asistente de ayuda (kobra/ayuda.py)
_readme = os.path.join(ROOT, "README.md")
if os.path.isfile(_readme):
    datas.append((_readme, "."))

# edicion.json: si está, `kobra_launcher.py::_activar_edicion` la lee al
# arrancar y aplica la edición (owner sin licencia, o un plan con su token).
# El build de CLIENTES no la genera, así que este bloque no hace nada ahí; el
# workflow `release_owner.yml` la escribe antes de correr PyInstaller para
# armar el instalador del dueño. Va a la raíz del bundle porque es donde
# `_base_dir()` (o sea `sys._MEIPASS`) la busca.
_edicion = os.path.join(ROOT, "edicion.json")
if os.path.isfile(_edicion):
    datas.append((_edicion, "."))

# Todos los módulos de `kobra/`, enumerados del paquete y NO a mano.
#
# Esta lista estaba escrita a mano y se desfasó: quedaron afuera 9 módulos, y
# entre ellos `kobra.owner` y `kobra.limitador`, que `webapp/backend/api.py`
# importa al arrancar. Si PyInstaller no los empaqueta, el backend no levanta,
# la app se queda en el splash hasta el timeout y el usuario ve un instalador
# que "no funciona" — sin ninguna pista de por qué.
#
# Enumerarlos evita que agregar un módulo nuevo rompa el instalador dos
# semanas después, que es justo lo que pasó. `tests/test_empaquetado.py`
# verifica que la enumeración cubra el paquete entero.
_KOBRA_DIR = os.path.join(ROOT, "kobra")
hiddenimports += ["kobra"] + sorted(
    f"kobra.{f[:-3]}" for f in os.listdir(_KOBRA_DIR)
    if f.endswith(".py") and f != "__init__.py"
)

hiddenimports += [
    "realtime.mi_cartera", "realtime.voicebot", "sklearn.utils._typedefs",
    "sklearn.neighbors._partition_nodes", "sklearn.utils._heap",
    # App completa (React + FastAPI) que sirve kobra_launcher.py — reemplaza
    # a Streamlit como lo que abre el instalador por default.
    "webapp", "webapp.backend", "webapp.backend.api",
    "backend_venta", "backend_venta.licencias",
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
