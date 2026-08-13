# © 2026 Martín Viera. Todos los derechos reservados.
"""La carpeta `instalador/` y las garantías del programa instalado.

Pedido: «el instalador que sea profesional como programa y no streamlit, y no
coincida con otro puerto abierto; versión owner idéntica a la descargada por
compradores; poner una carpeta aparte en GitHub con instalador exe incluido».

Sobre lo último: el `.exe` **no puede** estar commiteado. GitHub rechaza
archivos de más de 100 MB dentro de un repositorio y el instalador pesa
~267 MB; Git LFS lo permitiría pero su cuota gratis (1 GB/mes de tráfico) se
agota en tres descargas. El binario vive en Releases —el lugar de GitHub hecho
para esto— y la carpeta es el atajo: un README y un .bat que lo baja.

Estos tests fijan las cuatro garantías para que no se pierdan en un refactor.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(ROOT, "instalador")


@pytest.fixture(scope="module")
def readme():
    with open(os.path.join(CARPETA, "README.md"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def descargador():
    with open(os.path.join(CARPETA, "DESCARGAR_INSTALADOR.bat"),
              encoding="utf-8") as f:
        return f.read()


# --- La carpeta ------------------------------------------------------------
def test_la_carpeta_existe_con_lo_necesario():
    for archivo in ("README.md", "DESCARGAR_INSTALADOR.bat"):
        assert os.path.exists(os.path.join(CARPETA, archivo)), f"falta {archivo}"


def test_el_descargador_apunta_a_la_ultima_release(descargador):
    """`/releases/latest/download/` sirve siempre el último publicado: si
    apuntara a una versión fija, el .bat quedaría desactualizado en cada
    build."""
    assert "releases/latest/download/MVKobraAI_Setup.exe" in descargador


def test_el_descargador_tiene_salida_si_el_repo_es_privado(descargador):
    """El repositorio es privado: la descarga directa devuelve 404 sin
    credenciales. Sin este respaldo, el .bat fallaría sin decir por qué."""
    assert "releases/latest" in descargador
    assert "start " in descargador


def test_el_descargador_muestra_el_hash_para_verificar(descargador):
    assert "Get-FileHash" in descargador and "SHA256" in descargador


def test_el_descargador_no_tiene_caracteres_no_ascii(descargador):
    """Un .bat se lee en la code page de la consola (850/437), no en UTF-8."""
    malos = [c for c in descargador if ord(c) > 127]
    assert not malos, f"{len(malos)} caracteres no-ASCII -> mojibake"


def test_no_se_commiteo_ningun_binario_gigante():
    """El límite de GitHub es 100 MB por archivo. Si alguien intenta meter el
    .exe acá, el push falla entero — mejor que falle el test primero, con una
    explicación."""
    grandes = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "dist",
                                                "_staging", "__pycache__")]
        for fn in files:
            ruta = os.path.join(base, fn)
            try:
                if os.path.getsize(ruta) > 90 * 1024 * 1024:
                    grandes.append((os.path.relpath(ruta, ROOT),
                                    os.path.getsize(ruta) // (1024 * 1024)))
            except OSError:
                pass
    assert not grandes, f"archivos cerca del limite de 100 MB de GitHub: {grandes}"


# --- Las garantías del programa instalado ----------------------------------
def test_el_instalador_arranca_fastapi_y_no_streamlit():
    """El pedido dice «como programa y no streamlit». El .exe tiene que
    levantar la app React + FastAPI, no el dashboard Streamlit."""
    with open(os.path.join(ROOT, "packaging", "kobra.spec"), encoding="utf-8") as f:
        spec = f.read()
    assert "kobra_launcher.py" in spec, "cambió el punto de entrada del .exe"

    with open(os.path.join(ROOT, "packaging", "kobra_launcher.py"),
              encoding="utf-8") as f:
        launcher = f.read()
    assert "from webapp.backend.api import app" in launcher
    assert "uvicorn.run(app" in launcher

    # Se mira el CÓDIGO, no el texto: buscar la palabra suelta daba falso
    # positivo con un comentario que solo nombra la otra vía de arranque. Lo
    # que no puede pasar es que el launcher IMPORTE o EJECUTE Streamlit.
    import ast
    arbol = ast.parse(launcher)
    docstrings = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(nodo, clean=False)
            if doc:
                docstrings.add(doc)

    importados, literales = set(), []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            importados.add(nodo.module or "")
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if nodo.value not in docstrings:
                literales.append(nodo.value)

    assert not [m for m in importados if "streamlit" in m.lower()], \
        "el launcher del instalador volvió a importar Streamlit"
    assert not [s for s in literales if "streamlit" in s.lower()], \
        "el launcher del instalador volvió a invocar Streamlit"


def test_el_puerto_lo_asigna_el_sistema_operativo():
    """«que no coincida con otro puerto abierto». `listen(0)` hace que el SO
    devuelva uno libre de su rango dinámico: no puede entregar uno ocupado.
    Fijar un puerto (8501, 8000) sí chocaría con lo que ya corra en la máquina."""
    with open(os.path.join(ROOT, "electron", "main.js"), encoding="utf-8") as f:
        main = f.read()
    assert 'srv.listen(0, "127.0.0.1"' in main, \
        "Electron dejó de pedirle un puerto libre al sistema operativo"
    assert "KOBRA_APP_PORT: String(puerto)" in main, \
        "el puerto elegido ya no se le pasa al motor"


def test_electron_no_abre_el_navegador():
    """La app tiene ventana propia; el launcher no debe levantar además un
    navegador."""
    with open(os.path.join(ROOT, "electron", "main.js"), encoding="utf-8") as f:
        main = f.read()
    assert 'KOBRA_SIN_NAVEGADOR: "1"' in main
    assert "new BrowserWindow" in main


def test_el_owner_y_el_comprador_instalan_el_mismo_binario(readme):
    """Si fueran dos builds distintos, un bug podría aparecer solo del lado del
    cliente y no verse nunca del lado del dueño."""
    assert "mismo binario" in readme.lower()
    # Y en el código: el desbloqueo del dueño no depende de un build especial,
    # entra por el mismo endpoint de activación que usa un cliente.
    with open(os.path.join(ROOT, "webapp", "backend", "api.py"), encoding="utf-8") as f:
        api = f.read()
    assert "kowner.verificar(datos.token)" in api, \
        "el desbloqueo del dueño dejó de entrar por la activación normal"


def test_el_readme_explica_por_que_el_exe_no_esta_en_la_carpeta(readme):
    """Sin la explicación, el próximo que mire la carpeta va a intentar
    commitear el .exe y el push le va a fallar entero."""
    assert "100 MB" in readme
    assert "Releases" in readme
