# Operations

## Start production-like stack

```bash
cp .env.example .env
docker compose up --build
```

## Start development stack

```bash
docker compose -f docker-compose.dev.yml up --build
```

## Run tests

```bash
docker compose run --rm geollm-api pytest
```

## Run lint/type checks

```bash
docker compose run --rm geollm-api ruff check .
docker compose run --rm geollm-api mypy src
```

## Enable LangSmith

Set:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=llm-geoprocessing-prod
```

## Enable real GEE migration path

Set:

```bash
GEE_REAL_EXECUTION=true
```

Then implement `llm_geoprocessing.plugins.gee.api._execute_real_gee` by adapting the existing Earth Engine service functions behind the new `GeeToolRequest` / `GeeToolResponse` contract.

## Health endpoints

- Agent API: `GET /healthz`, `GET /readyz`
- GEE plugin API: `GET /healthz`, `GET /readyz`, `GET /capabilities`, `GET /tools`

## Streamlit UI

The production overlay includes an optional Dockerized Streamlit client. It does not replace the
FastAPI runtime; it calls the existing `/runs` and `/runs/{run_id}/resume` endpoints.

Start the UI profile:

```bash
docker compose --profile ui up -d --build
```

Open:

```text
http://localhost:8501
```

The Streamlit service uses the internal Docker URL:

```dotenv
GEOLLM_API_URL=http://geollm-api:8080
```

It mounts the same `gee_out` volume read-only at `/gee_out`, so real GeoTIFF artifacts returned by
the GEE plugin can be read and rendered on the map. In mock mode, artifacts are placeholder files and
will not render as rasters.

The UI includes:

- session-local chat history;
- resume support for clarification runs;
- a map viewer for GeoTIFF artifacts;
- a sidebar toggle that shows generated JSON instructions from `result.plan` for the current session.
