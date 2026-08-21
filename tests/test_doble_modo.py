# © 2026 Martín Viera. Todos los derechos reservados.

"""Cada edición se abre por DOS vías, y las dos tienen que funcionar igual.

Pedido: además del instalador .exe, que haya un .bat — muchas empresas
prohíben por política ejecutar un .exe bajado de internet, pero no correr un
script. Sin esa segunda vía, un cliente con TI restrictiva se queda sin
producto.

Los tres bugs que encontró la verificación end-to-end del paquete armado, y
que estos tests fijan para que no vuelvan:

1. Las ediciones NO incluían `app/` ni `kobra_streamlit.py`: la vía sin .exe
   directamente no existía.
2. `_base_dir()` de los dos launchers subía siempre un nivel. Eso vale en el
   repo (viven en `packaging/`) pero no en el ZIP (van a la raíz de
   `kobra_software/`), así que resolvía la carpeta equivocada. Fallaba en
   silencio —los imports andaban igual porque Python agrega el directorio del
   script a `sys.path`— y lo único roto era lo que se busca por ruta: la UI
   compilada no aparecía (404 en `/`) y el dashboard no arrancaba nunca.
3. El dashboard no leía `edicion.json`, así que la Demo abierta por Streamlit
   no aplicaba su propio límite de días: evaluación gratis para siempre con
   solo usar el otro acceso directo.
"""
import importlib.util
import json
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import edicion as kedicion  # noqa: E402

PAQUETE = os.path.join(ROOT, "packaging", "build_release.py")


