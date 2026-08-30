"""Configuración y carga de credenciales.

Las credenciales NUNCA se escriben en el código ni se commitean: salen de
variables de entorno o de un .env que está en .gitignore.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# LinkedIn corta una versión nueva por mes y soporta cada una por al menos un
# año. Se fija a propósito en vez de calcularla desde la fecha de hoy: una
# versión que cambia sola el día 1 de cada mes es un cambio de comportamiento
# que nadie pidió y que rompe sin aviso.
VERSION_API = os.getenv("LINKEDIN_API_VERSION", "202608")

BASE_API = "https://api.linkedin.com"
BASE_AUTH = "https://www.linkedin.com/oauth/v2"

# w_member_social es el que permite publicar. openid y profile son los que
# permiten averiguar QUIEN sos, que hace falta para armar el URN de autor.
SCOPES = ["openid", "profile", "w_member_social"]

RUTA_TOKEN = Path(os.getenv("LINKEDIN_TOKEN_PATH", Path.home() / ".mv-linkedin-token.json"))


class FaltaConfiguracion(RuntimeError):
    """Falta una credencial. El mensaje dice cuál y dónde ponerla."""


@dataclass(frozen=True)
class Credenciales:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def desde_entorno(cls) -> Credenciales:
        _cargar_dotenv()
        faltantes = [k for k in ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET") if not os.getenv(k)]
        if faltantes:
            raise FaltaConfiguracion(
                f"Falta {' y '.join(faltantes)}.\n"
                "Copiá .env.example a .env y completá los valores de tu app "
                "en https://www.linkedin.com/developers/apps"
            )
        return cls(
            client_id=os.environ["LINKEDIN_CLIENT_ID"],
            client_secret=os.environ["LINKEDIN_CLIENT_SECRET"],
            # Tiene que coincidir EXACTAMENTE con la URL autorizada en la app.
            # LinkedIn compara el string completo, incluida la barra final.
            redirect_uri=os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8765/callback"),
        )


def _cargar_dotenv() -> None:
    """Lee .env sin depender de python-dotenv: una dependencia menos."""
    ruta = Path(os.getenv("LINKEDIN_DOTENV", ".env"))
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        # No se pisa lo que ya está en el entorno: una variable exportada a
        # mano tiene que ganarle al archivo, no al revés.
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
