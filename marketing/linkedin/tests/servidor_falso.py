"""Un LinkedIn de mentira que corre en localhost.

Existe porque la alternativa para probar el cliente es publicar de verdad en el
perfil de alguien. Guarda cada request que recibe (ruta, cabeceras, cuerpo)
para que los tests puedan afirmar sobre lo que se MANDÓ, no sólo sobre lo que
se devolvió.
"""
from __future__ import annotations

import http.server
import json
import threading


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        largo = int(self.headers.get("Content-Length", 0))
        crudo = self.rfile.read(largo).decode("utf-8") if largo else ""
        self.server.recibidos.append({
            "ruta": self.path,
            "cabeceras": {k.lower(): v for k, v in self.headers.items()},
            "cuerpo": json.loads(crudo) if crudo else {},
        })

        codigo, cuerpo, extra = self.server.responder(self.path)
        self.send_response(codigo)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        datos = json.dumps(cuerpo).encode()
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *_a):
        pass


class LinkedInFalso:
    """Context manager: `with LinkedInFalso() as s: ... s.base, s.recibidos`."""

    def __init__(self, responder=None):
        self.responder = responder or self._por_defecto
        self.recibidos: list[dict] = []

    @staticmethod
    def _por_defecto(ruta: str):
        if ruta.endswith("/comments"):
            return 201, {"id": "urn:li:comment:(urn:li:activity:7,999)"}, {}
        # /rest/posts contesta 201 con cuerpo vacío y el URN en la cabecera.
        return 201, {}, {"x-restli-id": "urn:li:share:7123456789"}

    def __enter__(self):
        self._srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self._srv.recibidos = self.recibidos
        self._srv.responder = self.responder
        self.base = f"http://127.0.0.1:{self._srv.server_address[1]}"
        self._hilo = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *_a):
        self._srv.shutdown()
        self._srv.server_close()
        self._hilo.join(timeout=5)