@pytest.fixture(scope="module")
def br():
    spec = importlib.util.spec_from_file_location("br_test", PAQUETE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def edicion_owner(br, tmp_path_factory):
    """Arma la edición Owner de verdad y la extrae — sobre eso se verifica."""
    tmp = str(tmp_path_factory.mktemp("build"))
    zip_path = br.build_edicion(tmp, "Owner")
    destino = str(tmp_path_factory.mktemp("extraido"))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(destino)
    return destino


# --- 1) Las dos vías viajan en el paquete -----------------------------------
def test_el_paquete_trae_los_dos_lanzadores(edicion_owner):
    for archivo in ("INICIAR_OWNER.bat",           # app de escritorio (React)
                    "INICIAR_OWNER_STREAMLIT.bat",  # dashboard, sin .exe
                    "iniciar_owner.sh", "iniciar_owner_streamlit.sh",
                    "INSTALAR.bat"):
        assert os.path.exists(os.path.join(edicion_owner, archivo)), archivo


def test_los_bat_apuntan_a_scripts_que_existen(edicion_owner):
    """Un .bat que llama a un archivo inexistente es el peor de los fallos:
    doble clic, ventana negra un segundo, y nada."""
    soft = os.path.join(edicion_owner, "kobra_software")
    casos = [("INICIAR_OWNER.bat", "kobra_launcher.py"),
             ("INICIAR_OWNER_STREAMLIT.bat", "kobra_streamlit.py")]
    for bat, script in casos:
        with open(os.path.join(edicion_owner, bat), encoding="utf-8") as f:
            contenido = f.read()
        assert script in contenido, f"{bat} no llama a {script}"
        assert os.path.exists(os.path.join(soft, script)), f"falta {script}"


def test_el_dashboard_streamlit_viaja_en_el_paquete(edicion_owner):
    """El bug 1: sin `app/`, la vía sin .exe no podía existir."""
    assert os.path.exists(os.path.join(edicion_owner, "kobra_software", "app", "app.py"))


def test_los_bat_no_llevan_bom_ni_saltos_rotos(edicion_owner):
    """`cmd.exe` no abre un .bat con BOM, y un \\r\\r\\n rompe el parseo."""
    for nombre in os.listdir(edicion_owner):
        if not nombre.lower().endswith(".bat"):
            continue
        with open(os.path.join(edicion_owner, nombre), "rb") as f:
            crudo = f.read()
        assert not crudo.startswith(b"\xef\xbb\xbf"), f"{nombre} tiene BOM"
        assert b"\r\r\n" not in crudo, f"{nombre} tiene doble CR"
        assert b"\r\n" in crudo, f"{nombre} no tiene saltos de Windows"


def test_el_instalador_deja_los_accesos_de_las_dos_vias(edicion_owner):
    """INSTALAR.bat tiene que pedir los DOS accesos directos; si no, el
    cliente que instala se queda solo con la vía que no puede usar."""
    with open(os.path.join(edicion_owner, "INSTALAR.bat"), encoding="utf-8") as f:
        contenido = f.read()
    assert "-LanzadorAlterno" in contenido and "kobra_streamlit.py" in contenido


def test_el_leeme_explica_las_dos_formas(edicion_owner):
    with open(os.path.join(edicion_owner, "LEEME.txt"), encoding="utf-8") as f:
        texto = f.read()
    assert "INICIAR_OWNER_STREAMLIT.bat" in texto
    assert ".exe" in texto, "el LEEME no explica para qué sirve la vía sin .exe"


# --- 2) La raíz se resuelve por contenido, no por posición ------------------
def _base_dir_de(modulo_path, nombre):
    spec = importlib.util.spec_from_file_location(nombre, modulo_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._base_dir()


@pytest.mark.parametrize("script", ["kobra_launcher.py", "kobra_streamlit.py"])
def test_la_raiz_se_resuelve_bien_en_el_layout_del_zip(edicion_owner, script):
    """El bug 2, medido donde importa: con el launcher en la raíz de
    `kobra_software/`, `_base_dir()` tiene que devolver ESA carpeta (la que
    tiene `kobra/`, `app/` y `owner/ui_dist`), no la de arriba."""
    soft = os.path.join(edicion_owner, "kobra_software")
    base = _base_dir_de(os.path.join(soft, script), f"zip_{script[:-3]}")
    assert os.path.realpath(base) == os.path.realpath(soft)
    for necesaria in ("kobra", "app", os.path.join("owner", "ui_dist")):
        assert os.path.isdir(os.path.join(base, necesaria)), necesaria


@pytest.mark.parametrize("script", ["kobra_launcher.py", "kobra_streamlit.py"])
def test_la_raiz_sigue_bien_en_el_layout_del_repo(script):
    """Y el layout de siempre no se puede romper al arreglar el otro."""
    base = _base_dir_de(os.path.join(ROOT, "packaging", script), f"repo_{script[:-3]}")
    assert os.path.realpath(base) == os.path.realpath(ROOT)


# --- 3) La edición se aplica por las dos vías -------------------------------
def test_las_dos_vias_aplican_la_misma_edicion():
    """El bug 3: el dashboard tiene que leer `edicion.json` igual que la app
    de escritorio. Si no, la Demo abierta por Streamlit no vence nunca."""
    for script in ("kobra_launcher.py", "kobra_streamlit.py"):
        with open(os.path.join(ROOT, "packaging", script), encoding="utf-8") as f:
            contenido = f.read()
        assert "edicion" in contenido and "activar" in contenido, (
            f"{script} no aplica la edición del paquete")


def test_owner_no_vence_nunca(tmp_path, monkeypatch, sello_owner):
    monkeypatch.setenv("KOBRA_OWNER_TOKEN", sello_owner["token_owner"])
    v = kedicion.vigencia()
    assert v["ok"] and v["owner"] and v["dias_restantes"] is None


def test_una_edicion_vencida_bloquea_el_programa(tmp_path, monkeypatch):
    """La prueba que importa comercialmente: con la licencia vencida, la
    vigencia da NO — es lo que hace que el dashboard corte antes del login."""
    import importlib
    import time

    import jwt

    monkeypatch.delenv("KOBRA_OWNER_TOKEN", raising=False)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", "secreto-de-la-edicion")
    # `import_module` y no `reload` a secas: otros tests de la suite borran
    # los módulos `kobra.*` de sys.modules para releer la app con otro
    # entorno, y entonces recargar la referencia vieja explota con
    # "module not in sys.modules" — pero solo al correr la suite entera, no
    # el archivo aislado.
    kconfig = importlib.import_module("kobra.config")
    importlib.reload(kconfig)

    # La licencia de la evaluación, pero ya vencida hace una hora.
    ahora = int(time.time())
    vencida = jwt.encode(
        {"sub": "demo", "plan": "trial", "edition": "demo",
         "iat": ahora - 20 * 86400, "exp": ahora - 3600},
        "secreto-de-la-edicion", algorithm="HS256")

    ked = importlib.import_module("kobra.edicion")
    kconfig.guardar_extra(ked.CLAVE_TOKEN, vencida)
    importlib.reload(ked)
    v = ked.vigencia()
    assert not v["ok"] and v["motivo"] == "licencia_expirada"


def test_activar_owner_no_necesita_licencia(tmp_path, monkeypatch, sello_owner):
    monkeypatch.delenv("KOBRA_OWNER_TOKEN", raising=False)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    (tmp_path / "edicion.json").write_text(
        json.dumps(sello_owner), encoding="utf-8")
    ed = kedicion.activar(str(tmp_path))
    assert ed["owner"] is True
    assert os.environ.get("KOBRA_OWNER_TOKEN"), \
        "el launcher tiene que exportar el token firmado, no un booleano"


def test_un_sello_sin_firma_no_activa_owner(tmp_path, monkeypatch):
    """63 bytes de JSON convertían cualquier instalación en la edición sin
    límites. `edicion.json` vive del lado del cliente: creerle es regalarlo."""
    monkeypatch.delenv("KOBRA_OWNER_TOKEN", raising=False)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    (tmp_path / "edicion.json").write_text(
        json.dumps({"edition": "Owner", "plan": None, "dias": None,
                    "owner": True}), encoding="utf-8")
    ed = kedicion.activar(str(tmp_path))
    assert not (ed or {}).get("owner"), "un sello sin firma activó owner"
    assert os.environ.get("KOBRA_OWNER_TOKEN") is None
    assert kedicion.es_owner() is False


def test_sin_edicion_no_se_inventa_un_bloqueo(tmp_path):
    """Correr desde el repo (sin `edicion.json`) no puede quedar bloqueado."""
    assert kedicion.activar(str(tmp_path)) is None
