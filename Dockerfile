FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README_PRODUCTION.md ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir ".[dev]"

RUN addgroup --system app && adduser --system --ingroup app app && \
    mkdir -p /gee_out && chown -R app:app /app /gee_out

USER app

EXPOSE 8080
CMD ["uvicorn", "llm_geoprocessing.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
