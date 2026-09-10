#!/usr/bin/env bash
# © 2026 Martín Viera. Todos los derechos reservados.
# MV Kobra AI · entrypoint: genera datos/modelo si faltan y arranca el servicio pedido.
set -e

[ -f data/kobra_cartera.csv ]   || python data/generate_dataset.py --n 12000 --seed 42
[ -f data/kobra_gestiones.csv ] || python data/generate_gestiones.py --seed 42
[ -f data/ejemplo_llamada.wav ] || python data/generate_audio_demo.py
[ -f outputs/kobra_bundle.json ] || python -m kobra.pipeline

case "${1:-dashboard}" in
  app)
    # La app completa (React + FastAPI) para el servidor o la VM del cliente.
    #
    # Entra sin pedir licencia porque el sello Owner viaja por el entorno
    # (`kobra/edicion.py::es_owner` lo verifica contra la pública embebida).
    # El sello es una CREDENCIAL: llega por variable de entorno o por secreto
    # del orquestador, nunca horneado en la imagen — una imagen con el sello
    # adentro convierte a cualquiera que la baje en el dueño.
    if [ -z "${KOBRA_OWNER_TOKEN:-}" ] && [ -n "${KOBRA_OWNER_TOKEN_FILE:-}" ]; then
      # Secreto montado como archivo (docker secrets / Kubernetes): la vía que
      # no deja la credencial en `docker inspect` ni en el historial del shell.
      KOBRA_OWNER_TOKEN="$(cat "${KOBRA_OWNER_TOKEN_FILE}")"
      export KOBRA_OWNER_TOKEN
    fi
    if [ -z "${KOBRA_OWNER_TOKEN:-}" ]; then
      echo "ERROR: falta KOBRA_OWNER_TOKEN (o KOBRA_OWNER_TOKEN_FILE)." >&2
      echo "Sin el sello firmado, la app arrancaria pidiendo licencia — que es" >&2
      echo "exactamente lo que este modo viene a evitar. Emitilo una vez con" >&2
      echo "packaging/generar_sello_owner.bat y pasalo como variable." >&2
      exit 1
    fi
    # Sin contraseña: el gateo es el sello, no un login.
    #
    # Adentro del contenedor 0.0.0.0 es lo correcto y no una imprudencia —el
    # contenedor tiene su propio namespace de red, y un proceso atado a SU
    # loopback no responde por el puerto publicado; es el mismo razonamiento
    # que está escrito más abajo para el servicio en vivo. Quien decide la
    # exposición real es el que publica el puerto: el compose lo hace en
    # 127.0.0.1.
    #
    # El agujero es `docker run -p 8080:8080`, que publica en 0.0.0.0 del host.
    # Ahí cualquiera que llegue al puerto se pide un token de admin en
    # /api/licencia/owner-login SIN credencial, porque el proceso ya está en
    # modo owner. Por eso el arranque lo dice en voz alta en vez de dejarlo
    # solo escrito en la doc, y por eso el bind se puede fijar a mano.
    export KOBRA_MODO_STANDALONE=1
    KOBRA_APP_HOST="${KOBRA_APP_HOST:-0.0.0.0}"
    echo "MV Kobra AI - modo servidor. Entra SIN contrasena (el sello es la" >&2
    echo "puerta). Publica este puerto en 127.0.0.1 o detras de un proxy con" >&2
    echo "autenticacion: quien llegue al puerto entra como duenio." >&2
    exec python -m uvicorn webapp.backend.api:app \
      --host "${KOBRA_APP_HOST}" --port "${PORT:-8080}" --log-level warning
    ;;
  dashboard)
    exec streamlit run app/app.py \
      --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true
    ;;
  realtime)
    # Adentro de un contenedor, 0.0.0.0 es lo correcto y no una imprudencia.
    #
    # `realtime/server.py` ata 127.0.0.1 por defecto a propósito: quien abre el
    # programa en su notebook no tiene que exponer a la red de la oficina un
    # servicio que dispara llamadas telefónicas. Pero el contenedor tiene su
    # propio namespace de red: un proceso atado a SU loopback no responde por
    # el puerto que publica `ports: 8000:8000`, porque el reenvío de Docker
    # apunta a la interfaz del contenedor, no a su loopback. O sea que
    # `docker compose up` levantaba un servicio de realtime al que no se podía
    # llegar desde ningún lado.
    #
    # Publicar el puerto ya ES la decisión explícita de exponerlo, y el
    # servicio pide token desde `realtime/acceso.py` (mirá el token en
    # `docker compose logs realtime`).
    export KOBRA_REALTIME_HOST="${KOBRA_REALTIME_HOST:-0.0.0.0}"
    exec python -m realtime.server
    ;;
  *)
    exec "$@"
    ;;
esac
