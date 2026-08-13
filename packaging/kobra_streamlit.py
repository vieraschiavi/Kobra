# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Lanzador del dashboard Streamlit (edición Producción)
===================================================================
La edición Producción sirve el dashboard gerencial con Streamlit, no con el
FastAPI embebido de la app de escritorio (ese es `kobra_launcher.py`).

Existe para dos cosas que el `streamlit run` pelado no hace:

1. **No pisar puertos.** Streamlit arranca en 8501 fijo y, si está ocupado,
   o falla o se corre solo sin avisar. Acá se elige un puerto libre de verdad
   antes de levantar nada (ver `kobra/red.py`).
2. **Ser un destino de acceso directo.** El instalador de Windows crea el
   icono apuntando a un archivo Python; necesita uno que arranque el
   dashboard sin que el usuario tipee un comando.
"""
import os
import sys


def _base_dir() -> str:
    """Carpeta raíz del programa (la que contiene `kobra/` y `app/`).

    Misma lógica que `kobra_launcher.py::_base_dir`, y por el mismo motivo: en
    el repo este archivo está en `packaging/` (la raíz es el padre) y en el ZIP
    de una edición está en la raíz de `kobra_software/` (la raíz es su propia
    carpeta). Subir siempre un nivel hacía que en el ZIP no se encontrara
    `app/app.py` y el dashboard no abriera nunca. Se elige por CONTENIDO.
    """
    empaquetado = getattr(sys, "_MEIPASS", None)
    if empaquetado:
        return empaquetado
    aqui = os.path.dirname(os.path.abspath(__file__))
    for candidata in (aqui, os.path.dirname(aqui)):
        if os.path.isdir(os.path.join(candidata, "kobra")):
            return candidata
    return os.path.dirname(aqui)


def main() -> int:
    base = _base_dir()
    if base not in sys.path:
        sys.path.insert(0, base)

    # La edición (Demo con límite de días, Owner sin límites, o un plan) se
    # aplica ACÁ además de en la app de escritorio. Sin esto, abrir la Demo
    # por el dashboard salteaba su propio vencimiento — ver kobra/edicion.py.
    from kobra import edicion as kedicion
    kedicion.activar(base)

    from kobra import red as kred

    puerto = os.environ.get("KOBRA_APP_PORT")
    if not puerto:
        puerto = str(kred.puerto_libre(kred.PUERTOS_STREAMLIT))
    os.environ["KOBRA_APP_PORT"] = puerto

    app = os.path.join(base, "app", "app.py")
    if not os.path.exists(app):
        print(f"No encontre el dashboard en {app}", file=sys.stderr)
        return 1

    opciones = [
        "run", app,
        "--server.port", puerto,
        "--server.address", "127.0.0.1",
        "--browser.gatherUsageStats", "false",
    ]

    # `streamlit.web.cli` en proceso y no un subprocess: así el acceso directo
    # tiene un solo proceso, y cerrarlo cierra el servidor (con subprocess
    # quedaba el server huérfano y el puerto tomado hasta reiniciar).
    #
    # El fallback existe porque ese módulo es interno de Streamlit y ya se mudó
    # una vez (`streamlit.cli` -> `streamlit.web.cli` en 1.12). `python -m
    # streamlit` es la interfaz pública y no se mueve: si el import interno
    # falla, arrancar igual es mejor que no abrir.
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        import subprocess
        return subprocess.call([sys.executable, "-m", "streamlit", *opciones])

    sys.argv = ["streamlit", *opciones]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
