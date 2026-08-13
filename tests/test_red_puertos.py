# © 2026 Martín Viera. Todos los derechos reservados.

"""Elegir puerto sin pisar a otra aplicación (kobra/red.py).

Reportado desde una instalación real: «no pisar puertos si otra app los usa».

El defecto no era que faltara el chequeo — existía — sino que estaba escrito de
una forma que en Windows **no chequea nada**. El sondeo pedía `SO_REUSEADDR`
antes del `bind()`, y esa opción no significa lo mismo en los dos sistemas:

* En Unix permite reusar un puerto en TIME_WAIT, pero NO uno que otro proceso
  tenga en LISTEN — así que el sondeo funcionaba.
* En Windows permite hacer `bind()` sobre un puerto que otro proceso tiene en
  LISTEN (lo que en Unix habría que pedir aparte con `SO_REUSEPORT`). El
  sondeo devolvía «libre» para un puerto ocupado y arrancábamos encima de la
  otra aplicación.

Estos tests corren en Linux, donde el bug no se reproduce: por eso el primero
mira el CÓDIGO (que no se vuelva a pedir SO_REUSEADDR al sondear) y el resto
mira el COMPORTAMIENTO, que tiene que ser correcto en los dos sistemas.
"""
import ast
import inspect
import os
import socket
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import red as kred  # noqa: E402


def _codigo(fn):
    """Fuente de `fn` SIN su docstring.

    Hace falta porque los docstrings de este módulo nombran `SO_REUSEADDR`
    justamente para explicar por qué no se usa: buscarlo sobre la fuente cruda
    da un falso positivo contra el comentario que documenta el arreglo."""
    arbol = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    funcion = arbol.body[0]
    cuerpo = funcion.body
    if (cuerpo and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)):
        cuerpo = cuerpo[1:]
    return "\n".join(ast.unparse(n) for n in cuerpo)


@pytest.fixture()
def ocupar():
    """Ocupa puertos como lo haría otra aplicación, y los libera al final."""
    abiertos = []

    def _ocupar(puerto):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR acá es a propósito: así se comporta un servidor cualquiera.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", puerto))
        s.listen(1)
        abiertos.append(s)
        return puerto

    yield _ocupar
    for s in abiertos:
        s.close()


def test_el_sondeo_no_pide_so_reuseaddr():
    """La regresión concreta. En Windows, con SO_REUSEADDR puesto, `bind()`
    sobre un puerto ajeno en LISTEN tiene éxito y el sondeo miente."""
    assert "SO_REUSEADDR" not in _codigo(kred.esta_libre), \
        "volvió el SO_REUSEADDR que hacía que el sondeo diera libre un puerto ocupado"


def test_en_windows_pide_exclusividad_explicita():
    """SO_EXCLUSIVEADDRUSE es la forma de decir «este puerto es mío o no lo
    quiero». Solo existe en Windows, por eso se pide con getattr."""
    assert "SO_EXCLUSIVEADDRUSE" in _codigo(kred.esta_libre)


def test_un_puerto_ocupado_no_figura_como_libre(ocupar):
    p = ocupar(kred.PUERTOS_APP[0])
    assert kred.esta_libre(p) is False


def test_un_puerto_realmente_libre_figura_como_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        libre = s.getsockname()[1]
    # Cerrado el socket, ese puerto queda disponible.
    assert kred.esta_libre(libre) is True


def test_no_devuelve_el_puerto_que_otra_app_esta_usando(ocupar):
    """El caso del reporte: otra app en el primer candidato."""
    ocupado = ocupar(kred.PUERTOS_APP[0])
    elegido = kred.puerto_libre(kred.PUERTOS_APP)
    assert elegido != ocupado
    assert kred.esta_libre(elegido)


def test_con_todos_los_candidatos_ocupados_cae_a_uno_efimero(ocupar):
    """Devolver igual uno de la lista sería volver a pisar a alguien."""
    for p in kred.PUERTOS_APP:
        ocupar(p)
    elegido = kred.puerto_libre(kred.PUERTOS_APP)
    assert elegido not in kred.PUERTOS_APP
    assert kred.esta_libre(elegido)


