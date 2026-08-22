# © 2026 Martín Viera. Todos los derechos reservados.

"""`docker compose up` tiene que dejar el realtime alcanzable.

`realtime/server.py` ata `127.0.0.1` por defecto, y eso está bien: quien abre
el programa en su notebook no tiene que exponer a la red de la oficina un
servicio que dispara llamadas telefónicas.

Pero el contenedor tiene su propio namespace de red. Un proceso atado al
loopback DEL CONTENEDOR no responde por el puerto que publica
`ports: ["8000:8000"]`, porque el reenvío de Docker apunta a la interfaz del
contenedor y no a su loopback. Con el default de loopback y sin nadie que lo
cambie, `docker compose up` levantaba un servicio de realtime al que no se
llegaba desde ningún lado — y el síntoma es "connection reset", que manda a
buscar el problema a cualquier lado menos al bind.

Publicar el puerto YA es la decisión explícita de exponerlo, y desde
`realtime/acceso.py` el servicio pide token. Así que adentro del contenedor
`0.0.0.0` es lo correcto, no una imprudencia.

Nota: acá no se levanta Docker (no está en CI ni en el sandbox). Lo que se fija
es la configuración que decide el bind, que es donde estaba el defecto.
"""
import os
import re

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


@pytest.fixture()
def compose():
    return yaml.safe_load(leer("docker-compose.yml"))


def entorno(servicio):
    """El bloque `environment` como dict, venga en lista o en mapa."""
    env = servicio.get("environment") or []
    if isinstance(env, dict):
        return {k: str(v) for k, v in env.items()}
    return dict(e.split("=", 1) for e in env if "=" in e)


def test_el_realtime_del_contenedor_escucha_en_la_interfaz_publicada(compose):
    env = entorno(compose["services"]["realtime"])
    assert env.get("KOBRA_REALTIME_HOST") == "0.0.0.0", (
        "el realtime del contenedor queda atado al loopback del contenedor: "
        "el puerto se publica y no responde nadie")


def test_el_entrypoint_tambien_lo_pone_para_docker_run():
    """`docker compose` no es la única forma de correr la imagen: un
    `docker run kobra realtime` sin compose tiene que andar igual."""
    sh = leer("docker-entrypoint.sh")
    rama = sh.split("realtime)")[1].split(";;")[0]
    assert "KOBRA_REALTIME_HOST" in rama, (
        "corriendo la imagen sin compose, el realtime vuelve a quedar "
        "inalcanzable")
    # Con `:-`, para que quien quiera atar otra cosa pueda.
    assert re.search(r"KOBRA_REALTIME_HOST=\"?\$\{KOBRA_REALTIME_HOST:-", rama), (
        "pisa la variable en vez de usarla como default: no se puede cambiar "
        "desde afuera")


def test_el_default_del_programa_sigue_siendo_loopback():
    """La contracara: fuera del contenedor NO se expone solo. Si esto se
    invierte, cualquiera en la red de la oficina llega a `/voz/llamar`."""
    src = leer("realtime/server.py")
    assert 'os.getenv("KOBRA_REALTIME_HOST", "127.0.0.1")' in src, (
        "el servicio volvió a exponerse a la red por default")


def test_el_contenedor_puede_recibir_los_webhooks_de_twilio(compose):
    """Desde `realtime/acceso.py`, `/voz/entrante` y `/voz/turno` exigen la
    firma de Twilio y se falla cerrado sin `TWILIO_AUTH_TOKEN`. Si compose no
    lo pasa, no hay forma de configurarlo y las llamadas cortan solas."""
    env = entorno(compose["services"]["realtime"])
    for var in ("TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL", "KOBRA_REALTIME_TOKEN"):
        assert var in env, (
            f"compose no deja pasar {var}: el canal de voz no se puede "
            "configurar desde afuera del contenedor")


def test_el_token_se_puede_encontrar(compose):
    """El servicio pide token y lo genera solo. Si el usuario no sabe dónde
    mirarlo, el candado lo deja afuera a él: el volumen de config tiene que
    persistir (si no, cambia en cada arranque) y el header del compose tiene
    que decir cómo verlo."""
    rt = compose["services"]["realtime"]
    assert any(str(v).endswith(":/config") for v in rt.get("volumes", [])), (
        "sin volumen de config, el token se regenera en cada arranque y el "
        "link que anotó el usuario deja de servir")
    cabecera = leer("docker-compose.yml")[:1200]
    assert "logs realtime" in cabecera, (
        "no dice en ningún lado cómo ver el token")
