"""
Kobra IA · Lanzador del programa standalone (Windows)
=====================================================
Punto de entrada del ejecutable empaquetado con PyInstaller. Arranca el
dashboard Streamlit embebido (sin necesidad de tener Python instalado) y abre
el navegador. Es lo que se ejecuta cuando el usuario hace doble clic en el
acceso directo "Kobra IA" que crea el instalador.
"""
import os
import sys
import threading
import time
import webbrowser


def _base_dir() -> str:
    """Carpeta con los recursos (dentro del bundle PyInstaller o del repo)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    app_path = os.path.join(base, "app", "app.py")

    # Config de Streamlit para modo "programa" (no dev, no telemetría).
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_SERVER_PORT", "8501")
    # Que los import del proyecto (kobra, realtime, data) resuelvan.
    if base not in sys.path:
        sys.path.insert(0, base)

    port = os.environ.get("STREAMLIT_SERVER_PORT", "8501")
    threading.Thread(target=_abrir_navegador,
                     args=(f"http://localhost:{port}",), daemon=True).start()

    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", app_path,
                f"--server.port={port}",
                "--server.headless=true",
                "--global.developmentMode=false",
                "--browser.gatherUsageStats=false"]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
