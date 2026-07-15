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


def _abrir_navegador(url: str):
    # Espera a que el server levante y abre el navegador una sola vez.
    for _ in range(60):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            continue
    webbrowser.open(url)


def main():
    base = _base_dir()

    # Modo standalone: la app pide licencia (compra o trial), no contraseña.
    os.environ["KOBRA_MODO_STANDALONE"] = "1"
    port = os.environ.get("KOBRA_APP_PORT") or str(_puerto_libre())
    os.environ["KOBRA_APP_PORT"] = port
    # Que los import del proyecto (kobra, webapp, backend_venta, data) resuelvan.
    if base not in sys.path:
        sys.path.insert(0, base)

    # UI compilada: si no está el build normal de Vite (correr desde código sin
    # haber pasado por Node), caer al build versionado en owner/ui_dist para que
    # la interfaz igual se sirva sin necesidad de instalar Node.
    if not os.environ.get("KOBRA_UI_DIST"):
        _dist_normal = os.path.join(base, "webapp", "frontend", "dist")
        _dist_owner = os.path.join(base, "owner", "ui_dist")
        if not os.path.isdir(_dist_normal) and os.path.isdir(_dist_owner):
            os.environ["KOBRA_UI_DIST"] = _dist_owner

    threading.Thread(target=_abrir_navegador,
                     args=(f"http://localhost:{port}",), daemon=True).start()

    import uvicorn
    from webapp.backend.api import app
    uvicorn.run(app, host="127.0.0.1", port=int(port), log_level="warning")


if __name__ == "__main__":
    main()
