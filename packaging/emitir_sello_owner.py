# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Emite el sello del dueño y lo deja guardado
=========================================================
Reemplaza esto, que había que escribir a mano en una consola:

    KOBRA_LICENSE_PRIVATE_KEY=... python -c \\
      "from backend_venta import licencias as l; print(l.emitir_sello_owner())"

Tres cosas lo hacían incómodo y las tres eran evitables: las comillas anidadas
(en `cmd` de Windows hay que escaparlas y es donde se rompe), tener que poner
una variable de entorno con una clave RSA de varias líneas ANTES de correrlo
—cosa que `set` no hace bien—, y que el resultado saliera por pantalla para
copiarlo y pegarlo a mano, que es justo el paso donde el token se corta.

Acá la clave se lee de un ARCHIVO (`.pem`) y el token se escribe DIRECTO al
archivo donde lo va a buscar el build. Ni la clave ni el token pasan nunca por
la pantalla, el portapapeles o el historial de la consola.

Se usa con `packaging\\generar_sello_owner.bat` (doble clic). A mano:

    python packaging/emitir_sello_owner.py --clave C:\\ruta\\privada.pem

Sobre rotar la clave
--------------------
Este script NO genera un par nuevo, a propósito. La privada que firma el sello
del dueño es la MISMA que firma las licencias vendidas: cambiarla invalida
todas las licencias ya entregadas a clientes que pagaron. Si la clave se
perdió, eso es una decisión comercial, no un paso de un build.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Dónde queda el sello: fuera del repo, en el perfil del usuario. Dentro del
# repo sería una credencial a un `git add -A` de distancia.
DESTINO_POR_DEFECTO = os.path.join(
    os.path.expanduser("~"), ".kobra", "sello_owner.txt")
ENV_CLAVE = "KOBRA_LICENSE_PRIVATE_KEY"


def clave_privada(archivo: str | None) -> str:
    """La privada, del archivo indicado o de la variable de entorno.

    El archivo va primero: una clave RSA tiene saltos de línea y `set` de
    Windows no los conserva, así que la vía del archivo es la que de verdad
    funciona en la PC del dueño.
    """
    if archivo:
        try:
            with open(archivo, encoding="utf-8-sig") as f:
                pem = f.read()
        except OSError as e:
            raise SystemExit(f"[ERROR] no pude leer la clave de {archivo}: {e}") from e
        if "PRIVATE KEY" not in pem:
            # El encabezado se nombra con puntos suspensivos en el medio a
            # propósito: `tests/test_licencia_comprada_activa.py` hace
            # `git grep` del marcador entero para atajar una clave privada
            # commiteada, y escribirlo seguido acá haría que este archivo lo
            # encuentre — un guard de seguridad en rojo por una frase.
            raise SystemExit(
                f"[ERROR] {archivo} no parece una clave privada.\n"
                "  La primera línea tiene que ser -----BEGIN ... PRIVATE KEY-----\n"
                "  (sirven tanto la forma PKCS8 como la RSA).\n"
                "  Ojo: la PÚBLICA no sirve para firmar.")
        return pem
    pem = os.environ.get(ENV_CLAVE, "")
    if not pem.strip():
        raise SystemExit(
            "[ERROR] falta la clave privada del dueño.\n"
            f"  Pasala con --clave <ruta.pem>, o ponela en {ENV_CLAVE}.\n"
            "  Es la misma que firma las licencias vendidas: la tenés en las\n"
            "  variables de entorno del servidor de ventas (Vercel →\n"
            f"  Settings → Environment Variables → {ENV_CLAVE}).\n"
            "  Guardala en un .pem en tu PC, fuera del repo.")
    return pem


def emitir(pem: str, dias: int) -> str:
    """El token firmado. Sale de `backend_venta.licencias`, que es el ÚNICO
    lugar donde se arman los claims — si se emitiera acá aparte, un cambio en
    el formato dejaría sellos que el programa no reconoce."""
    os.environ[ENV_CLAVE] = pem
    try:
        from backend_venta import licencias as klic
        return klic.emitir_sello_owner(dias=dias)
    except Exception as e:
        raise SystemExit(
            f"[ERROR] no pude firmar el sello: {e}\n"
            "  Si dice algo de 'Could not deserialize', la clave está\n"
            "  incompleta o es de otro formato.") from e
    finally:
        # No dejarla en el entorno del proceso más de lo necesario.
        os.environ.pop(ENV_CLAVE, None)


def guardar(token: str, destino: str) -> str:
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(token + "\n")
    # Permisos restrictivos donde el sistema los respeta. En Windows no hace
    # nada y no se finge que sí: ahí lo que protege el archivo es estar en el
    # perfil del usuario.
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return destino


def comprobar(token: str) -> None:
    """Que el sello recién emitido lo acepte el programa, con el mismo código
    que corre al arrancar. Si la pública embebida y esta privada no son del
    mismo par, se sabe ACÁ y no después de compilar el instalador."""
    from kobra import edicion as kedicion
    if not kedicion.sello_owner_valido({"token_owner": token}):
        raise SystemExit(
            "[ERROR] el sello se firmó pero el programa NO lo acepta.\n"
            "  Esa clave privada no es del par de la pública embebida en el\n"
            "  programa (backend_venta/licencia_clave.py). Revisá que sea la\n"
            "  clave de ventas actual y no una vieja.\n"
            "  (no se guardó nada)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Emite el sello de la edición Owner y lo guarda.")
    p.add_argument("--clave", default=None,
                   help="archivo .pem con la clave privada del dueño")
    p.add_argument("--destino", default=DESTINO_POR_DEFECTO,
                   help=f"dónde guardar el sello (por defecto {DESTINO_POR_DEFECTO})")
    p.add_argument("--dias", type=int, default=3650,
                   help="vigencia del sello en días (por defecto 3650, ~10 años)")
    args = p.parse_args(argv)

    token = emitir(clave_privada(args.clave), args.dias)
    comprobar(token)                       # antes de guardar, no después
    ruta = guardar(token, args.destino)
    # El tamaño y no el token: esta salida queda en la consola del dueño y a
    # veces en un log.
    print(f"[OK] sello del dueño guardado en {ruta} "
          f"({os.path.getsize(ruta)} bytes, vigencia {args.dias} días)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