def test_respeta_el_orden_de_preferencia(ocupar):
    """Sin nada ocupado tiene que salir el primero: la URL es la de siempre y
    el usuario no ve un puerto distinto en cada arranque."""
    if not kred.esta_libre(kred.PUERTOS_APP[0]):
        pytest.skip("el primer candidato está ocupado en esta máquina")
    assert kred.puerto_libre(kred.PUERTOS_APP) == kred.PUERTOS_APP[0]


def test_los_candidatos_no_son_los_puertos_tipicos_de_otros_programas():
    """8000/8080/8501/5000 son justamente los que ya suele tener tomados otra
    cosa (el propio Streamlit, Flask, Docker...)."""
    tipicos = {80, 443, 3000, 5000, 8000, 8080, 8081, 8501, 8888}
    assert not (set(kred.PUERTOS_APP) & tipicos)
    assert not (set(kred.PUERTOS_STREAMLIT) & tipicos)


def test_el_lanzador_de_escritorio_usa_esta_logica():
    """No una copia propia que se olvide de arreglar."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "kl_puertos", os.path.join(ROOT, "packaging", "kobra_launcher.py"))
    kl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kl)
    fuente = _codigo(kl._puerto_libre)
    assert "kobra import red" in fuente or "from kobra import red" in fuente
    assert "SO_REUSEADDR" not in fuente


def test_el_lanzador_de_streamlit_elige_puerto_antes_de_arrancar():
    """Streamlit asume 8501 fijo: si no se le pasa uno libre, o falla o se
    corre solo de puerto sin avisar."""
    ruta = os.path.join(ROOT, "packaging", "kobra_streamlit.py")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    assert "puerto_libre" in src
    assert "--server.port" in src


def _cargar_streamlit_launcher(monkeypatch, capturado):
    """Carga packaging/kobra_streamlit.py con un doble de Streamlit.

    Streamlit no es dependencia de los tests (ni está instalado en el
    contenedor de CI), así que se inyecta un módulo falso: lo que se verifica
    es **con qué puerto y qué argumentos** arrancaría, que es exactamente la
    decisión que antes estaba mal.
    """
    import types
    st = types.ModuleType("streamlit")
    web = types.ModuleType("streamlit.web")
    cli = types.ModuleType("streamlit.web.cli")

    def _main():
        capturado["argv"] = list(sys.argv)
        return 0

    cli.main = _main
    web.cli = cli
    st.web = web
    for nombre, mod in (("streamlit", st), ("streamlit.web", web),
                        ("streamlit.web.cli", cli)):
        monkeypatch.setitem(sys.modules, nombre, mod)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ks_launcher", os.path.join(ROOT, "packaging", "kobra_streamlit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_streamlit_no_arranca_en_un_puerto_que_otra_app_usa(ocupar, monkeypatch):
    """El caso concreto: otra app en el puerto que Streamlit tomaría."""
    ocupado = ocupar(kred.PUERTOS_STREAMLIT[0])
    monkeypatch.delenv("KOBRA_APP_PORT", raising=False)
    capturado = {}
    argv_previo = list(sys.argv)
    try:
        mod = _cargar_streamlit_launcher(monkeypatch, capturado)
        assert mod.main() == 0
    finally:
        sys.argv = argv_previo

    argv = capturado["argv"]
    puerto = int(argv[argv.index("--server.port") + 1])
    assert puerto != ocupado, "arrancaria encima de la otra aplicacion"
    assert kred.esta_libre(puerto)
    assert argv[1] == "run" and argv[2].endswith(os.path.join("app", "app.py"))


def test_streamlit_respeta_un_puerto_pedido_a_mano(monkeypatch):
    """Con KOBRA_APP_PORT puesto (Docker, o un reverse proxy) manda esa."""
    monkeypatch.setenv("KOBRA_APP_PORT", "9123")
    capturado = {}
    argv_previo = list(sys.argv)
    try:
        mod = _cargar_streamlit_launcher(monkeypatch, capturado)
        mod.main()
    finally:
        sys.argv = argv_previo
    argv = capturado["argv"]
    assert argv[argv.index("--server.port") + 1] == "9123"
