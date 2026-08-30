"""Cliente de la API oficial de LinkedIn: publicar y comentar.

Sólo dos operaciones, porque son las dos que hacen falta para el flujo real:
el post va sin link, y el link va en el primer comentario (LinkedIn suprime
el alcance de los posts que llevan un link externo en el cuerpo).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .auth import Token
from .config import BASE_API, VERSION_API

TIEMPO_LIMITE = 30

VISIBILIDADES = ("PUBLIC", "CONNECTIONS")

# LinkedIn corta el cuerpo con un "ver más" y rechaza por encima de este largo.
LARGO_MAXIMO_POST = 3000
LARGO_MAXIMO_COMENTARIO = 1250


class ErrorAPI(RuntimeError):
    """La API contestó un error. Trae el código y el cuerpo crudo."""

    def __init__(self, codigo: int, cuerpo: str, contexto: str = "") -> None:
        self.codigo = codigo
        self.cuerpo = cuerpo
        super().__init__(f"LinkedIn devolvió {codigo}{f' al {contexto}' if contexto else ''}.\n{cuerpo}")


@dataclass(frozen=True)
class Publicado:
    urn: str
    url: str


def _url_publica(urn: str) -> str:
    # El id que va en la URL es el numérico del final del URN.
    return f"https://www.linkedin.com/feed/update/{urn}/"


class Cliente:
    """Envuelve /rest/posts y /rest/socialActions.

    `base` es un parámetro y no una constante importada a propósito: es lo que
    permite correr los tests contra un servidor local en vez de contra
    LinkedIn. Sin eso, la única forma de probar el cliente sería publicando de
    verdad en el perfil de alguien.
    """

    def __init__(self, token: Token, base: str = BASE_API, version: str = VERSION_API) -> None:
        self.token = token
        self.base = base.rstrip("/")
        self.version = version

    # ---------------------------------------------------------------- interno

    def _cabeceras(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token.access_token}",
            "Content-Type": "application/json",
            # Las dos cabeceras de abajo no son opcionales: sin LinkedIn-Version
            # la API contesta 426, y sin X-Restli-Protocol-Version interpreta el
            # cuerpo con el protocolo viejo y falla al parsear los URN.
            "LinkedIn-Version": self.version,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _post(self, ruta: str, cuerpo: dict, contexto: str) -> tuple[dict, dict]:
        req = urllib.request.Request(
            f"{self.base}{ruta}",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers=self._cabeceras(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIEMPO_LIMITE) as r:
                crudo = r.read()
                cabeceras = {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            raise ErrorAPI(e.code, e.read().decode("utf-8", "replace")[:600], contexto) from e
        except urllib.error.URLError as e:
            raise ErrorAPI(0, f"No se pudo llegar a {self.base}: {e.reason}", contexto) from e
        datos = json.loads(crudo) if crudo.strip() else {}
        return datos, cabeceras

    # ---------------------------------------------------------------- público

    def publicar(self, texto: str, visibilidad: str = "PUBLIC") -> Publicado:
        """Crea un post de texto en el perfil del dueño del token."""
        texto = texto.strip()
        if not texto:
            raise ValueError("El texto del post está vacío.")
        if len(texto) > LARGO_MAXIMO_POST:
            raise ValueError(
                f"El post tiene {len(texto)} caracteres y el máximo es {LARGO_MAXIMO_POST}."
            )
        if visibilidad not in VISIBILIDADES:
            raise ValueError(f"Visibilidad inválida: {visibilidad}. Usá una de {VISIBILIDADES}.")

        cuerpo = {
            "author": self.token.urn_autor,
            "commentary": texto,
            "visibility": visibilidad,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        datos, cabeceras = self._post("/rest/posts", cuerpo, "publicar")
        # El URN viene en la cabecera x-restli-id, no en el cuerpo: /rest/posts
        # contesta 201 con el cuerpo vacío. Leerlo del cuerpo es el error clásico
        # y deja al cliente sin el id con el que después se comenta.
        urn = cabeceras.get("x-restli-id") or datos.get("id", "")
        if not urn:
            raise ErrorAPI(201, "Se creó el post pero no vino el URN en x-restli-id.", "publicar")
        return Publicado(urn=urn, url=_url_publica(urn))

    def comentar(self, urn_post: str, texto: str) -> str:
        """Comenta un post propio. Acá es donde va el link."""
        texto = texto.strip()
        if not texto:
            raise ValueError("El comentario está vacío.")
        if len(texto) > LARGO_MAXIMO_COMENTARIO:
            raise ValueError(
                f"El comentario tiene {len(texto)} caracteres y el máximo es {LARGO_MAXIMO_COMENTARIO}."
            )
        # El URN va percent-encoded dentro del path: los ':' sin escapar hacen
        # que la ruta se parsee mal y devuelve 404.
        ruta = f"/rest/socialActions/{urllib.parse.quote(urn_post, safe='')}/comments"
        cuerpo = {
            "actor": self.token.urn_autor,
            "object": urn_post,
            "message": {"text": texto},
        }
        datos, cabeceras = self._post(ruta, cuerpo, "comentar")
        return datos.get("id") or cabeceras.get("x-restli-id", "")
