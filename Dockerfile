FROM python:3.11-slim AS builder

WORKDIR /build

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nginx \
    supervisor \
    tesseract-ocr \
    tesseract-ocr-deu \
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

RUN mkdir -p /app/data /app/frontend /var/log/supervisor /var/log/nginx /var/lib/nginx/body /var/lib/nginx/cache /var/run

RUN touch /var/run/supervisord.pid

WORKDIR /app/backend

ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
