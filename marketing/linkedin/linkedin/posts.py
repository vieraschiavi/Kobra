"""Los posts se leen de archivos de texto, no se pasan por la línea de comandos.

Motivo: un post de LinkedIn tiene saltos de línea, comillas y acentos. Pasarlo
como argumento de shell lo rompe de maneras que no se ven hasta que ya está
publicado. Un archivo se revisa antes, se versiona y se corrige.

Formato:

    # idioma: es
    # visibilidad: PUBLIC
    Cuerpo del post, tal cual va a salir.

    --- comentario ---
    El primer comentario, con el link.

La línea de comentario es opcional. Todo lo que empieza con "# clave: valor"
antes del cuerpo son metadatos y NO se publica.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SEPARADOR = re.compile(r"^-{2,}\s*comentario\s*-{2,}\s*$", re.IGNORECASE | re.MULTILINE)
_META = re.compile(r"^#\s*([a-zA-Z_]+)\s*:\s*(.+)$")


class ErrorFormato(ValueError):
    pass


@dataclass(frozen=True)
class PostArchivo:
    ruta: Path
    cuerpo: str
    comentario: str = ""
    idioma: str = ""
    visibilidad: str = "PUBLIC"

    @property
    def tiene_comentario(self) -> bool:
        return bool(self.comentario.strip())


def leer(ruta: Path) -> PostArchivo:
    if not ruta.is_file():
        raise ErrorFormato(f"No existe el archivo: {ruta}")
    texto = ruta.read_text(encoding="utf-8")

    partes = SEPARADOR.split(texto)
    if len(partes) > 2:
        raise ErrorFormato(
            f"{ruta}: hay más de un separador '--- comentario ---'. "
            "Un post tiene un solo primer comentario."
        )
    cabeza = partes[0]
    comentario = partes[1].strip() if len(partes) == 2 else ""

    meta: dict[str, str] = {}
    lineas_cuerpo: list[str] = []
    en_cabecera = True
    for linea in cabeza.splitlines():
        m = _META.match(linea) if en_cabecera else None
        if m:
            meta[m.group(1).lower()] = m.group(2).strip()
            continue
        if en_cabecera and not linea.strip():
            # Las líneas en blanco de la cabecera no cuentan como cuerpo.
            if not lineas_cuerpo:
                continue
        en_cabecera = False
        lineas_cuerpo.append(linea)

    cuerpo = "\n".join(lineas_cuerpo).strip()
    if not cuerpo:
        raise ErrorFormato(f"{ruta}: el cuerpo del post está vacío.")

    return PostArchivo(
        ruta=ruta,
        cuerpo=cuerpo,
        comentario=comentario,
        idioma=meta.get("idioma", ""),
        visibilidad=meta.get("visibilidad", "PUBLIC").upper(),
    )
