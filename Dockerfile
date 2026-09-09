# MV Kobra AI · imagen única para la app, el dashboard y el servicio realtime
#
# La app completa (React + FastAPI) es la misma que corre en el .exe y en la
# nube. Acá sirve para el caso que ningún instalador cubre: una laptop
# corporativa donde NO se puede instalar nada —ni .exe ni .bat— trabajando
# sobre datos de un cliente que no pueden salir de su infraestructura.
# El programa corre en el servidor del cliente y se usa por el navegador; los
# datos nunca tocan la máquina de quien lo usa. Ver docs/MODOS_INSTALACION.md.

# --- 1) La interfaz, compilada acá y no traída hecha -------------------------
# Si el dist viajara commiteado, la imagen mostraría la interfaz del día que
# alguien se acordó de recompilarla. Node vive solo en esta etapa: no queda en
# la imagen final.
FROM node:20-slim AS ui
WORKDIR /ui
COPY webapp/frontend/package.json webapp/frontend/package-lock.json ./
RUN npm ci
COPY webapp/frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KOBRA_CONFIG_DIR=/config

WORKDIR /app

# libsndfile para soundfile (análisis de voz)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# La interfaz compilada en la etapa anterior. Va donde la app la busca sola
# (webapp/backend/api.py), así el contenedor no necesita KOBRA_UI_DIST.
COPY --from=ui /ui/dist ./webapp/frontend/dist
RUN chmod +x docker-entrypoint.sh && mkdir -p /config

EXPOSE 8080 8501 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["dashboard"]
