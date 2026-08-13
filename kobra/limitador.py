# © 2026 Martín Viera. Todos los derechos reservados.
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


# Defaults para el freno GENERAL (no el de la puerta de entrada de arriba):
# cualquier request, no solo login/licencia. 120 cada 60 s por IP y por ruta
# es holgado para un usuario real —incluido el polling del dashboard— y corto
# para un script.
PETICIONES = max(int(os.getenv("KOBRA_RATE_PETICIONES", "120")), 1)
PETICIONES_VENTANA_SEG = max(int(os.getenv("KOBRA_RATE_VENTANA_SEG", "60")), 1)


class LimitadorGeneral:
    """Middleware ASGI puro — cubre HTTP y WebSocket por igual.

    `@app.middleware("http")` de Starlette/FastAPI NO envuelve el handshake de
    WebSocket: un decorador puesto así dejaría `/ws`, `/ws_audio` y `/twilio`
    —los endpoints de voz en vivo, exactamente donde más importa— completamente
    afuera del freno. Por eso esto es un middleware ASGI real, agregado con
    `app.add_middleware(LimitadorGeneral)`, no un decorador de ruta HTTP.

    Es la RED DE SEGURIDAD general: cubre todo endpoint público sin necesidad
    de acordarse de agregarlo ruta por ruta. Los límites más estrictos que ya
    existen (`_frenar()` en login/licencia/setup, o el de `/voz/llamar`) se
    mantienen aparte — éste es más laxo a propósito, para no molestar a un uso
    normal, y actúa como piso para todo lo que a alguien se le olvide frenar
    a mano.
    """

    def __init__(self, app, permitidos: int | None = None,
                 ventana_seg: int | None = None, exentas: tuple = ()):
        self.app = app
        self.limitador = Limitador(
            PETICIONES if permitidos is None else permitidos,
            PETICIONES_VENTANA_SEG if ventana_seg is None else ventana_seg)
        # Salud/capacidad: los pega un monitor de uptime cada pocos segundos
        # desde SIEMPRE la misma IP (el propio orquestador). Frenarlos apaga
        # las alertas justo cuando algo anda mal.
        self.exentas = set(exentas) | {"/health", "/api/health", "/salud", "/capacidad"}

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self.exentas:
            await self.app(scope, receive, send)
            return

        from starlette.requests import HTTPConnection
        conexion = HTTPConnection(scope)
        clave = f"general:{ip_de(conexion)}:{path}"
        try:
            self.limitador.intentar(clave)
        except LimiteIntentos as e:
            if scope["type"] == "websocket":
                # 1013 = "Try Again Later" (RFC 6455 / IANA): lo más parecido
                # a un 429 que tiene el protocolo de WebSocket.
                await send({"type": "websocket.close", "code": 1013,
                            "reason": f"demasiadas conexiones, reintentar en {e.espera_seg}s"})
            else:
                from starlette.responses import JSONResponse
                respuesta = JSONResponse(
                    {"detail": f"Demasiadas peticiones. Esperá {e.espera_seg} segundos y probá de nuevo."},
                    status_code=429, headers={"Retry-After": str(e.espera_seg)})
                await respuesta(scope, receive, send)
            return
        await self.app(scope, receive, send)
