# MV Kobra AI · imagen única para dashboard y servicio realtime
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
RUN chmod +x docker-entrypoint.sh && mkdir -p /config

EXPOSE 8501 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["dashboard"]
