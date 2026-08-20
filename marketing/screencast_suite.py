# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Screencast real de los módulos de la suite
=========================================================
Graba un recorrido REAL por las pantallas nuevas —tablero conversacional,
gobernanza, medidas, AutoML, logística y proyectos— contra la aplicación
corriendo de verdad, con Playwright. No es una animación de marketing: lo que
se ve en el video es lo que hace el producto, que es el mismo criterio del
screencast de MV Data Governance.

Produce `landing/video/MVKobraAI_Suite_Demo.webm` (Playwright graba webm
nativo — no requiere ffmpeg). Los subtítulos en los tres idiomas salen de
`marketing/subtitulos.py` (cues SUITE), sincronizados con las duraciones de
acá: si se cambia un tramo, regenerar los .vtt.

La voz en tres idiomas NO se sintetiza acá a propósito: requiere
`ELEVENLABS_API_KEY`, que no se guarda en el repo. El guion de narración vive
en los mismos cues; con la clave cargada, `python3 -m marketing.voz_suite`
renderiza los MP3 con la voz real del producto (`kobra/voz_tts.py`).

Uso:  python3 -m marketing.screencast_suite [salida.webm]
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA_DEFAULT = os.path.join(RAIZ, "landing", "video", "MVKobraAI_Suite_Demo.webm")

# El recorrido: (ruta del hash router, segundos en pantalla). Las duraciones
# son la fuente de verdad de los tiempos de los subtítulos (subtitulos.py).
RECORRIDO = [
    ("/", 6),             # visión general: el producto que ya se conocía
    ("/tablero", 8),      # tablero conversacional
    ("/gobernanza", 8),   # clasificación, calidad DAMA, integridad
    ("/medidas", 7),      # KPIs con fórmulas propias
    ("/automl", 7),       # entrenar con datos propios
    ("/logistica", 8),    # módulo suelto: ofertas/reposición
    ("/proyectos", 8),    # módulo suelto: salud y backlog
]
VIEWPORT = {"width": 1280, "height": 800}   # igual que MVKobraAI_Demo_Real


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _preparar_datos(dir_datos: str) -> None:
    """Datos sintéticos para que cada pantalla muestre contenido real.

    La cartera scoreada sale del pipeline (outputs/); las tablas de logística
    y proyectos se generan acá con la MISMA forma que validan sus módulos —
    un screencast de pantallas vacías no muestra el producto.
    """
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(42)          # seed fija, como todo en el repo

    outputs = os.path.join(dir_datos, "outputs")
    os.makedirs(outputs, exist_ok=True)
    shutil.copy(os.path.join(RAIZ, "outputs", "kobra_scored.csv"),
                os.path.join(outputs, "kobra_scored.csv"))

    n = 40
    productos = pd.DataFrame({
        "sku": [f"SKU-{i:03d}" for i in range(n)],
        "nombre": [f"Producto {i:03d}" for i in range(n)],
        "categoria": rng.choice(["Filtros", "Lubricantes", "Correas", "Baterías"], n),
        "proveedor": rng.choice(["Norte SRL", "Central SA", "Import UY"], n),
        "precio": rng.uniform(80, 900, n).round(2),
        "costo": rng.uniform(40, 500, n).round(2),
        "stock": rng.integers(0, 800, n),
        "stock_min": rng.integers(10, 60, n),
        "lead_time_dias": rng.integers(3, 20, n),
    })
    fechas = pd.date_range("2026-02-01", "2026-08-01", freq="D")
    ventas = pd.DataFrame({
        "fecha": rng.choice(fechas, 1200),
        "sku": rng.choice(productos["sku"], 1200),
        "cantidad": rng.integers(1, 6, 1200),
        "cliente_id": rng.choice([f"C-{i:02d}" for i in range(25)], 1200),
        "venta_id": [f"V-{i:05d}" for i in range(1200)],
        "zona": rng.choice(["Norte", "Sur", "Este", "Oeste"], 1200),
    })
    proyectos = pd.DataFrame({
        "proyecto_id": [f"P{i}" for i in range(1, 6)],
        "nombre": ["Migración ERP", "Portal clientes", "App móvil",
                   "Integración BI", "Onboarding digital"],
        "dueno": ["Ana", "Beto", "Carla", "Ana", "Diego"],
        "criticidad": ["Alta", "Media", "Alta", "Baja", "Media"],
        "presupuesto": [100000.0, 50000.0, 80000.0, 30000.0, 45000.0],
        "ejecutado": [60000.0, 52000.0, 81000.0, 10000.0, 20000.0],
    })
    nt = 40
    tareas = pd.DataFrame({
        "tarea_id": [f"T{i:03d}" for i in range(nt)],
        "proyecto_id": rng.choice(proyectos["proyecto_id"], nt),
        "titulo": [f"Tarea {i:03d}" for i in range(nt)],
        "estado": rng.choice(["todo", "in_progress", "blocked", "done"], nt,
                             p=[0.4, 0.25, 0.1, 0.25]),
        "responsable": rng.choice(["Ana", "Beto", "Carla", "Diego", None], nt),
        "prioridad": rng.choice(["Alta", "Media", "Baja"], nt),
        "vencimiento": rng.choice(pd.date_range("2026-07-01", "2026-11-30"), nt),
        "depende_de": [None] * nt,
    })
    equipo = pd.DataFrame({
        "nombre": ["Ana", "Beto", "Carla", "Diego"],
        "capacidad_semanal_hs": [40, 40, 40, 40],
        "carga_actual_hs": [38, 55, 30, 42],
    })
    for nombre, df in [("logistica_productos", productos),
                       ("logistica_ventas", ventas),
                       ("proyectos_proyectos", proyectos),
                       ("proyectos_tareas", tareas),
                       ("proyectos_equipo", equipo)]:
        df.to_csv(os.path.join(outputs, f"{nombre}.csv"), index=False)


