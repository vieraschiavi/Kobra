#!/usr/bin/env bash
# Kobra · entrypoint: genera datos/modelo si faltan y arranca el servicio pedido.
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
    exec python -m realtime.server
    ;;
  *)
    exec "$@"
    ;;
esac
