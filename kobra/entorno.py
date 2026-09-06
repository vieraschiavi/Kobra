# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · ¿Esta máquina lo va a dejar correr?
==================================================
Antes de instalar nada, contesta la pregunta que importa cuando el programa
va a una computadora que no es tuya: la VM del cliente, o la laptop que te dio
la consultora que te contrata.

El problema real
----------------
En esas máquinas no sos administrador, el antivirus bloquea ejecutables sin
firma, y a veces ni siquiera se puede escribir en el disco donde te dejaron la
carpeta. Todo eso se descubre HOY de la peor manera: se instala, se abre, y
algo falla con un mensaje que no dice qué pedirle a IT.

Este módulo lo averigua antes y en treinta segundos, y cuando algo falla dice
**exactamente qué pedir**. Esa frase es la diferencia entre resolverlo en un
mail y perder una semana de idas y vueltas.

Qué NO hace
-----------
No detecta el antivirus ni AppLocker: un programa no puede preguntarle a la
política de seguridad si lo va a dejar correr, solo puede intentar y ver. Lo
que sí hace es probar las capacidades concretas que el programa necesita, que
es lo que termina fallando cuando esas políticas están activas.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
from dataclasses import dataclass

# Espacio mínimo para la instalación completa (motor + datos de demo). El
# número sale de medir el bundle, no de una estimación: `dist/MVKobraAI` pesa
# ~270 MB y los datos de la demo otro tanto.
ESPACIO_MINIMO_GB = 2.0


@dataclass(frozen=True)
class Chequeo:
    """El resultado de una comprobación, con el remedio adentro.

    `remedio` no es opcional ni decorativo: un diagnóstico que dice "falló"
    sin decir qué pedir deja al consultor exactamente donde estaba. Cuando el
    chequeo pasa, va vacío.
    """
    id: str
    titulo: str
    ok: bool
    detalle: str
    remedio: str = ""
    # Un fallo bloqueante impide usar el programa; uno no bloqueante solo
    # descarta un modo de instalación. Distinguirlos evita el diagnóstico
    # todo-rojo que no ayuda a decidir.
    bloqueante: bool = True


def _es_admin() -> bool:
    """Informativo, no un requisito: el programa NO necesita administrador.

    Se pregunta para recomendar el modo correcto — con permisos conviene el
    instalador; sin permisos, la carpeta portable.
    """
    try:
        if sys.platform == "win32":
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def puede_escribir(carpeta: str) -> Chequeo:
    """Que se pueda crear un archivo de verdad, no que la carpeta exista.

    En una VM corporativa pasa seguido: la carpeta del usuario existe y se
    lista, pero una política la deja de solo lectura. `os.access` miente en
    ese caso (mira permisos POSIX, no la ACL de Windows), así que acá se
    escribe un archivo y se borra.
    """
    try:
        os.makedirs(carpeta, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=carpeta, prefix=".kobra_",
                                         delete=True) as f:
            f.write(b"x")
        return Chequeo("escritura", "Guardar datos y configuración", True,
                       f"Se puede escribir en {carpeta}")
    except Exception as e:
        return Chequeo(
            "escritura", "Guardar datos y configuración", False,
            f"No se puede escribir en {carpeta}: {e}",
            "Pedile a IT permiso de escritura en esa carpeta, o elegí otra "
            "durante la instalación (el asistente deja cambiarla). En modo "
            "portable, poné la carpeta del programa en una unidad donde "
            "puedas escribir.")


