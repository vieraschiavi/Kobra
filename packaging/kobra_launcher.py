"""
MV Kobra AI · Lanzador del programa standalone (Windows)
=====================================================
Punto de entrada del ejecutable empaquetado con PyInstaller. Arranca la app
completa (React + FastAPI, la misma interfaz que corre en la nube) embebida
— un solo proceso sirve tanto la UI compilada como la API — y abre el
navegador. Es lo que se ejecuta cuando el usuario hace doble clic en el
acceso directo "MV Kobra AI" que crea el instalador.

El acceso a esta copia local se gatea por LICENCIA (la que se recibe al
comprar, o el trial de 3 días de la demo), no por una contraseña de
administrador — ver webapp/backend/api.py::MODO_STANDALONE. La propia app
pide la licencia sola en el primer arranque, sin pasos previos.
"""
import os
import socket
import sys
import threading
import time
import webbrowser


def _base_dir() -> str:
    """Carpeta con los recursos (dentro del bundle PyInstaller o del repo)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _puerto_libre() -> int:
    """Elige un puerto libre para no chocar con otros programas. Prueba unos
    puertos propios de MV Kobra AI y, si están ocupados, pide uno efímero al
    sistema operativo."""
    for p in (8531, 8542, 8553, 8564, 8575):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _abrir_ventana_app(url: str) -> bool:
    """Abre en modo 'app' (ventana limpia, sin barra de navegador — se ve como
    una app de escritorio) usando Chrome o Edge, que están en casi todo Windows.
    Devuelve True si lo logró; si no hay ninguno, el llamador cae al navegador
    normal. No suma peso (no es Electron): reusa el navegador ya instalado."""
    import shutil
    import subprocess
    candidatos = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        shutil.which("chrome"), shutil.which("msedge"),
        shutil.which("google-chrome"), shutil.which("chromium"),
    ]
    for exe in candidatos:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--new-window"])
                return True
            except Exception:
                continue
    return False


def _abrir_navegador(url: str):
    # Espera a que el server levante y abre la app una sola vez.
    for _ in range(60):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            continue
    # Modo ventana-app (más profesional: ventana limpia sin barra del navegador).
    # Default en Windows (Edge está siempre) para que el cliente con el .exe
    # también lo tenga; se puede forzar/desactivar con KOBRA_APP_WINDOW=1/0.
    flag = os.environ.get("KOBRA_APP_WINDOW")
    quiere_app = flag == "1" or (flag != "0" and sys.platform == "win32")
    if quiere_app and _abrir_ventana_app(url):
        return
    webbrowser.open(url)


def _activar_edicion(base: str):
    """Si el paquete trae una `edicion.json` (demo con límite de días, owner o
    un plan puntual), activa esa edición antes de levantar la app:
      - owner  → KOBRA_OWNER=1 (sin licencia, sin vencimiento).
      - demo/plan → siembra el secreto de firma y el token de licencia embebidos
        en la config del usuario, así la app valida y aplica el límite de días /
        cupo / features del plan sin que el prospecto tenga que activar nada.
    Es idempotente: solo siembra el token la primera vez (no pisa uno activado
    después por el usuario)."""
    ruta = os.path.join(base, "edicion.json")
    if not os.path.exists(ruta):
        return
    try:
        import json
        with open(ruta, encoding="utf-8") as f:
            ed = json.load(f)
    except (OSError, ValueError):
        return
    if ed.get("owner"):
        os.environ["KOBRA_OWNER"] = "1"
        return
    secreto, token = ed.get("secreto"), ed.get("token")
    if secreto:
        os.environ.setdefault("KOBRA_LICENSE_SECRET", secreto)
    if token:
        try:
            if base not in sys.path:
                sys.path.insert(0, base)
            from kobra import config as kconfig
            if not kconfig.leer_extra("LICENCIA_TOKEN"):
                kconfig.guardar_extra("LICENCIA_TOKEN", token)
        except Exception:
            pass


def main():
    base = _base_dir()

    # Modo standalone: la app pide licencia (compra o trial), no contraseña.
    os.environ["KOBRA_MODO_STANDALONE"] = "1"
    _activar_edicion(base)
    port = os.environ.get("KOBRA_APP_PORT") or str(_puerto_libre())
    os.environ["KOBRA_APP_PORT"] = port
    # Que los import del proyecto (kobra, webapp, backend_venta, data) resuelvan.
    if base not in sys.path:
        sys.path.insert(0, base)

    # Primer arranque instalado: copia la demo sintética (data/, outputs/)
    # bundleada a la carpeta de datos escribible del usuario (nunca Program
    # Files). Ver kobra/rutas.py — sin esto, la demo no aparece la 1a vez.
    from kobra import rutas as krutas
    krutas.sembrar_si_hace_falta()

    # UI compilada: si no está el build normal de Vite (correr desde código sin
    # haber pasado por Node), caer al build versionado en owner/ui_dist para que
    # la interfaz igual se sirva sin necesidad de instalar Node.
    if not os.environ.get("KOBRA_UI_DIST"):
        _dist_normal = os.path.join(base, "webapp", "frontend", "dist")
        _dist_owner = os.path.join(base, "owner", "ui_dist")
        if not os.path.isdir(_dist_normal) and os.path.isdir(_dist_owner):
            os.environ["KOBRA_UI_DIST"] = _dist_owner

    # Dentro de la app Electron (electron/main.js) la ventana la maneja
    # Electron: acá no hay que abrir además un navegador.
    if os.environ.get("KOBRA_SIN_NAVEGADOR") != "1":
        threading.Thread(target=_abrir_navegador,
                         args=(f"http://localhost:{port}",), daemon=True).start()

    import uvicorn

    from webapp.backend.api import app
    uvicorn.run(app, host="127.0.0.1", port=int(port), log_level="warning")


if __name__ == "__main__":
    main()
