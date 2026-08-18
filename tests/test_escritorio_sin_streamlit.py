# © 2026 Martín Viera. Todos los derechos reservados.

"""La app de escritorio es React + Electron, y nada más.

Decisión de producto: lo que se le vende a una empresa entra por una sola
puerta. Un comprador que abría el dashboard Streamlit veía su barra propia, su
menú de hamburguesa y su estética de notebook, y lo que estaba comprando
dejaba de parecer un producto terminado. Una puerta bien hecha vale más que
dos a medias.

Qué cambió y qué no:

* El instalador ya no empaqueta `streamlit` ni `altair` — 43 MB que el .exe
  cargaba y no usaba nunca.
* Las releases de cliente ya no publican el ZIP de Streamlit.
* El código **no se borró**: `app/app.py` sigue entero y
  `python packaging/build_release.py --edicion Demo` sigue armando el ZIP a
  mano para el cliente cuyo sistemas prohíbe ejecutar un .exe. Lo que se sacó
  es el ofrecimiento por defecto, que es la parte reversible.

El test que importa es el último: bloquea el import de `streamlit` y levanta
el backend de verdad. Sacar un paquete del bundle por deducción es cómo se
arma un instalador que revienta en la máquina del cliente con un
`ModuleNotFoundError` y no acá.
"""
import builtins
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "packaging", "kobra.spec")
WF = os.path.join(ROOT, ".github", "workflows", "build_windows.yml")


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _sin_comentarios(texto):
    """Sin las líneas `#`: los comentarios de estos archivos explican por qué
    se sacó Streamlit, y lo nombran. Sin filtrarlos, la explicación del arreglo
    hace fallar al test que verifica el arreglo — ya pasó tres veces en este
    repo."""
    return "\n".join(ln for ln in texto.splitlines()
                     if not ln.strip().startswith("#"))


def test_el_ejecutable_no_empaqueta_streamlit():
    """43 MB de peso muerto en un instalador que ya pesa 268."""
    spec = _sin_comentarios(_leer(SPEC))
    for paquete in ('"streamlit"', '"altair"'):
        assert paquete not in spec, \
            f"el .exe vuelve a empaquetar {paquete}, que nunca ejecuta"


def test_la_release_de_clientes_no_ofrece_el_zip_de_streamlit():
    wf = _sin_comentarios(_leer(WF))
    assert "MVKobraAI_Demo_v" not in wf, \
        "la release de clientes volvió a publicar la edición Streamlit"
    assert "INICIAR_DEMO_STREAMLIT" not in wf, \
        "el cuerpo de la release sigue mandando al .bat de Streamlit"


def test_el_exe_sigue_siendo_lo_que_se_publica():
    """El corolario: si al sacar el ZIP quedara una release sin nada, sería
    peor que antes."""
    wf = _leer(WF)
    assert "dist/MVKobraAI_Setup.exe" in wf, \
        "la release dejó de publicar el instalador"


def test_el_empaquetador_todavia_puede_armar_la_edicion_streamlit():
    """No se borró: se dejó de ofrecer. Si un cliente no puede correr un .exe,
    la vía sigue existiendo a un comando de distancia."""
    assert os.path.isfile(os.path.join(ROOT, "app", "app.py")), \
        "se borró el dashboard Streamlit en vez de dejar de ofrecerlo"
    build = _leer(os.path.join(ROOT, "packaging", "build_release.py"))
    assert "kobra_streamlit.py" in build, \
        "el empaquetador ya no sabe armar la edición sin .exe"


@pytest.mark.skipif(sys.platform == "win32", reason="el gate real corre en CI Linux")
def test_el_backend_de_escritorio_arranca_sin_streamlit(tmp_path, monkeypatch):
    """La evidencia, no la deducción.

    Se bloquea el import de `streamlit` y se levanta el backend real: login y
    diez endpoints. Si algo del camino de escritorio lo necesitara, acá
    aparecería un `ModuleNotFoundError` — que es exactamente lo que le pasaría
    al cliente al abrir el programa, y en un momento mucho peor.
    """
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))

    real_import = builtins.__import__

    def bloqueado(nombre, *a, **kw):
        if nombre == "streamlit" or nombre.startswith("streamlit."):
            raise ImportError("streamlit bloqueado a propósito por este test")
        return real_import(nombre, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", bloqueado)

    import importlib
    sys.path.insert(0, ROOT)
    from fastapi.testclient import TestClient

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import autenticacion as kauth
    importlib.reload(kauth)
    from webapp.backend import api
    importlib.reload(api)

    kauth.establecer_password("admin", "SinStreamlit123!")
    c = TestClient(api.app)
    r = c.post("/api/auth/login",
               json={"password": "SinStreamlit123!", "empresa": "principal"})
    assert r.status_code == 200, r.text
    h = {"Authorization": "Bearer " + r.json()["token"]}

    # 500 = algo explotó adentro (por ejemplo, el import bloqueado). 404 no:
    # con una carpeta de datos vacía, varias pantallas contestan 404 y eso
    # pasa igual con Streamlit disponible — se comprobó contra ese control.
    for ruta in ("/api/health", "/api/config/estado", "/api/almacenamiento",
                 "/api/licencia/estado", "/api/agenda"):
        assert c.get(ruta, headers=h).status_code < 500, \
            f"{ruta} rompe sin Streamlit — el .exe no puede dejar de traerlo"

    monkeypatch.undo()
    importlib.reload(kconfig)
    importlib.reload(kauth)
    importlib.reload(api)


def test_el_readme_no_vende_dos_caminos_al_cliente():
    """Un README que sigue ofreciendo las dos vías deja al comprador eligiendo
    justo lo que se quiso dejar de mostrar."""
    readme = _leer(os.path.join(ROOT, "README.md"))
    # Se busca en la sección de descarga/instalación, no en todo el archivo:
    # el README documenta el repo entero, y `streamlit run app/app.py` sigue
    # siendo un comando válido para desarrollo.
    bloques = re.split(r"\n#{2,3} ", readme)
    venta = [b for b in bloques
             if re.search(r"descarg|instalad|comprar|precio", b[:200], re.I)]
    malos = [b.split("\n")[0] for b in venta if "INICIAR_DEMO_STREAMLIT" in b]
    assert not malos, \
        f"estas secciones de venta siguen ofreciendo la vía Streamlit: {malos}"