def puerto_disponible() -> Chequeo:
    """El programa levanta un servidor en 127.0.0.1 y abre el navegador ahí.

    No sale a internet: es tráfico dentro de la misma máquina. Aun así, algunos
    endpoint protection bloquean que un proceso escuche en un socket, y ese es
    el fallo que deja al programa "abriendo" para siempre.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            puerto = s.getsockname()[1]
        return Chequeo("puerto", "Abrir la aplicación en el navegador", True,
                       f"Se puede escuchar en 127.0.0.1 (probado en {puerto})")
    except Exception as e:
        return Chequeo(
            "puerto", "Abrir la aplicación en el navegador", False,
            f"No se puede escuchar en 127.0.0.1: {e}",
            "Pedile a IT que permita a MV Kobra AI escuchar en localhost "
            "(127.0.0.1). NO es acceso a internet ni apertura de puertos hacia "
            "afuera: es comunicación dentro de la misma máquina, entre el "
            "programa y el navegador.")


def espacio_disponible(carpeta: str) -> Chequeo:
    try:
        libre = shutil.disk_usage(carpeta).free / 1e9
    except Exception as e:
        return Chequeo("espacio", "Espacio en disco", False,
                       f"No se pudo medir el espacio: {e}",
                       "Verificá que la ruta exista y sea accesible.")
    ok = libre >= ESPACIO_MINIMO_GB
    return Chequeo(
        "espacio", "Espacio en disco", ok,
        f"{libre:,.1f} GB libres (hacen falta {ESPACIO_MINIMO_GB:,.0f} GB)",
        "" if ok else
        "Liberá espacio o elegí otra unidad: tanto el instalador como la "
        "carpeta portable dejan elegir dónde guardar el programa y los datos.")


def sin_internet() -> Chequeo:
    """El programa NO necesita internet, y eso es una ventaja para vender.

    Se declara como chequeo —siempre en verde— porque es justo la pregunta que
    hace el área de seguridad del cliente antes de autorizar una instalación,
    y tenerla contestada por escrito en el diagnóstico ahorra la reunión.
    """
    return Chequeo(
        "internet", "Funciona sin internet", True,
        "El programa corre entero en esta máquina: no manda datos afuera ni "
        "necesita conexión para operar.",
        bloqueante=False)


def admin() -> Chequeo:
    """No es un requisito: decide qué modo conviene."""
    hay = _es_admin()
    return Chequeo(
        "admin", "Permisos de administrador", True,
        "Sí — podés usar el instalador o la carpeta portable, la que prefieras."
        if hay else
        "No — usá la CARPETA PORTABLE, que no instala nada ni toca el registro. "
        "El programa no necesita administrador para funcionar.",
        bloqueante=False)


def diagnosticar(carpeta_datos: str | None = None) -> dict:
    """Todos los chequeos, con el veredicto.

    `apto` mira solo los bloqueantes: que no seas administrador no impide usar
    el programa, y marcarlo en rojo haría que alguien abandone una instalación
    que iba a funcionar perfecto.
    """
    carpeta = carpeta_datos or os.path.expanduser("~/.kobra")
    chequeos = [puede_escribir(carpeta), puerto_disponible(),
                espacio_disponible(os.path.dirname(carpeta) or carpeta),
                admin(), sin_internet()]
    bloqueos = [c for c in chequeos if c.bloqueante and not c.ok]
    return {
        "apto": not bloqueos,
        "modo_sugerido": "instalador" if _es_admin() else "portable",
        "chequeos": [c.__dict__ for c in chequeos],
        "bloqueos": [c.__dict__ for c in bloqueos],
    }


def _ascii(texto: str) -> str:
    """Sin acentos, para la consola de Windows.

    El informe se imprime en una ventana de `cmd`, que en una máquina
    corporativa suele estar en cp850 o cp1252: un texto UTF-8 con acentos sale
    con símbolos raros, y eso es justo lo que el consultor va a copiar y pegar
    en un mail a IT. Un informe que se lee mal resta credibilidad al pedido.

    Solo afecta a esta salida: los `Chequeo` conservan los acentos para la API
    y la pantalla, que sí los muestran bien.
    """
    import unicodedata
    return (unicodedata.normalize("NFKD", texto)
            .encode("ascii", "ignore").decode("ascii"))


def informe_texto(carpeta_datos: str | None = None) -> str:
    """El diagnóstico como texto plano, para pegar en un mail a IT.

    Es la forma en que esto realmente se usa: el consultor corre el
    diagnóstico en la VM del cliente y manda el resultado al área de sistemas.
    Por eso sale en texto y no en JSON.
    """
    r = diagnosticar(carpeta_datos)
    lineas = ["MV Kobra AI - Diagnostico del entorno",
              "=" * 52, ""]
    for c in r["chequeos"]:
        lineas.append(f"[{'OK' if c['ok'] else 'FALLA'}] {_ascii(c['titulo'])}")
        lineas.append(f"       {_ascii(c['detalle'])}")
        if c["remedio"]:
            lineas += ["", "       QUE PEDIR A IT:",
                       f"       {_ascii(c['remedio'])}"]
        lineas.append("")
    lineas.append("=" * 52)
    if r["apto"]:
        lineas.append("RESULTADO: esta maquina puede correr MV Kobra AI.")
        lineas.append(f"Modo recomendado: {r['modo_sugerido'].upper()}")
    else:
        lineas.append(f"RESULTADO: faltan {len(r['bloqueos'])} permiso(s). "
                      "Ver 'QUE PEDIR A IT' arriba.")
    return "\n".join(lineas)


if __name__ == "__main__":
    print(informe_texto())
    raise SystemExit(0 if diagnosticar()["apto"] else 1)
