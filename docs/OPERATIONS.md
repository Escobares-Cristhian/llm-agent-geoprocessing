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