def grabar(salida: str = SALIDA_DEFAULT) -> str:
    from playwright.sync_api import sync_playwright

    puerto = _puerto_libre()
    tmp = tempfile.mkdtemp(prefix="screencast_")
    _preparar_datos(os.path.join(tmp, "datos"))

    # La app real, en modo owner: todas las pantallas habilitadas sin tocar
    # licencias — es la copia del dueño, la misma con la que se demuestra.
    entorno = {**os.environ,
               "KOBRA_CONFIG_DIR": os.path.join(tmp, "config"),
               "KOBRA_DATA_DIR": os.path.join(tmp, "datos"),
               "KOBRA_MODO_STANDALONE": "1", "KOBRA_OWNER": "1"}
    servidor = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.backend.api:app",
         "--port", str(puerto), "--log-level", "warning"],
        cwd=RAIZ, env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{puerto}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("el servidor no arrancó")

        with sync_playwright() as p:
            # Si hay un Chromium del sistema (p. ej. /opt/pw-browsers/chromium,
            # el del entorno de CI/nube), se usa ese: la revisión que descarga
            # cada versión de Playwright puede no estar instalada.
            eje = shutil.which("chromium", path="/opt/pw-browsers") or None
            navegador = p.chromium.launch(executable_path=eje)
            ctx = navegador.new_context(viewport=VIEWPORT,
                                        record_video_dir=tmp,
                                        record_video_size=VIEWPORT)
            pagina = ctx.new_page()
            # El tour de bienvenida se marca como visto ANTES de cargar la app:
            # si no, el modal tapa todas las pantallas del video.
            pagina.add_init_script("localStorage.setItem('kobra_tour_visto','1')")
            # En modo owner el frontend entra solo (owner-login automático).
            pagina.goto(f"{base}/#/", wait_until="networkidle")
            for ruta, segundos in RECORRIDO:
                pagina.goto(f"{base}/#{ruta}")
                try:
                    pagina.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass                       # una pantalla lenta no corta el video
                pagina.wait_for_timeout(segundos * 1000)
            video = pagina.video
            ctx.close()                        # cierra y vuelca el webm
            crudo = video.path()
            navegador.close()

        os.makedirs(os.path.dirname(salida), exist_ok=True)
        shutil.move(crudo, salida)
        return salida
    finally:
        servidor.terminate()


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else SALIDA_DEFAULT
    ruta = grabar(destino)
    mb = os.path.getsize(ruta) / 1e6
    print(f"[OK] {ruta}  ({mb:.1f} MB)")
    print("Subtítulos: python3 -m marketing.subtitulos  (genera suite.*.vtt)")
    print("Voz (con ELEVENLABS_API_KEY): python3 -m marketing.voz_suite")
