# LLM Geoprocessing — Production-Ready Refactor Overlay

This overlay converts the PoC into a Docker-only, API-first, typed, observable geospatial agent service.
It is intended to be copied over the repository root of `Escobares-Cristhian/llm-geoprocessing`.

## What this adds

- FastAPI API service for thread/run execution.
- LangGraph orchestration with clarification checkpoints.
- Typed Pydantic contracts for plans, products, actions, artifacts, errors, and tool calls.
- GEE plugin boundary with allowlisted tools and standardized request/response schemas.
- MCP-compatible tool server for GEE tool exposure.
- Docker-only development and production execution.
- LangSmith tracing hooks and structured JSON logging.
- Unit, contract, graph, and API tests.
- Security, operations, migration, and architecture documentation.

## Apply overlay

From a clean checkout of the original repository:

```bash
cp -R /path/to/llm-geoprocessing-production-ready/* .
cp .env.example .env
```

Then run everything inside Docker:

```bash
docker compose up --build
```

Run checks:

```bash
docker compose run --rm geollm-api pytest
docker compose run --rm geollm-api ruff check .
docker compose run --rm geollm-api mypy src
```

## API quickstart

```bash
curl -s http://localhost:8080/healthz

curl -s -X POST http://localhost:8080/runs \
  -H 'Content-Type: application/json' \
  -d '{"message":"Calculate NDVI for Sentinel-2 over bbox [-58.4,-34.6,-58.3,-34.5] from 2024-01-01 to 2024-01-31", "thread_id":"demo"}' | jq .
```

The default stack uses `GEO_LLM_PROVIDER=mock` and `GEE_REAL_EXECUTION=false`, so it runs without API keys or Earth Engine credentials.


## Built-in chat UI

After starting Docker Compose, open http://localhost:8080/chat. The UI is served by the API container and calls `/runs` and `/runs/{run_id}/resume`; no host-side Node, Streamlit, or Python install is required.
