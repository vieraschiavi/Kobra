# © 2026 Martín Viera. Todos los derechos reservados.

"""Un `.env` de este proyecto es, por definición, un archivo de secretos.

El README manda poner ahí `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`MP_ACCESS_TOKEN`, `KOBRA_LICENSE_PRIVATE_KEY`, `RESEND_API_KEY` y
`TWILIO_AUTH_TOKEN`. O sea: el archivo que el propio producto le pide al
cliente que cree es el que junta todas las llaves del negocio.

Estaba sin ignorar. `docs/AUDITORIA_PRODUCCION.md` daba por hecho que "el .env
no está trackeado", y era cierto **solo porque todavía nadie había creado
uno** — no porque algo lo impidiera. El primer `git add .` lo subía.

Y no es un error que se arregle con un commit: una clave privada de licencias
que entró al historial hay que rotarla, y con ella se re-emiten todas las
licencias vendidas.
"""
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Los nombres con los que la gente guarda secretos de verdad.
ARCHIVOS_DE_SECRETOS = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.produccion",
    "produccion.env",
    "webapp/.env",
    "api/.env",
]


def _git_ignora(ruta: str) -> bool:
    """Le pregunta a git de verdad, en vez de leer .gitignore a mano.

    Importa la diferencia: las reglas de .gitignore tienen precedencia,
    negaciones y alcance por directorio. Un test que hiciera `".env" in
    open(".gitignore").read()` pasaría con una regla mal escrita que git no
    aplica.
    """
    r = subprocess.run(["git", "check-ignore", "-q", ruta],
                       cwd=ROOT, capture_output=True)
    return r.returncode == 0


@pytest.mark.parametrize("archivo", ARCHIVOS_DE_SECRETOS)
def test_un_archivo_de_entorno_no_se_puede_commitear(archivo):
    assert _git_ignora(archivo), (
        f"git NO ignora {archivo}: un `git add .` subiría las claves del "
        "negocio al repositorio")


def test_la_plantilla_de_ejemplo_si_se_versiona():
    """`.env.example` es lo contrario: la lista de qué variables hacen falta,
    con los valores en blanco. Ese sí tiene que viajar, o el que clona el repo
    no sabe qué configurar."""
    assert not _git_ignora(".env.example"), (
        "la plantilla sin secretos quedó ignorada: quien clone el repo no va a "
        "saber qué variables configurar")


def test_no_hay_ningun_secreto_ya_rastreado():
    """El control de fondo: que ninguno de estos archivos esté YA en el índice
    de git. Ignorarlos a futuro no sirve si uno entró antes."""
    seguidos = subprocess.run(["git", "ls-files"], cwd=ROOT,
                              capture_output=True, text=True).stdout.split("\n")
    sospechosos = [f for f in seguidos
                   if f and (os.path.basename(f).startswith(".env")
                             or f.endswith(".env")
                             or f.endswith(".pem"))
                   and not f.endswith(".env.example")]
    assert not sospechosos, (
        "hay archivos de secretos rastreados por git: " + ", ".join(sospechosos) +
        ". Sacarlos del índice NO alcanza — lo que entró al historial hay que "
        "rotarlo.")


def test_el_sello_owner_sigue_sin_poder_commitearse():
    """`packaging/Owner.bat` lleva un token firmado con la privada del dueño:
    convierte cualquier instalación en la edición sin límites. Ya estaba
    ignorado; esto es la red para que siga estándolo."""
    assert _git_ignora("packaging/Owner.bat"), (
        "Owner.bat dejó de estar ignorado: commitearlo regala el producto "
        "completo a cualquiera con acceso al repo")
