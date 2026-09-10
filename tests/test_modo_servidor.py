# © 2026 Martín Viera. Todos los derechos reservados.

"""El tercer modo de instalación: la app en el servidor o la VM del cliente.

El escenario que lo pide es concreto: una consultora te pone en un proyecto
para un cliente, la laptop que te dan **no deja instalar nada** —ni .exe ni
.bat— y los datos de ese cliente no pueden terminar en tu máquina. El
instalador no sirve y la carpeta portable tampoco: las dos corren del lado de
quien las abre.

La respuesta es correr el programa del lado del cliente y usarlo por el
navegador. Lo que estos tests fijan no es que el contenedor exista, sino las
tres promesas que hacen que ese modo sirva para pasar una revisión de
seguridad:

1. **Entra sin licencia** — si no, el modo no resuelve nada: quedarías
   escribiendo una licencia en el servidor de otra empresa.
2. **El sello no viaja en la imagen** — una imagen con el sello adentro
   convierte en dueño a cualquiera que la baje.
3. **Los datos quedan en volúmenes del servidor** — que es exactamente la
   pregunta que hace el área de seguridad del cliente.
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ENTRYPOINT = os.path.join(ROOT, "docker-entrypoint.sh")
DOCKERFILE = os.path.join(ROOT, "Dockerfile")
COMPOSE = os.path.join(ROOT, "docker-compose.yml")
DOCKERIGNORE = os.path.join(ROOT, ".dockerignore")


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _sin_comentarios(texto):
    """El script efectivo. Los comentarios de estos archivos EXPLICAN el
    porqué de cada regla, así que un grep crudo se encuentra la explicación a
    sí mismo y el test pasa a medir la documentación."""
    return "\n".join(re.sub(r"#.*$", "", ln) for ln in texto.splitlines())


@pytest.fixture(scope="module")
def compose():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_leer(COMPOSE))


# ---------------------------------------------------------------------------
# 1. Entra sin licencia — y no arranca a medias si no puede
# ---------------------------------------------------------------------------

def test_sin_el_sello_el_arranque_falla_y_explica_por_que():
    """Se ejecuta de verdad, no se lee.

    El fracaso silencioso sería peor que el error: la app arrancaría pidiendo
    licencia en el servidor del cliente, que es justo lo que este modo viene a
    evitar, y encima parecería que anduvo.
    """
    entorno = {k: v for k, v in os.environ.items()
               if k not in ("KOBRA_OWNER_TOKEN", "KOBRA_OWNER_TOKEN_FILE")}
    r = subprocess.run(["bash", ENTRYPOINT, "app"], cwd=ROOT, env=entorno,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 1, r.stdout + r.stderr
    salida = r.stdout + r.stderr
    assert "KOBRA_OWNER_TOKEN" in salida
    assert "generar_sello_owner" in salida, "el error tiene que decir cómo salir de él"


def test_el_modo_app_no_pide_contrasena_ademas_del_sello():
    """`KOBRA_MODO_STANDALONE=1` es lo que hace que la puerta sea la licencia
    (acá, el sello) y no un login. Sin esto el modo pediría contraseña además,
    y volvería a haber algo que escribir."""
    guion = _sin_comentarios(_leer(ENTRYPOINT))
    bloque = guion.split("app)", 1)[1].split(";;", 1)[0]
    assert "KOBRA_MODO_STANDALONE=1" in bloque
    assert "webapp.backend.api:app" in bloque


def test_el_sello_tambien_puede_llegar_como_secreto_en_un_archivo():
    """Una variable de entorno queda en `docker inspect` y en el historial del
    shell. Los orquestadores montan secretos como archivos justamente por
    eso."""
    bloque = _sin_comentarios(_leer(ENTRYPOINT)).split("app)", 1)[1]
    assert "KOBRA_OWNER_TOKEN_FILE" in bloque


# ---------------------------------------------------------------------------
# 2. El sello no viaja en la imagen
# ---------------------------------------------------------------------------

def test_la_imagen_no_trae_el_sello_adentro():
    """Una imagen con el sello horneado convierte en dueño a cualquiera que la
    baje: es el mismo producto regalado, con otro formato."""
    docker = _sin_comentarios(_leer(DOCKERFILE))
    for linea in docker.splitlines():
        if linea.strip().startswith(("ENV", "ARG")):
            assert "KOBRA_OWNER_TOKEN" not in linea, linea
            assert "KOBRA_OWNER_SELLO" not in linea, linea
    assert "KOBRA_LICENSE_PRIVATE_KEY" not in docker, (
        "la privada del dueño no puede estar ni nombrada en la imagen")


def _patrones_dockerignore():
    lineas = _leer(DOCKERIGNORE).splitlines()
    return [ln.strip() for ln in lineas
            if ln.strip() and not ln.strip().startswith("#")]


def _a_regex(patron):
    """Un patrón de `.dockerignore` como lo entiende Docker, no como fnmatch.

    La diferencia importa acá: en `fnmatch` el `*` cruza las barras, así que
    `*.env` "taparía" `webapp/.env` y el test daría verde sobre un archivo que
    `docker build` igual mete en la imagen. Docker usa `filepath.Match`, donde
    `*` NO cruza `/`, más `**` para lo anidado.
    """
    salida, i = [], 0
    while i < len(patron):
        if patron[i] == "*":
            if patron[i:i + 2] == "**":
                salida.append(".*")
                i += 2
                continue
            salida.append("[^/]*")
        elif patron[i] == "?":
            salida.append("[^/]")
        else:
            salida.append(re.escape(patron[i]))
        i += 1
    return re.compile("^" + "".join(salida) + "$")


def _queda_afuera(ruta):
    """¿`docker build` deja esta ruta afuera del contexto?

    Un patrón que coincide con una carpeta se lleva todo lo que cuelga de
    ella, así que se prueba contra la ruta y contra cada prefijo suyo. Gana el
    último patrón que coincide: por eso `!env.example` puede rescatar un
    archivo que una regla anterior excluyó.
    """
    partes = ruta.strip("/").split("/")
    prefijos = ["/".join(partes[:i]) for i in range(1, len(partes) + 1)]
    veredicto = False
    for patron in _patrones_dockerignore():
        niega = patron.startswith("!")
        rx = _a_regex(patron.lstrip("!").rstrip("/"))
        if any(rx.match(p) for p in prefijos):
            veredicto = not niega
    return veredicto


# Lo que NO puede terminar adentro de una imagen que corre en otra empresa.
# Cada ruta es un archivo que existe (o que aparece apenas alguien usa el
# programa como dice el README), no un caso inventado.
AFUERA = [
    # `.env` de este proyecto lleva KOBRA_LICENSE_PRIVATE_KEY: con esa clave,
    # quien tenga la imagen se firma sus propias licencias y sellos Owner.
    ".env",
    ".env.produccion",
    "webapp/.env",
    "clave_licencias.pem",
    "licencias.key",
    # El ZIP de la edición Owner que deja `packaging/`, con su sello adentro.
    "dist/MVKobraAI_Owner_v1.5.0.zip",
    "edicion.json",
    "packaging/Owner.bat",
    # El lanzador de la edición del dueño: no lleva sello, pero es el mapa de
    # cómo se abre. El contenedor no lo usa.
    "owner/MVKobraAI_Owner.bat",
    "owner/ui_dist/index.html",
    # La cadena de auditoría de la instalación del dueño.
    "data/auditoria.log",
    "data/uso_licencias.db",
    # 68 MB de dependencias de desarrollo. El patrón viejo `node_modules/` no
    # las tapaba: es relativo a la raíz y estas cuelgan de webapp/frontend.
    "webapp/frontend/node_modules/vite/package.json",
    "kobra/__pycache__/pipeline.cpython-311.pyc",
]

# Lo que SÍ tiene que viajar, o la imagen no se construye ni arranca.
ADENTRO = [
    "requirements.txt",
    "Dockerfile",
    "docker-entrypoint.sh",
    "kobra/pipeline.py",
    "webapp/backend/api.py",
    "webapp/frontend/package.json",
    "webapp/frontend/package-lock.json",
    # El entrypoint regenera los datos si faltan: sin los generadores, el
    # contenedor arranca sin cartera.
    "data/generate_dataset.py",
    "data/generate_gestiones.py",
    "app/app.py",
    "env.example",
    # El entrypoint corre `kobra.pipeline` pero no `kobra.train`: si el modelo
    # entrenado no viaja, el contenedor sirve el de fallback y la priorización
    # que ve el cliente es otra (38,6% de la cartera cambia de decil).
    "outputs/probpago_model.joblib",
    "outputs/model_selection.json",
]


@pytest.mark.parametrize("ruta", AFUERA)
def test_el_contexto_de_build_no_arrastra_secretos_ni_la_edicion_owner(ruta):
    """`.gitignore` no alcanza: son dos listas distintas.

    `COPY . .` copia el contexto tal como está en el DISCO. Los tres archivos
    más peligrosos de esta lista —el `.env`, el ZIP Owner y `edicion.json`—
    están todos en `.gitignore`, o sea que no están en el repo pero sí en la
    máquina de quien construye, que es justo la que arma la imagen.
    """
    assert _queda_afuera(ruta), (
        f"{ruta} entraría en la imagen que corre en el servidor de un cliente")


@pytest.mark.parametrize("ruta", ADENTRO)
def test_el_contexto_de_build_no_se_come_lo_que_la_imagen_necesita(ruta):
    """El contrapeso del test de arriba: excluir de más rompe el build, y lo
    rompe recién en el servidor del cliente, que es el peor lugar."""
    assert not _queda_afuera(ruta), f"{ruta} hace falta para construir o arrancar"


def test_el_compose_toma_el_sello_del_entorno_y_no_lo_escribe(compose):
    entorno = compose["services"]["app"]["environment"]
    sello = [e for e in entorno if e.startswith("KOBRA_OWNER_TOKEN=")]
    assert sello, "el servicio app tiene que recibir el sello"
    # `${VAR:-}` y no un valor: el token no puede quedar commiteado.
    assert all("${" in e for e in sello), sello


# ---------------------------------------------------------------------------
# 3. Los datos quedan del lado del cliente
# ---------------------------------------------------------------------------

def test_los_datos_quedan_en_volumenes_del_servidor(compose):
    """Es la pregunta del área de seguridad: dónde queda la cartera. Con los
    datos en volúmenes del servidor, la respuesta es «acá, en su máquina»."""
    app = compose["services"]["app"]
    destinos = {v.split(":")[1] for v in app["volumes"]}
    assert "/app/data" in destinos
    assert "/app/outputs" in destinos
    assert "/config" in destinos


def test_el_puerto_no_se_publica_a_toda_la_red_por_defecto(compose):
    """Este modo entra SIN contraseña: publicado en 0.0.0.0, cualquiera que
    llegue al puerto entra como dueño. Por defecto va atado al loopback y se
    expone a mano, con un proxy con autenticación adelante."""
    puertos = compose["services"]["app"]["ports"]
    assert all(p.startswith("127.0.0.1:") for p in puertos), puertos


def test_la_interfaz_se_compila_en_la_imagen():
    """Si el dist viajara commiteado, el contenedor mostraría la interfaz del
    día que alguien se acordó de recompilarla."""
    docker = _leer(DOCKERFILE)
    assert "npm ci" in docker and "npm run build" in docker
    assert "AS ui" in docker
    assert "--from=ui" in docker, "el runtime tiene que copiar el dist compilado"
    # Node solo en la etapa de compilación: no tiene por qué quedar en la
    # imagen que corre en el servidor de un cliente.
    runtime = docker.split("FROM python:3.11-slim", 1)[1]
    assert "npm" not in runtime and "node" not in runtime


def test_el_modo_servidor_esta_documentado():
    """La documentación acá no es un extra: es lo que se le muestra al área de
    seguridad del cliente para que autorice. Tiene que contestar las tres
    preguntas que hacen: cómo se levanta, dónde quedan los datos, y qué pasa
    con el puerto."""
    doc = _leer(os.path.join(ROOT, "docs", "MODOS_INSTALACION.md")).lower()
    assert "docker compose up" in doc, "falta el comando con el que se levanta"
    assert "kobra_owner_token" in doc, "falta cómo entra sin licencia"
    assert "navegador" in doc
    assert "no instalás nada" in doc, "la promesa central del modo"
    assert "127.0.0.1" in doc, "falta la advertencia del puerto sin contraseña"
