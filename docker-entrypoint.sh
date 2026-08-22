#!/usr/bin/env bash
# © 2026 Martín Viera. Todos los derechos reservados.
# MV Kobra AI · entrypoint: genera datos/modelo si faltan y arranca el servicio pedido.
set -e

[ -f data/kobra_cartera.csv ]   || python data/generate_dataset.py --n 12000 --seed 42
[ -f data/kobra_gestiones.csv ] || python data/generate_gestiones.py --seed 42
[ -f data/ejemplo_llamada.wav ] || python data/generate_audio_demo.py
[ -f outputs/kobra_bundle.json ] || python -m kobra.pipeline

case "${1:-dashboard}" in
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
