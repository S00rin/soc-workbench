FROM python:3.12-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --prefix=/python-runtime -r requirements.txt
COPY app ./app
RUN python -m compileall --invalidation-mode=checked-hash -q -b app \
    && find app -type f -name '*.py' -delete \
    && find app -type d -name '__pycache__' -prune -exec rm -rf '{}' +

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/opt/soc/data ENVIRONMENT=production DEBUG=false
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-fas \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 soc \
    && useradd --system --uid 10001 --gid soc --home-dir /opt/soc --shell /usr/sbin/nologin soc \
    && mkdir -p /opt/soc/backend /opt/soc/data \
    && chown -R soc:soc /opt/soc
COPY --from=build /python-runtime/ /usr/local/
COPY --from=build --chown=soc:soc /build/app/ /opt/soc/backend/app/
WORKDIR /opt/soc/backend
USER 10001:10001
EXPOSE 8000
VOLUME ["/opt/soc/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
