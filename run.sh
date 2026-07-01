#!/usr/bin/env bash
# Kobra · runner end-to-end
# Uso:
#   ./run.sh            -> instala deps, genera datos, corre pipeline y levanta el dashboard
#   ./run.sh pipeline   -> solo genera datos + modelo + exports
#   ./run.sh app        -> solo levanta el dashboard Streamlit
#   ./run.sh ppt        -> genera la presentación gerencial (PPTX)
set -e
cd "$(dirname "$0")"

install() { pip3 install -q -r requirements.txt; }
data()    { python3 data/generate_dataset.py --n 12000 --seed 42; }
pipeline(){ python3 -m kobra.pipeline; }
train()   { python3 -m kobra.train; }
test_()   { python3 -m pytest -q tests/; }
app()     { streamlit run app/app.py; }
ppt()     { python3 presentation/build_ppt.py; }

case "${1:-all}" in
  install)  install ;;
  data)     data ;;
  pipeline) data; pipeline ;;
  train)    data; train ;;
  test)     test_ ;;
  app)      app ;;
  ppt)      ppt ;;
  all)      install; data; pipeline; echo "Levantando dashboard…"; app ;;
  *) echo "Opción inválida: $1"; exit 1 ;;
esac
