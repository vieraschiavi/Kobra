"""
MV Kobra AI · Capacidad de llamadas simultáneas (chatvoice / chatbot)
====================================================================
Cuántas conversaciones puede sostener el producto **al mismo tiempo**, y qué
hace cuando se pasa de ese número.

Antes no había respuesta a ninguna de las dos preguntas: los diccionarios de
sesiones de `realtime/server.py` crecían sin tope y sin vencimiento, así que
"la capacidad" era, en los hechos, la memoria del servidor. Medido: 500
llamadas abandonadas tras el saludo dejaban 500 sesiones vivas para siempre —
en telefonía el abandono es la norma, no la excepción (el deudor corta apenas
escucha "cobranzas").

Este módulo pone las dos piezas que faltaban:

  1. **Un tope explícito** (`KOBRA_MAX_LLAMADAS`, default 50 — un gestor IA por
     cada uno de los 50 gestores del plan). Pasado el tope se rechaza con un
     mensaje claro ("todas las líneas ocupadas"), que es lo que hace una central
     telefónica: mejor una llamada rechazada y reintentada que cincuenta
     llamadas degradadas.

  2. **Vencimiento por inactividad** (`KOBRA_TTL_SESION_SEG`, default 900 s).
     Una llamada que no manda un turno en 15 minutos ya se cortó del otro lado:
     la sesión se libera y el cupo vuelve al pool.

El registro es seguro entre threads porque los handlers de voz y WhatsApp
corren en el threadpool de Starlette (ver `realtime/server.py`), no en el event
loop.
"""
from __future__ import annotations

import os
import threading
import time

# Tope de conversaciones simultáneas por proceso. 50 = el plan comercial
# ("máximo 50 gestores"). Con varios workers de uvicorn el tope es por worker:
# `capacidad_total()` lo deja explícito para no vender 4× de más.
MAX_SIMULTANEAS = max(int(os.getenv("KOBRA_MAX_LLAMADAS", "50")), 1)

# Inactividad tras la cual se da la conversación por terminada.
TTL_SESION_SEG = max(int(os.getenv("KOBRA_TTL_SESION_SEG", "900")), 30)


class LimiteAlcanzado(Exception):
    """No hay cupo libre: todas las líneas están ocupadas."""


class RegistroSesiones:
    """Sesiones vivas de un canal (voz o WhatsApp), con tope y vencimiento."""

    def __init__(self, nombre: str, maximo: int | None = None,
                 ttl_seg: int | None = None, reloj=time.monotonic):
        self.nombre = nombre
        self.maximo = MAX_SIMULTANEAS if maximo is None else max(int(maximo), 1)
        self.ttl_seg = TTL_SESION_SEG if ttl_seg is None else max(int(ttl_seg), 1)
        self._reloj = reloj
        self._lock = threading.Lock()
        self._sesiones: dict = {}          # clave -> [sesion, ultimo_uso]
        self.rechazadas = 0                # cuántas se rechazaron por tope
        self.vencidas = 0                  # cuántas se liberaron por inactividad
        self.pico = 0

    # --- interno (siempre con el lock tomado) --------------------------------
    def _purgar(self) -> int:
        corte = self._reloj() - self.ttl_seg
        muertas = [k for k, (_, visto) in self._sesiones.items() if visto < corte]
        for k in muertas:
            del self._sesiones[k]
        self.vencidas += len(muertas)
        return len(muertas)

    # --- API ------------------------------------------------------------------
    def purgar(self) -> int:
        """Libera las sesiones inactivas. Devuelve cuántas cerró."""
        with self._lock:
            return self._purgar()

    def abrir(self, clave: str, fabrica):
        """Abre (o reabre) una conversación. `fabrica` se llama solo si hay cupo.

        Se construye DENTRO del lock a propósito: crear la sesión es barato
        (leer el brief de la cartera en memoria) y hacerlo afuera abriría una
        ventana donde N llamadas simultáneas pasan todas el chequeo de cupo.
        """
        with self._lock:
            self._purgar()
            if clave not in self._sesiones and len(self._sesiones) >= self.maximo:
                self.rechazadas += 1
                raise LimiteAlcanzado(
                    f"{self.nombre}: {len(self._sesiones)}/{self.maximo} "
                    f"conversaciones simultáneas en curso")
            sesion = fabrica()
            self._sesiones[clave] = [sesion, self._reloj()]
            self.pico = max(self.pico, len(self._sesiones))
            return sesion

    def obtener(self, clave: str):
        """Sesión en curso, refrescando su marca de actividad. None si no existe
        o si ya venció."""
        with self._lock:
            self._purgar()
            par = self._sesiones.get(clave)
            if par is None:
                return None
            par[1] = self._reloj()
            return par[0]

    def cerrar(self, clave: str):
        with self._lock:
            par = self._sesiones.pop(clave, None)
            return par[0] if par else None

    def vivas(self) -> int:
        with self._lock:
            self._purgar()
            return len(self._sesiones)

    # El registro reemplazó a un `dict` pelado: se mantienen `in` y `len()` para
    # que el código que ya los usaba (tests incluidos) siga leyéndose igual.
    def __contains__(self, clave) -> bool:
        with self._lock:
            self._purgar()
            return clave in self._sesiones

    def __len__(self) -> int:
        return self.vivas()

    def metricas(self) -> dict:
        with self._lock:
            self._purgar()
            vivas = len(self._sesiones)
            return {"canal": self.nombre, "en_curso": vivas, "maximo": self.maximo,
                    "libres": max(self.maximo - vivas, 0), "pico": self.pico,
                    "rechazadas": self.rechazadas, "vencidas_por_inactividad": self.vencidas,
                    "ttl_seg": self.ttl_seg}


def capacidad_total(workers: int = 1) -> dict:
    """Capacidad anunciable del despliegue. El tope es POR PROCESO: con N
    workers de uvicorn la capacidad se multiplica, pero también la RAM."""
    return {"por_worker": MAX_SIMULTANEAS, "workers": max(int(workers), 1),
            "simultaneas": MAX_SIMULTANEAS * max(int(workers), 1),
            "ttl_sesion_seg": TTL_SESION_SEG}
