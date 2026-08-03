# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build/backend
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --prefix=/python-runtime -r requirements.txt
COPY backend/app ./app
# Legacy .pyc files can be imported without their source. The final image is
# assembled in a fresh stage, so no proprietary .py or build layer is copied.
RUN python -m compileall --invalidation-mode=checked-hash -q -b app \
    && find app -type f -name '*.py' -delete \
    && find app -type d -name '__pycache__' -prune -exec rm -rf '{}' +

FROM python:3.12-slim AS runtime
ARG APP_VERSION=0.4.0
LABEL org.opencontainers.image.title="Soorin SOC Workbench" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.vendor="Soorin"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/soc/backend \
    DATA_DIR=/opt/soc/data \
    ENVIRONMENT=production \
    DEBUG=false \
    PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-fas \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 soc \
    && useradd --system --uid 10001 --gid soc --home-dir /opt/soc --shell /usr/sbin/nologin soc \
    && mkdir -p /opt/soc/backend /opt/soc/frontend/dist /opt/soc/data \
    && chown -R soc:soc /opt/soc
COPY --from=backend-build /python-runtime/ /usr/local/
COPY --from=backend-build --chown=soc:soc /build/backend/app/ /opt/soc/backend/app/
COPY --from=frontend-build --chown=soc:soc /build/frontend/dist/ /opt/soc/frontend/dist/
WORKDIR /opt/soc/backend
USER 10001:10001
EXPOSE 8000
VOLUME ["/opt/soc/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
