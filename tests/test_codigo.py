# © 2026 Martín Viera. Todos los derechos reservados.
"""Eje CÓDIGO: cero warnings de deprecación y cobertura de los módulos de dinero.

Corriendo la suite completa con las advertencias de deprecación elevadas a
error, salían 3 (no 10 — el resto del "warnings summary" normal son cosas que
no son DeprecationWarning, como el `UserWarning` de xlsxwriter al mergear una
celda sola):

    realtime/server.py:74     @app.on_event("startup")   — deprecado en FastAPI
    tests/test_kobra.py:403   import audioop             — deprecado en 3.11+,
                                                             se elimina en 3.13
    marketing/vectorizar_marca.py:88   np.cross(2D, 2D)   — deprecado en NumPy 2.0

Los tres se corrigieron. Este archivo no vuelve a correr la suite entera bajo
`-W error` en cada test (duplicaría el tiempo de CADA corrida de la suite,
para siempre) — apunta puntualmente a los tres módulos que las disparaban, así
que una regresión ahí se detecta rápido. La verificación completa —la suite
entera, sin ninguna advertencia de deprecación— se corrió a mano y su salida
va pegada en el commit; correrla de nuevo:

    python3 -m pytest -q tests/ -W error::DeprecationWarning
"""
import subprocess
import sys

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))


def test_los_tres_focos_conocidos_no_vuelven_a_avisar_deprecacion():
    """`realtime.server` (on_event), el oráculo de audioop en test_kobra y el
    simplificador de marca (np.cross 2D) son, hoy, los únicos tres lugares
    del repo que emiten `DeprecationWarning` al correr la suite. Se corren
    ACÁ, elevando la advertencia a error, para que una regresión en
    cualquiera de los tres falle rápido y con el nombre del culpable — sin
    pagar el costo de repetir la suite entera en cada test."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-W", "error::DeprecationWarning",
         "tests/test_kobra.py::test_g711_codecs_bit_exactos",
         "tests/test_kobra.py::test_stream_decoders",
         "tests/test_marca.py::test_el_simplificador_conserva_las_esquinas_y_tira_los_puntos_de_paso",
         "tests/test_concurrencia.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        f"volvió una DeprecationWarning en alguno de los tres focos conocidos:\n"
        f"{r.stdout[-3000:]}\n{r.stderr[-1000:]}")


def test_ningun_archivo_propio_hace_at_app_on_event():
    """Barrido estático, más barato que importar cada app: si alguien agrega
    un `@app.on_event` nuevo en otro FastAPI del repo, que se note acá antes
    que en el warnings summary de la suite completa."""
    import os
    import re
    encontrados = []
    for base in ("webapp/backend", "realtime", "backend_venta"):
        for root, _, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                ruta = os.path.join(root, f)
                with open(ruta, encoding="utf-8") as fh:
                    # Ancla al inicio de línea (con indentación) para no
                    # confundir un decorador real con un comentario que lo
                    # MENCIONA — como el que explica, en este mismo archivo,
                    # por qué ya no se usa.
                    if re.search(r'^\s*@\w+\.on_event\(', fh.read(), re.MULTILINE):
                        encontrados.append(ruta)
    assert not encontrados, f"@app.on_event (deprecado) en: {encontrados}"
