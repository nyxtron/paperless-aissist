FROM python:3.11-slim AS builder

WORKDIR /build

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

ARG APP_VERSION=dev

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION=${APP_VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    nginx \
    supervisor \
    libpoppler-cpp-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && pip cache purge

COPY --from=builder /install /usr/local
COPY --from=builder /build /build

COPY backend /app/backend
COPY examples /app/examples
COPY frontend/dist /app/frontend
COPY nginx.conf /app/nginx.conf
COPY supervisord.conf /app/supervisord.conf
COPY docker/entrypoint.sh /app/entrypoint.sh

RUN mkdir -p /app/data /app/frontend /var/log/supervisor /var/log/nginx /var/lib/nginx/body /var/lib/nginx/cache /var/run \
    && chmod +x /app/entrypoint.sh

WORKDIR /app/backend

ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1
ENV PUID=1000
ENV PGID=1000

EXPOSE 8080

# Probes the backend through nginx, so an unreachable uvicorn marks the
# container unhealthy instead of going unnoticed.
HEALTHCHECK --interval=60s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
