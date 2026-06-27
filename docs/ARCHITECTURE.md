# Architecture

```text
client
  |
  v
geollm-api FastAPI
  |
  v
LangGraph agent
  |-- classify_intent
  |-- plan_geoprocess
  |-- validate_plan
  |-- human_clarification
  |-- execute_tools
  |-- interpret_result
  |
  +--> LangSmith traces
  +--> PostGIS/checkpoints/artifact metadata
  +--> GEE tool client
           |
           v
      gee-plugin-api FastAPI
           |
           +--> mock artifact mode
           +--> real Earth Engine migration point
```

## Design decisions

1. **Headless API is the production interface.** CLI/GUI clients should call the API instead of owning orchestration.
2. **LangGraph owns control flow.** Each step is a named node so retries, traces, checkpoints, and human interrupts are observable.
3. **Pydantic owns contracts.** LLM output is not trusted until it validates as `GeoProcessPlan`.
4. **Plugins are allowlisted tools.** The LLM never executes arbitrary Python, SQL, shell, or URLs.
5. **Docker is the only supported runtime.** Compose DNS replaces Linux-only host networking.
6. **MCP is an integration surface, not a security boundary.** Tool names remain allowlisted and validated server-side.

## Graph state

`AgentState` stores `run_id`, `thread_id`, chat messages, intent, plan, clarification request, result, and structured errors.

## Artifact handling

Artifacts are represented as typed records with `kind`, `uri`, `mime_type`, and metadata. Production object storage can replace the local volume later without changing graph state.
