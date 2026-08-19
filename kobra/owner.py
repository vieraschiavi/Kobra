# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Desbloqueo de la copia del dueño (owner)
=======================================================
La copia del dueño entra sin licencia, sin trial y sin vencimiento. Hasta acá
eso era una decisión de BUILD: el ZIP de la edición Owner traía
`edicion.json` con `owner: true` y el launcher exportaba `KOBRA_OWNER=1`. El
instalador público (`MVKobraAI_Setup.exe`) no tenía forma de llegar a ese modo.

Este módulo agrega la otra vía: desbloquear owner **en cualquier build**,
incluido el instalador público, escribiendo la credencial en el mismo campo
donde un cliente pega su licencia.

Por qué mail + código y no solo el mail
----------------------------------------
El instalador que baja un cliente y el que usa el dueño son el MISMO binario.
Si alcanzara con escribir el mail, cualquiera que lo conozca —y está en los
commits de este repo, además de ser un Gmail real— se quedaría con el producto
completo gratis, y los planes pagos dejarían de tener sentido. El mail
identifica; el código autentica.

Qué se guarda acá y qué no
---------------------------
* El **mail** va en claro: no es un secreto, es un identificador.
* Del **código** se guarda solo `scrypt(codigo, sal)`. Publicar el hash y la
  sal no permite derivar el código: scrypt es deliberadamente caro en tiempo y
  memoria, y el código tiene ~125 bits de entropía (25 caracteres de un
  alfabeto de 32, sin los ambiguos O/0 e I/1/l). Probar candidatos contra este
  hash no es viable.
* El **código en claro no está en el repositorio** y no debe agregarse nunca.
  Vive donde lo guarde el dueño (gestor de contraseñas).

Para rotarlo, correr `python -m kobra.owner --nuevo-codigo`, pegar la SAL y el
HASH que imprime, y guardar el código aparte.
"""
from __future__ import annotations

import hashlib
import hmac

# Identificador del dueño. No es secreto.
EMAIL = "vieraschiavi@gmail.com"

# scrypt(codigo, SAL). Publicables: sin el código no sirven de nada.
_SAL = bytes.fromhex("13c8a3fa47e247bd5fc3d4b2650c8ccb")
_HASH = bytes.fromhex(
    "d6a1711f7c425876f1a75c5b84c86236fb8459c78a3bee8e1c64237d63eb6d61")

# Parámetros de scrypt. `maxmem` explícito porque el default de OpenSSL
# (32 MB) no alcanza para n=2**15 y falla con "memory limit exceeded".
_N, _R, _P, _DKLEN = 2 ** 15, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024

# Separador entre mail y código. El `|` no aparece en direcciones de correo ni
# en el alfabeto del código, así que partir por él nunca es ambiguo.
SEPARADOR = "|"


def _derivar(codigo: str) -> bytes:
    return hashlib.scrypt(codigo.encode("utf-8"), salt=_SAL, n=_N, r=_R,
                          p=_P, dklen=_DKLEN, maxmem=_MAXMEM)


def partir(texto: str):
    """`"mail|codigo"` -> `(mail, codigo)`; `None` si no tiene esa forma.

    Devolver `None` en vez de lanzar deja que el llamador trate el texto como
    lo que probablemente sea: un token de licencia normal.
    """
    if not texto or SEPARADOR not in texto:
        return None
    mail, _, codigo = texto.partition(SEPARADOR)
    mail, codigo = mail.strip().lower(), codigo.strip()
    if not mail or not codigo:
        return None
    return mail, codigo


def verificar(texto: str) -> bool:
    """¿`texto` es la credencial del dueño?

    Compara en tiempo constante (`compare_digest`): con `==`, el tiempo de
    respuesta filtra cuántos bytes coincidieron y permite reconstruir el hash
    byte a byte. Además el mail se compara igual, para no filtrar por timing
    si el mail es el correcto y solo falla el código.
    """
    partes = partir(texto)
    if partes is None:
        return False
    mail, codigo = partes
    mail_ok = hmac.compare_digest(mail, EMAIL.lower())
    codigo_ok = hmac.compare_digest(_derivar(codigo), _HASH)
    return mail_ok and codigo_ok


def _nuevo_codigo():
    """Genera un código nuevo e imprime la SAL y el HASH para pegar arriba."""
    import secrets
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin O/0 ni I/1/l
    codigo = "-".join("".join(secrets.choice(alfabeto) for _ in range(5))
                      for _ in range(5))
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(codigo.encode(), salt=sal, n=_N, r=_R, p=_P,
                       dklen=_DKLEN, maxmem=_MAXMEM)
    print("CODIGO (guardalo, no va al repositorio):", codigo)
    print("_SAL  =", repr(sal.hex()))
    print("_HASH =", repr(h.hex()))


if __name__ == "__main__":
    import sys
    if "--nuevo-codigo" in sys.argv:
        _nuevo_codigo()
    else:
        print(__doc__)
