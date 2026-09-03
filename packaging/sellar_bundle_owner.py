# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Sella el bundle como edición OWNER
================================================
Escribe el `edicion.json` firmado dentro del bundle de PyInstaller para que el
instalador que salga de ahí sea el del dueño: entra directo, sin licencia, sin
trial y sin vencimiento.

Es el equivalente local de dos pasos del workflow `release_owner.yml`
("Marcar el bundle como edición Owner" + "Verificar que el bundle quedó
marcado"), que hoy no se pueden correr porque las Actions del repo están sin
cupo. El mismo sello, escrito desde la PC del dueño.

De dónde sale el token
----------------------
El sello lleva un token RS256 firmado con la privada del dueño. `owner: true`
a secas no vale nada — `kobra/edicion.py::sello_owner_valido` lo verifica
contra la pública embebida en el programa. El token se emite UNA vez:

    KOBRA_LICENSE_PRIVATE_KEY=... python3 -c \\
      "from backend_venta import licencias as l; print(l.emitir_sello_owner())"

y se guarda. Este script lo lee de `KOBRA_OWNER_SELLO` o del archivo que se le
indique. **Nunca lo imprime** ni lo deja en un log: es una credencial, y quien
la tenga puede convertir cualquier instalación en la edición sin límites.

Por qué VERIFICA el token antes de escribirlo
---------------------------------------------
Un token cortado al copiar y pegar (le falta el último tramo, o viaja con un
salto de línea en el medio) produce un `edicion.json` de aspecto perfecto que
el programa rechaza al arrancar. El resultado sería un `MVKobraAI_Setup_OWNER.exe`
de 270 MB, veinte minutos de compilación, y una copia que pide licencia igual
que la de un cliente. Acá el token se valida con el MISMO código que corre en
el arranque; si no pasa, no se escribe nada.

Uso:
    python packaging/sellar_bundle_owner.py                    # sella dist/MVKobraAI
    python packaging/sellar_bundle_owner.py --bundle dist/X    # otra carpeta
    python packaging/sellar_bundle_owner.py --solo-verificar   # sin escribir
    python packaging/sellar_bundle_owner.py --sello-archivo C:\\ruta\\sello.txt
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Import por directorio y no `from packaging import ...`: el nombre `packaging`
# ya lo ocupa la librería homónima de PyPI (misma razón que en
# generar_owner_bat.py, de donde sale la ÚNICA definición del sello).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ENV_SELLO = "KOBRA_OWNER_SELLO"
ENV_ARCHIVO = "KOBRA_OWNER_SELLO_ARCHIVO"
BUNDLE_POR_DEFECTO = os.path.join("dist", "MVKobraAI")


def token_del_entorno(archivo: str | None = None) -> str:
    """El token firmado, de la variable o del archivo. Sin él no hay Owner.

    El archivo existe porque una variable de entorno con un JWT de 700
    caracteres es incómoda de pegar en una consola de Windows y queda en el
    historial de `cmd`. Un archivo suelto fuera del repo se guarda una vez.
    """
    crudo = os.environ.get(ENV_SELLO, "")
    origen = archivo or os.environ.get(ENV_ARCHIVO, "")
    if not crudo.strip() and origen:
        try:
            with open(origen, encoding="utf-8-sig") as f:
                crudo = f.read()
        except OSError as e:
            raise SystemExit(
                f"[ERROR] no pude leer el sello de {origen}: {e}") from e
    # Un token pegado desde un mail o un chat llega partido en varias líneas.
    # Un JWT no lleva espacios, así que juntarlo es seguro y evita el caso más
    # común de "el sello no me valida".
    token = "".join(crudo.split())
    if not token:
        raise SystemExit(
            "[ERROR] falta el sello del dueño.\n"
            "  Generalo una sola vez con doble clic en:\n"
            "      packaging\\generar_sello_owner.bat\n"
            "  (te pide el .pem de la clave privada, firma el sello, lo guarda\n"
            "   y deja la variable puesta — no hay que copiar ni pegar nada)\n"
            f"  Si ya lo tenés: ponelo en {ENV_SELLO}, apuntá {ENV_ARCHIVO}\n"
            "  al archivo, o pasá --sello-archivo <ruta>.\n"
            "  Sin él, el instalador saldría pidiendo licencia como el de un cliente.")
    return token


def verificar(token: str) -> None:
    """El mismo control que hace el programa al arrancar, pero ahora — no
    después de compilar durante veinte minutos."""
    from kobra import edicion as kedicion
    if not kedicion.sello_owner_valido({"token_owner": token}):
        raise SystemExit(
            "[ERROR] el sello no valida contra la clave pública del programa.\n"
            "  Suele ser un token incompleto (se cortó al copiar) o de otro par\n"
            "  de claves. Volvé a emitirlo y guardalo entero.\n"
            "  (no se escribió nada: el bundle quedó como estaba)")


def carpeta_sello(bundle: str) -> str:
    """Dónde va el archivo: `_internal/` es `sys._MEIPASS` en un build onedir
    de PyInstaller 6, que es de donde `kobra/edicion.py` lo lee al arrancar.
    En builds más viejos era la raíz del bundle."""
    interno = os.path.join(bundle, "_internal")
    return interno if os.path.isdir(interno) else bundle


def sellar(bundle: str, token: str) -> str:
    """Escribe el sello y devuelve la ruta. El JSON lo arma `generar_owner_bat`
    para que la herramienta, el CI y este script no puedan separarse."""
    import generar_owner_bat

    if not os.path.isdir(bundle):
        raise SystemExit(
            f"[ERROR] no existe el bundle {bundle}.\n"
            "  Compilá primero el motor:  python -m PyInstaller packaging/kobra.spec")
    destino = os.path.join(carpeta_sello(bundle), "edicion.json")
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(generar_owner_bat.sello(token))
    return destino


def comprobar_lo_escrito(ruta: str) -> None:
    """Releer lo que quedó en disco y activarlo de verdad. Si el instalador va
    a salir sin licencia, que lo demuestre acá y no en la máquina del dueño."""
    from kobra import edicion as kedicion
    ed = kedicion.leer(os.path.dirname(ruta))
    if not ed or not ed.get("owner") or not kedicion.sello_owner_valido(ed):
        raise SystemExit(f"[ERROR] el sello quedó mal escrito en {ruta}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sella el bundle como edición Owner.")
    p.add_argument("--bundle", default=BUNDLE_POR_DEFECTO,
                   help=f"carpeta del bundle de PyInstaller (por defecto {BUNDLE_POR_DEFECTO})")
    p.add_argument("--sello-archivo", default=None,
                   help="archivo con el token firmado (alternativa a KOBRA_OWNER_SELLO)")
    p.add_argument("--solo-verificar", action="store_true",
                   help="comprobar que el sello existe y valida, sin tocar el bundle")
    args = p.parse_args(argv)

    token = token_del_entorno(args.sello_archivo)
    verificar(token)
    if args.solo_verificar:
        print("[OK] sello del dueño presente y válido.")
        return 0

    ruta = sellar(args.bundle, token)
    comprobar_lo_escrito(ruta)
    # El tamaño y no el contenido: el token es una credencial y esta salida
    # termina en la consola del build (y a veces en un archivo de log).
    print(f"[OK] bundle sellado como OWNER: {ruta} ({os.path.getsize(ruta)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
