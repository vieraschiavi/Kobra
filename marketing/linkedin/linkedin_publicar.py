#!/usr/bin/env python3
"""Publica en LinkedIn con la API oficial.

Por defecto NO publica: muestra exactamente lo que saldría y termina. Publicar
requiere --publicar y una confirmación tipeada. Un post en LinkedIn no se puede
editar sin perder las métricas del original, así que el default seguro es el
que no manda nada.

    python3 linkedin_publicar.py posts/kobra-es.txt              # vista previa
    python3 linkedin_publicar.py posts/kobra-es.txt --publicar   # publica
    python3 linkedin_publicar.py --autorizar                     # sólo login
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from linkedin import posts
from linkedin.auth import token_valido
from linkedin.cliente import (
    LARGO_MAXIMO_COMENTARIO,
    LARGO_MAXIMO_POST,
    Cliente,
    ErrorAPI,
)
from linkedin.config import Credenciales, FaltaConfiguracion

CONFIRMACION = "PUBLICAR"


def _mostrar(p: posts.PostArchivo) -> None:
    etiqueta = f" · idioma {p.idioma}" if p.idioma else ""
    print(f"\n┌─ {p.ruta.name}{etiqueta} · visibilidad {p.visibilidad}")
    print("│")
    for linea in p.cuerpo.splitlines():
        print(f"│ {linea}")
    print("│")
    print(f"└─ {len(p.cuerpo)} caracteres (máximo {LARGO_MAXIMO_POST})")
    if p.tiene_comentario:
        print(f"\n  Primer comentario ({len(p.comentario)} de {LARGO_MAXIMO_COMENTARIO}):")
        for linea in p.comentario.splitlines():
            print(f"  │ {linea}")
    else:
        print("\n  Sin primer comentario. Si el post lleva link, va acá y no en el cuerpo.")


def _validar(p: posts.PostArchivo) -> list[str]:
    problemas = []
    if len(p.cuerpo) > LARGO_MAXIMO_POST:
        problemas.append(f"el cuerpo tiene {len(p.cuerpo)} caracteres y el máximo es {LARGO_MAXIMO_POST}")
    if len(p.comentario) > LARGO_MAXIMO_COMENTARIO:
        problemas.append(
            f"el comentario tiene {len(p.comentario)} caracteres y el máximo es {LARGO_MAXIMO_COMENTARIO}"
        )
    if "http://" in p.cuerpo or "https://" in p.cuerpo:
        problemas.append("hay un link en el CUERPO: LinkedIn suprime el alcance. Movelo al comentario")
    return problemas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo", nargs="?", type=Path, help="archivo del post (ver linkedin/posts.py)")
    ap.add_argument("--publicar", action="store_true", help="publica de verdad (pide confirmación)")
    ap.add_argument("--sin-comentario", action="store_true", help="no publica el primer comentario")
    ap.add_argument("--autorizar", action="store_true", help="corre sólo el login y guarda el token")
    args = ap.parse_args(argv)

    try:
        cred = Credenciales.desde_entorno()
    except FaltaConfiguracion as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 2

    if args.autorizar:
        token = token_valido(cred)
        print(f"Autorizado como: {token.nombre or token.sub}")
        return 0

    if not args.archivo:
        ap.error("falta el archivo del post (o usá --autorizar)")

    try:
        p = posts.leer(args.archivo)
    except posts.ErrorFormato as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 2

    _mostrar(p)

    problemas = _validar(p)
    if problemas:
        print("\n  Problemas:")
        for x in problemas:
            print(f"   · {x}")
        print()
        return 1

    if not args.publicar:
        print("\nVista previa. No se publicó nada. Agregá --publicar para mandarlo.\n")
        return 0

    # La confirmación se tipea entera a propósito: un [s/n] se contesta con el
    # dedo antes que con la cabeza, y esto es irreversible.
    print("\nEsto se publica en tu perfil AHORA y no se puede deshacer sin borrar el post.")
    respuesta = input(f'Escribí "{CONFIRMACION}" para confirmar: ').strip()
    if respuesta != CONFIRMACION:
        print("Cancelado. No se publicó nada.")
        return 1

    token = token_valido(cred)
    cliente = Cliente(token)
    try:
        publicado = cliente.publicar(p.cuerpo, visibilidad=p.visibilidad)
        print(f"\nPublicado: {publicado.url}")
        if p.tiene_comentario and not args.sin_comentario:
            cliente.comentar(publicado.urn, p.comentario)
            print("Primer comentario agregado.")
    except ErrorAPI as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
