#!/usr/bin/env bash
# © 2026 Martín Viera. Todos los derechos reservados.
# MV Kobra AI · runner end-to-end
# Uso:
#   ./run.sh            -> instala deps, genera datos, corre pipeline y levanta el dashboard
#   ./run.sh pipeline   -> solo genera datos + modelo + exports
#   ./run.sh train      -> reentrena y recalibra el modelo (~10 min)
#   ./run.sh app        -> solo levanta el dashboard Streamlit
#   ./run.sh ppt        -> genera la presentación gerencial (PPTX)
#
# El modelo entrenado viene commiteado en `outputs/`, así que un arranque
# limpio NO reentrena: usa ese. `./run.sh train` lo rehace a mano.
set -e
cd "$(dirname "$0")"

install()  { pip3 install -q -r requirements.txt; }
data()     { python3 data/generate_dataset.py --n 12000 --seed 42; \
             python3 data/generate_gestiones.py --seed 42; \
             python3 data/generate_audio_demo.py; }
pipeline() { python3 -m kobra.pipeline; }
train()    { python3 -m kobra.train; }

# `train` reentrena y recalibra eligiendo entre cinco modelos por validación
# cruzada. Son 10m21s medidos con 12.000 filas en 4 cores, y hasta acá los
# corría CUALQUIERA que escribiera `./run.sh` por primera vez, sin que nada se
# lo avisara: el primer contacto con el producto eran diez minutos de consola
# muda.
#
# No hacen falta: el modelo elegido y calibrado viene commiteado en `outputs/`.
# Pero saltearlo cuando NO está tampoco sirve — ahí el programa cae en el
# Gradient Boosting ad-hoc de `fit()` y 4.635 de 12.000 deudores (38,6%) cambian
# de decil, que es lo que decide a quién se llama primero.
#
# Así que se corre solo si falta. Forzarlo sigue siendo `./run.sh train`.
train_si_falta() {
  if [ -f outputs/probpago_model.joblib ] && [ -f outputs/model_selection.json ]; then
    echo "[run] Modelo entrenado presente — se usa el de outputs/ (./run.sh train lo rehace)."
  else
    echo "[run] Falta el modelo entrenado: entrenando. Esto tarda ~10 minutos."
    train
  fi
}
test_()    { python3 -m pytest -q tests/; }
app()      { streamlit run app/app.py; }
realtime() { python3 -m realtime.server; }
ppt()      { python3 presentation/build_ppt.py; }

case "${1:-all}" in
  install)  install ;;
  data)     data ;;
  pipeline) data; train_si_falta; pipeline ;;
  train)    data; train ;;   # explícito: reentrena aunque el modelo ya esté
  test)     test_ ;;
  app)      app ;;
  realtime) realtime ;;   # copiloto de audio en vivo (http://localhost:8000)
  ppt)      ppt ;;
  all)      install; data; train_si_falta; pipeline; echo "Levantando dashboard…"; app ;;
  *) echo "Opción inválida: $1"; exit 1 ;;
esac
