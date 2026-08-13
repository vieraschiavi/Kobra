# © 2026 Martín Viera. Todos los derechos reservados.
"""El instalador .exe de la edición Owner (release_owner.yml → instalador).

Pedido: «poneme un instalador exe owner aparte en github que no puedan usar
los clientes pero que funcione igual que version full solamente para mi».

Hasta acá la edición Owner se publicaba solo como ZIP, que necesita Python en
la máquina. Este job arma el INSTALADOR de Windows del dueño con el mismo
pipeline que el de clientes (PyInstaller + Electron + NSIS): asistente
gráfico, iconos, desinstalador y sin Python.

Las tres cosas que estos tests fijan, porque romper cualquiera es silencioso y
caro:

1. **Que sea de verdad Owner.** Si `edicion.json` no viaja en el bundle, el
   instalador "Owner" pide licencia como el de un cliente: el mismo producto
   con otro nombre, y el dueño se entera al abrirlo.

2. **Que no pise la copia de cliente.** Con el mismo `appId`, instalar el Owner
   reemplaza la entrada en «Agregar o quitar programas», la carpeta y los
   accesos directos del instalador de clientes. Con identidad separada las dos
   conviven — que es lo que hace falta para probar qué ve un comprador sin
   perder la copia propia.

3. **Que no se publique donde lo vea un cliente.** Esta edición arranca sin
   licencia y sin vencimiento: publicarla en el repo público de descargas
   equivale a regalar el producto completo.
"""
import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "release_owner.yml")
CFG = os.path.join(ROOT, "electron", "electron-builder.owner.yml")
CFG_CLIENTE = os.path.join(ROOT, "electron", "package.json")


@pytest.fixture(scope="module")
def wf():
    with open(WF, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def wf_texto():
    with open(WF, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def cfg():
    with open(CFG, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def cfg_cliente():
    import json
    with open(CFG_CLIENTE, encoding="utf-8") as f:
        return json.load(f)["build"]


# --- 1) Que sea de verdad la edición Owner ---------------------------------
def test_hay_un_job_que_arma_el_instalador_en_windows(wf):
    assert "instalador" in wf["jobs"], "no existe el job del instalador Owner"
    assert wf["jobs"]["instalador"]["runs-on"] == "windows-latest"


def test_el_bundle_se_marca_como_owner(wf_texto):
    """`kobra_launcher.py::_activar_edicion` lee `edicion.json` al arrancar."""
    assert '"owner":true' in wf_texto.replace(" ", "")
    assert "edicion.json" in wf_texto


def test_el_spec_incluye_la_marca_de_edicion():
    """Sin esto, el edicion.json que escribe el workflow no viaja en el bundle
    y el instalador Owner pide licencia como el de un cliente."""
    with open(os.path.join(ROOT, "packaging", "kobra.spec"), encoding="utf-8") as f:
        spec = f.read()
    assert "edicion.json" in spec
    assert 'datas.append((_edicion, "."))' in spec


def test_se_verifica_que_la_marca_entro_al_bundle(wf_texto):
    """Un `edicion.json` que no llegó al bundle es un fallo silencioso: el .exe
    se arma igual y recién al abrirlo pide licencia."""
    assert "no entro al bundle" in wf_texto


def test_la_prueba_de_humo_exige_que_arranque_EN_MODO_OWNER(wf_texto):
    """No alcanza con que el motor responda 200: tiene que responder que está
    en modo owner. Si respondiera pidiendo licencia, el instalador sería
    inútil para lo que se armó."""
    assert "NO en modo owner" in wf_texto
    assert "estado.owner" in wf_texto


def test_edicion_json_no_esta_commiteada():
    """Si quedara en el repo, el instalador de CLIENTES se armaría como Owner:
    entraría sin licencia y regalaría el producto."""
    assert not os.path.exists(os.path.join(ROOT, "edicion.json")), \
        "edicion.json quedo en el repo: el instalador de clientes saldria Owner"
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        assert "/edicion.json" in f.read(), "edicion.json no esta ignorada"


# --- 2) Que conviva con la copia de cliente --------------------------------
@pytest.mark.parametrize("clave", ["appId", "productName", "artifactName"])
def test_la_identidad_es_distinta_a_la_del_instalador_de_clientes(
        cfg, cfg_cliente, clave):
    """Con el mismo appId, instalar el Owner PISA la copia de cliente: misma
    entrada en «Agregar o quitar programas», misma carpeta, mismos accesos."""
    assert cfg[clave] != cfg_cliente[clave], \
        f"{clave} coincide con el instalador de clientes: se pisan"


def test_los_accesos_directos_no_se_pisan(cfg, cfg_cliente):
    """Mismo nombre de acceso = el del Owner reemplaza al del cliente en el
    Escritorio y en el Menú Inicio."""
    assert cfg["nsis"]["shortcutName"] != cfg_cliente["nsis"]["shortcutName"]
    assert cfg["nsis"]["uninstallDisplayName"] != cfg_cliente["nsis"]["uninstallDisplayName"]


def test_la_carpeta_de_salida_es_propia(cfg, cfg_cliente):
    """Si compartieran carpeta de salida, un build pisaría el artefacto del
    otro y se publicaría el equivocado."""
    assert cfg["directories"]["output"] != cfg_cliente["directories"]["output"]


def test_el_instalador_owner_se_llama_distinto(cfg):
    """Que el nombre del archivo diga qué es: los dos .exe van a convivir en la
    carpeta de descargas."""
    assert "OWNER" in cfg["artifactName"].upper()


def test_conserva_el_asistente_completo(cfg):
    """El Owner no es una versión degradada: mismo asistente que el cliente."""
    assert cfg["nsis"]["oneClick"] is False
    assert cfg["nsis"]["allowToChangeInstallationDirectory"] is True
    assert cfg["nsis"]["createDesktopShortcut"] is True
    assert cfg["nsis"]["createStartMenuShortcut"] is True


# --- 3) Que no llegue a un cliente -----------------------------------------
def test_no_se_publica_en_el_repo_publico_de_descargas(wf):
    """`mv-kobra-ai-releases` es PÚBLICO. Esta edición arranca sin licencia:
    publicarla ahí es regalar el producto completo.

    El gate mira el YAML parseado y no el texto: los comentarios del workflow
    nombran ese repo justamente para explicar por qué NO se publica ahí, y
    buscarlo como texto da un falso positivo contra la explicación."""
    for nombre, job in wf["jobs"].items():
        for paso in job["steps"]:
            destino = (paso.get("with") or {}).get("repository", "")
            assert "mv-kobra-ai-releases" not in str(destino), \
                f"el job '{nombre}' publica en el repo publico de descargas"


def test_no_se_marca_como_latest(wf_texto):
    """`/releases/latest/download/` es el enlace que usa la landing para el
    instalador de CLIENTES. Si el Owner se marcara `latest`, un comprador se
    bajaría la edición sin licencia."""
    assert wf_texto.count("make_latest: false") >= 2, \
        "algun paso del Owner puede quedar como release `latest`"


def test_el_tag_del_owner_no_choca_con_el_de_clientes(wf_texto):
    """Los builds de clientes taguean `vX.Y.Z`; el Owner usa `owner-vX.Y.Z`.
    Con el mismo tag, uno sobreescribiría los assets del otro."""
    assert "owner-v" in wf_texto
