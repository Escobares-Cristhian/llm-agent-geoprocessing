# Implementation Audit

## Current baseline observed

The upstream repository describes a modular LLM geoprocessing framework with a FastAPI GEE microservice, GeoTIFF tile exports, optional PostGIS upload, chat modes, multiple LLM providers, and a Qt/X11 GUI mode. The current README states the Compose stack includes `geollm`, `gee`, and `postgis`, and lists GEE operations for band exports, RGB exports, normalized-difference indices, composite operations, latest imagery checks, projection/resolution controls, scaling, cloud masking, and tile limits.

## Production gaps closed by this overlay

- Adds API-first execution instead of a CLI/GUI-first loop.
- Adds LangGraph orchestration and resumable clarification flow.
- Replaces prompt-only JSON validation with Pydantic contracts.
- Adds an allowlisted GEE plugin client and stable plugin API.
- Adds MCP-compatible tool exposure.
- Removes host networking from the production Compose file.
- Adds health/readiness endpoints and service healthchecks.
- Adds test layers for domain, plugin contract, graph fallback, and API health.
- Adds structured logging and LangSmith tracing hooks.

## Remaining migration work

The only intentionally incomplete part is real Earth Engine execution in `llm_geoprocessing.plugins.gee.api._execute_real_gee`. The existing GEE implementation should be moved behind that function while preserving the new typed HTTP contract.
