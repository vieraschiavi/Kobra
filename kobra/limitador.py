"""
MV Kobra AI · Límite de intentos en la puerta de entrada
========================================================
La superficie pública del backend es chica —login, activación de licencia,
primer arranque— pero es exactamente donde se prueba a fuerza bruta:

  - `POST /api/auth/login` acepta la contraseña del administrador. Sin freno,
    un script prueba miles por minuto contra un hash PBKDF2 que el servidor
    calcula gratis para el atacante.
  - `POST /api/licencia/activar` acepta un token de licencia. Sin freno, se
    puede tantear hasta encontrar uno vigente.
  - `POST /api/auth/setup` crea la contraseña en el primer arranque.

Este módulo pone un **cubo de fichas (token bucket) por IP y por acción**: cada
IP arranca con `permitidos` intentos y recupera uno cada
`ventana_seg / permitidos` segundos. Un humano que se equivoca de contraseña
nunca lo nota; un script que prueba en ráfaga se queda sin fichas enseguida.

Por qué acá y no un paquete: `slowapi` traería `limits` y su cadena de
dependencias para ~70 líneas de lógica, y el producto se instala en la PC de un
cliente donde cada dependencia es una cosa más que puede fallar al instalar.

Por qué en memoria: el backend corre como un proceso por instalación. Con
varios workers el límite es por worker — `intentos_por_worker()` lo deja
explícito para no prometer un techo que no es.
"""
from __future__ import annotations

import os
import threading
import time

# Defaults para la puerta de un producto instalado, no para una API pública
# masiva: 10 intentos y después uno cada 30 s.
INTENTOS = max(int(os.getenv("KOBRA_LOGIN_INTENTOS", "10")), 1)
VENTANA_SEG = max(int(os.getenv("KOBRA_LOGIN_VENTANA_SEG", "300")), 1)


class LimiteIntentos(Exception):
    """Se acabaron las fichas. `espera_seg` dice cuánto falta para la próxima."""

    def __init__(self, espera_seg: int):
        self.espera_seg = espera_seg
        super().__init__(f"demasiados intentos; reintentar en {espera_seg} s")


class Limitador:
    """Token bucket por clave (IP + acción).

    Seguro entre threads a propósito: los handlers de FastAPI que no son
    `async` corren en el threadpool, así que dos intentos simultáneos tocan
    este diccionario desde hilos distintos. Sin el lock, dos peticiones podrían
    leer las mismas fichas y consumir una sola.
    """

    def __init__(self, permitidos: int | None = None, ventana_seg: int | None = None,
                 reloj=time.monotonic):
        self.permitidos = INTENTOS if permitidos is None else max(int(permitidos), 1)
        self.ventana_seg = VENTANA_SEG if ventana_seg is None else max(int(ventana_seg), 1)
        self._reloj = reloj
        self._lock = threading.Lock()
        self._cubos: dict[str, list] = {}      # clave -> [fichas, ultimo_toque]
        self.rechazados = 0

    @property
    def recarga_seg(self) -> float:
        """Segundos que tarda en volver UNA ficha."""
        return self.ventana_seg / float(self.permitidos)

    def _purgar(self, ahora: float) -> None:
        """Saca los cubos ya recargados: sin esto, cada IP que pasó una vez
        queda en memoria para siempre y el diccionario crece sin techo — un
        atacante rotando IPs lo convertiría en una fuga de memoria."""
        viejos = [k for k, (_, visto) in self._cubos.items()
                  if ahora - visto > self.ventana_seg * 2]
        for k in viejos:
            del self._cubos[k]

    def intentar(self, clave: str) -> None:
        """Consume una ficha. Levanta `LimiteIntentos` si no quedan."""
        with self._lock:
            ahora = self._reloj()
            if len(self._cubos) > 4096:
                self._purgar(ahora)
            fichas, visto = self._cubos.get(clave, [float(self.permitidos), ahora])
            fichas = min(self.permitidos, fichas + (ahora - visto) / self.recarga_seg)
            if fichas < 1.0:
                self.rechazados += 1
                self._cubos[clave] = [fichas, ahora]
                raise LimiteIntentos(int((1.0 - fichas) * self.recarga_seg) + 1)
            self._cubos[clave] = [fichas - 1.0, ahora]

    def perdonar(self, clave: str) -> None:
        """Devuelve la ficha. Se llama cuando el intento resultó CORRECTO: el
        límite tiene que castigar el tanteo, no cobrarle al usuario que se
        equivocó una vez y después entró bien."""
        with self._lock:
            par = self._cubos.get(clave)
            if par:
                par[0] = min(self.permitidos, par[0] + 1.0)

    def metricas(self) -> dict:
        with self._lock:
            return {"permitidos": self.permitidos, "ventana_seg": self.ventana_seg,
                    "claves_vivas": len(self._cubos), "rechazados": self.rechazados}


def ip_de(request) -> str:
    """IP del cliente, mirando el proxy si lo hay.

    Detrás de Vercel o nginx, `request.client.host` es la IP del proxy: todas
    las peticiones del mundo compartirían un solo cubo y el primer atacante
    dejaría afuera a todos los usuarios legítimos. `x-forwarded-for` trae la
    cadena y la primera entrada es el cliente real.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    cliente = getattr(request, "client", None)
    return getattr(cliente, "host", None) or "desconocido"


def intentos_por_worker(workers: int = 1) -> dict:
    """El límite es POR PROCESO: con N workers el techo real se multiplica."""
    return {"por_worker": INTENTOS, "workers": max(int(workers), 1),
            "total": INTENTOS * max(int(workers), 1), "ventana_seg": VENTANA_SEG}
