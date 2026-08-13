# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Elección de puerto sin pisar a otros programas
============================================================
Tanto el lanzador de escritorio (`packaging/kobra_launcher.py`, FastAPI) como
el de la edición Producción (`packaging/kobra_streamlit.py`, Streamlit) tienen
que abrir un puerto local. Si el puerto elegido ya lo está usando otra
aplicación, hay dos finales malos: el programa no arranca, o —peor— arranca
igual y las dos se pelean las conexiones entrantes.

La lógica vive acá y no en cada lanzador porque el detalle que la hace
correcta es contraintuitivo y se arregla una sola vez (ver `esta_libre`).
"""
from __future__ import annotations

import socket

# Puertos propios de MV Kobra AI. No son los "de siempre" (8000/8501/8080) a
# propósito: esos son justamente los que ya suele tener ocupados otra cosa.
PUERTOS_APP = (8531, 8542, 8553, 8564, 8575)
PUERTOS_STREAMLIT = (8531, 8542, 8553, 8564, 8575)


def esta_libre(puerto: int, host: str = "127.0.0.1") -> bool:
    """¿Se puede servir en `puerto` sin pisar a nadie?

    **Sin SO_REUSEADDR a propósito.** En Windows esa opción NO significa lo
    mismo que en Unix: habilita hacer `bind()` sobre un puerto que otro proceso
    ya tiene en LISTEN — el comportamiento que en Unix hay que pedir aparte con
    SO_REUSEPORT. Con la opción puesta, el sondeo devolvía «libre» para un
    puerto ocupado y MV Kobra AI arrancaba encima de la otra aplicación, que es
    exactamente lo que hay que evitar. Sin ella el `bind()` falla como
    corresponde y se pasa al siguiente candidato.

    En Windows se pide además SO_EXCLUSIVEADDRUSE: es la forma explícita de
    decir «este puerto es mío o no lo quiero», y cierra el mismo agujero desde
    el otro lado (que alguien se cuelgue del nuestro después).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        exclusivo = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusivo is not None:
            try:
                s.setsockopt(socket.SOL_SOCKET, exclusivo, 1)
            except OSError:
                pass
        s.bind((host, puerto))
        # `listen()` y no solo `bind()`: en algunas configuraciones el bind pasa
        # y el conflicto recién aparece al escuchar. Si vamos a servir ahí,
        # probamos exactamente lo que vamos a hacer.
        s.listen(1)
        return True
    except OSError:
        return False
    finally:
        s.close()


def puerto_libre(candidatos=PUERTOS_APP, host: str = "127.0.0.1") -> int:
    """Primer `candidato` libre; si están todos ocupados, uno efímero del SO.

    El fallback efímero importa: con los cinco candidatos tomados, devolver uno
    igual sería volver a pisar a alguien. Que el SO elija garantiza que salga
    libre, aunque la URL quede menos "linda".
    """
    for p in candidatos:
        if esta_libre(p, host):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]
