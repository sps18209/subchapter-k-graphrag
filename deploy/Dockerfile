# syntax=docker/dockerfile:1
#
# Subchapter K GraphRAG API image.
#
# THE BUILD CONTEXT IS THE BUNDLE ROOT (the parent of deploy/), because the image
# needs both the engine (python/) and the service (deploy/). Build it with:
#     docker build -f deploy/Dockerfile -t subk-graphrag-api .
# run from the bundle root, or just use docker-compose.yml which sets the context.

# ---- build stage: resolve dependencies into a clean prefix --------------------
FROM python:3.12-slim AS builder
WORKDIR /install
COPY deploy/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install/prefix -r requirements.txt

# ---- runtime stage: minimal, non-root ----------------------------------------
FROM python:3.12-slim

# Unprivileged user. Never run a production container as root.
RUN groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app

WORKDIR /app
# Installed dependencies only (no build tools, no pip cache, no source from builder).
COPY --from=builder /install/prefix /usr/local
# The engine (pure stdlib) and the service share one import root.
COPY python/ /app/python/
COPY deploy/ /app/deploy/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/deploy:/app/python \
    SUBK_DB=/tmp/subk_api.db

USER app
WORKDIR /app/deploy
EXPOSE 8000

# /health is unauthenticated and cheap; orchestrators use it for liveness.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# python -m keeps the working dir importable for `app:app`.
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
