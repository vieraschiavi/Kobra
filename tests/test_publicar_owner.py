# © 2026 Martín Viera. Todos los derechos reservados.

"""Publicar la edición Owner sin regalar el producto.

El pedido fue «una versión owner para descargar en GitHub». Existía el
workflow, pero mientras la cuenta no tenga minutos de Actions no publica nada:
el código estaba y el archivo descargable no. `packaging/publicar_owner.py` lo
hace desde cualquier máquina con un token.

El riesgo de este script es específico: la edición Owner arranca **sin
licencia y sin vencimiento**, así que subirla al repositorio equivocado —el
público de descargas— sería regalar el producto completo a cualquiera que la
baje. Eso no se arregla con un comentario en el README: se bloquea en el
código, y estos tests verifican que el bloqueo funcione.
"""
import importlib.util
import json
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def pub():
    spec = importlib.util.spec_from_file_location(
        "publicar_owner", os.path.join(ROOT, "packaging", "publicar_owner.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _zip_valido(tmp_path, **cambios):
    """Un paquete Owner mínimo pero completo, con los retoques que se pidan."""
    ed = {"edition": "Owner", "plan": None, "dias": None, "owner": True}
    ed.update(cambios.pop("edicion", {}))
    p = tmp_path / "paquete.zip"
    with zipfile.ZipFile(p, "w") as z:
        for pieza in ("INSTALAR.bat", "INICIAR_OWNER.bat",
                      "kobra_software/kobra_launcher.py",
                      "kobra_software/packaging/instalar_windows.ps1",
                      "kobra_software/packaging/desinstalar_windows.ps1",
                      "kobra_software/electron/build/icon.ico"):
            if pieza in cambios.get("omitir", ()):
                continue
            datos = cambios.get("contenido", {}).get(pieza, b"x")
            z.writestr(pieza, datos)
        z.writestr("kobra_software/edicion.json", json.dumps(ed))
    return str(p)


# --- El paquete se verifica ANTES de publicarlo ----------------------------
def test_un_paquete_completo_pasa(pub, tmp_path):
    r = pub.verificar(_zip_valido(tmp_path))
    assert r["edicion"]["owner"] is True


def test_rechaza_un_paquete_al_que_le_falta_el_instalador(pub, tmp_path):
    """Un ZIP mal armado que igual se publica es peor que no publicar nada: se
    descarga, no arranca, y el error aparece recién en la PC del que lo bajó."""
    z = _zip_valido(tmp_path, omitir=("INSTALAR.bat",))
    with pytest.raises(SystemExit, match="faltan piezas"):
        pub.verificar(z)


def test_rechaza_un_bat_con_BOM(pub, tmp_path):
    """cmd.exe no saltea el BOM: la ventana arranca con un error de comando no
    reconocido. Ya pasó una vez; no puede publicarse así."""
    z = _zip_valido(tmp_path, contenido={"INSTALAR.bat": b"\xef\xbb\xbf@echo off"})
    with pytest.raises(SystemExit, match="BOM"):
        pub.verificar(z)


@pytest.mark.parametrize("edicion,motivo", [
    ({"owner": False}, "no es owner"),
    ({"dias": 14}, "no puede llevar límite"),
    ({"plan": "trial"}, "no puede llevar límite"),
])
def test_rechaza_un_paquete_que_no_es_realmente_owner(pub, tmp_path, edicion, motivo):
    """Publicar como «Owner» algo que en realidad vence a los 14 días sería
    peor que no publicar: el dueño se queda sin producto sin entender por qué."""
    with pytest.raises(SystemExit, match=motivo):
        pub.verificar(_zip_valido(tmp_path, edicion=edicion))


# --- Dónde NO puede publicarse ---------------------------------------------
@pytest.mark.parametrize("repo", [
    "vieraschiavi/mv-kobra-ai-releases",
    "vieraschiavi/kobra-downloads",
    "vieraschiavi/Kobra-Public",
    "otro/descargas",
])
def test_no_publica_en_un_repo_que_parece_el_publico(pub, repo, monkeypatch):
    """El nombre se chequea ANTES de llamar a la API: si el token no tuviera
    permiso de lectura sobre ese repo, la verificación por API fallaría con un
    404 confuso en vez de con el motivo real."""
    def _no_deberia_llamar(*a, **k):
        raise AssertionError("llamó a la API antes de mirar el nombre")
    monkeypatch.setattr(pub, "_pedir", _no_deberia_llamar)
    with pytest.raises(SystemExit, match="repositorio PÚBLICO"):
        pub._validar_destino(repo, "token-falso")


def test_no_publica_en_un_repo_publico_aunque_el_nombre_no_lo_delate(pub, monkeypatch):
    """El nombre no alcanza: un repo puede llamarse cualquier cosa y ser
    público. Se confirma contra la API antes de subir un byte."""
    monkeypatch.setattr(pub, "_pedir", lambda *a, **k: {"private": False})
    with pytest.raises(SystemExit, match="es PÚBLICO"):
        pub._validar_destino("vieraschiavi/Kobra", "token-falso")


def test_publica_en_el_repo_privado(pub, monkeypatch):
    monkeypatch.setattr(pub, "_pedir", lambda *a, **k: {"private": True})
    pub._validar_destino("vieraschiavi/Kobra", "token-falso")   # no levanta


def test_el_destino_por_defecto_es_el_repo_privado(pub):
    assert pub.REPO_DEFAULT == "vieraschiavi/Kobra"


# --- No robarle el enlace `latest` al instalador de clientes ---------------
def test_la_release_owner_no_se_marca_como_latest(pub, monkeypatch):
    """La landing descarga desde `/releases/latest/download/MVKobraAI_Setup.exe`.
    Si la edición Owner se marcara `latest`, ese enlace pasaría a apuntar a una
    release que no tiene el .exe — y el instalador de clientes daría 404."""
    enviados = []

    def _fake(url, token, datos=None, metodo=None, binario=None, content_type=None):
        if url.endswith("/releases/tags/owner-v9.9.9"):
            raise SystemExit("404")            # no existe todavía
        if datos:
            enviados.append(datos)
        if url.endswith("/releases"):
            return {"upload_url": "https://uploads/assets{?name}", "assets": []}
        return {"private": True, "browser_download_url": "https://x/z.zip"}

    monkeypatch.setattr(pub, "_pedir", _fake)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        f.write(b"contenido")
        ruta = f.name
    try:
        pub.publicar(ruta, "owner-v9.9.9", "n", "c", "vieraschiavi/Kobra", "tok")
    finally:
        os.remove(ruta)

    creacion = [d for d in enviados if "tag_name" in d]
    assert creacion, "no se creó la release"
    assert creacion[0]["make_latest"] == "false", \
        "la edición Owner se marcó como latest y le robó el enlace al instalador"
    assert creacion[0]["draft"] is False


def test_republicar_reemplaza_el_archivo_en_vez_de_duplicarlo(pub, monkeypatch):
    """Sin esto, GitHub rechaza el segundo upload con el mismo nombre y la
    release queda con el ZIP viejo."""
    borrados = []

    def _fake(url, token, datos=None, metodo=None, binario=None, content_type=None):
        if metodo == "DELETE":
            borrados.append(url)
            return {}
        if url.endswith("/releases/tags/owner-v9.9.9"):
            return {"upload_url": "https://uploads/assets{?name}",
                    "assets": [{"id": 77, "name": "z.zip"}]}
        return {"private": True, "browser_download_url": "https://x/z.zip"}

    monkeypatch.setattr(pub, "_pedir", _fake)
    import tempfile
    d = tempfile.mkdtemp()
    ruta = os.path.join(d, "z.zip")
    with open(ruta, "wb") as f:
        f.write(b"nuevo")
    pub.publicar(ruta, "owner-v9.9.9", "n", "c", "vieraschiavi/Kobra", "tok")
    assert any("assets/77" in u for u in borrados), \
        "no borró el archivo anterior: el upload nuevo va a rebotar"
