# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- frontend build
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Omada Docs" \
      org.opencontainers.image.description="Read-only documentation platform for TP-Link Omada networks" \
      org.opencontainers.image.source="https://github.com/sebheider/omada_docs"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMADA_DOCS_DATA_DIR=/data \
    OMADA_DOCS_FRONTEND_DIR=/app/static \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    PUID=1000 \
    PGID=1000

# Pango/HarfBuzz for WeasyPrint (PDF), Cairo for diagram rasterisation (DOCX), fonts for both.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libcairo2 \
      fonts-dejavu-core fonts-liberation shared-mime-info tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
      > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=frontend /src/dist ./static
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh \
 && mkdir -p /data \
 && python -m compileall -q app

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:8080' + os.environ.get('OMADA_DOCS_BASE_PATH','').rstrip('/') + '/api/health', timeout=4)" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
