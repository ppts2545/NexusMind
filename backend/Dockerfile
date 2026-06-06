FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install build deps for some native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

# ── API server ────────────────────────────────────────────────────────────────
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ── Celery worker (crawl + embed) ─────────────────────────────────────────────
FROM base AS worker
CMD ["celery", "-A", "app.workers.celery_app.celery_app", "worker", \
     "--loglevel=info", "--concurrency=4", "-Q", "crawl,embed,dataset,celery"]

# ── Celery beat scheduler ─────────────────────────────────────────────────────
FROM base AS beat
CMD ["celery", "-A", "app.workers.celery_app.celery_app", "beat", "--loglevel=info"]
