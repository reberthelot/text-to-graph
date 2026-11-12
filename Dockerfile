# syntax=docker/dockerfile:1
#
# Multi-stage Dockerfile (GUIDE section 10):
#
#   base        shared Python runtime + non-root user
#   frontend    the evaluation UI (:8080)
#   text2graph  the text-to-graph web service (:8000)  <- LAST stage = default
#
# `docker build .` (no --target) builds the service, as the assignment
# expects. compose.yaml builds both.

FROM python:3.11-alpine AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# WORKDIR before any COPY: otherwise files land at the image root.
WORKDIR /app

# Never run as root.
# BusyBox syntax (Alpine): -S system account, -D no password, home kept.
RUN addgroup -S appuser && adduser -S -D -G appuser -s /sbin/nologin appuser


# ---------------------------------------------------------------------------
# Frontend -- evaluation UI and RDF scoring. Holds no secret.
# ---------------------------------------------------------------------------
FROM base AS frontend

COPY requirements-frontend.txt .
RUN pip install --no-cache-dir -r requirements-frontend.txt

COPY src/__init__.py /app/src/
COPY src/app/ /app/src/app/
COPY frontend/ /app/frontend/
COPY data/keyboards.txt /app/data/

USER appuser
EXPOSE 8080

# Liveness: mirrors GET /api/health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8080"]


# ---------------------------------------------------------------------------
# text2graph service -- owns the LLM credentials and the linking catalogue.
# ---------------------------------------------------------------------------
FROM base AS text2graph

# Dependencies first: this layer stays cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/__init__.py /app/src/
COPY src/text2graph/ /app/src/text2graph/
COPY data/catalogue.json /app/data/
COPY main.py /app/

USER appuser
EXPOSE 8000

# Liveness: mirrors GET /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# Stateless apart from pooled clients and the read-only catalogue: more
# workers would be safe, but one keeps the logs readable. Scale with replicas.
CMD ["uvicorn", "src.text2graph.server:app", "--host", "0.0.0.0", "--port", "8000"]
