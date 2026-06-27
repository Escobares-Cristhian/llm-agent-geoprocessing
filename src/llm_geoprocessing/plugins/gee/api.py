from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException

from llm_geoprocessing.domain.config import get_settings
from llm_geoprocessing.domain.geoprocess import Artifact, ArtifactKind
from llm_geoprocessing.observability.logging import configure_logging, get_logger
from llm_geoprocessing.plugins.base import ToolDescriptor
from llm_geoprocessing.plugins.gee.schemas import (
    SUPPORTED_GEE_OPERATIONS,
    GeeCapabilitiesResponse,
    GeeOperation,
    GeeToolRequest,
    GeeToolResponse,
)

logger = get_logger(__name__)


def _tool_descriptors() -> list[ToolDescriptor]:
    base_input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "product_id": {"type": "string"},
            "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
            "date_initial": {"type": "string", "format": "date"},
            "date_end": {"type": "string", "format": "date"},
            "bands": {"type": "array", "items": {"type": "string"}},
            "max_tiles": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": True,
    }
    return [
        ToolDescriptor(
            name=operation.value,
            description=f"Execute GEE geoprocess operation {operation.value}",
            input_schema=base_input_schema,
            output_schema=GeeToolResponse.model_json_schema(),
        )
        for operation in GeeOperation
    ]


def _mock_artifact(request: GeeToolRequest) -> Artifact:
    settings = get_settings()
    base_dir = settings.artifact_base_dir
    base_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(base_dir) / f"{request.output_id}.mock.tif"
    artifact_path.write_text(
        "mock GeoTIFF placeholder produced by production overlay; enable GEE_REAL_EXECUTION for real exports\n",
        encoding="utf-8",
    )
    return Artifact(
        kind=ArtifactKind.GEOTIFF,
        uri=str(artifact_path),
        mime_type="image/tiff",
        metadata={
            "operation": request.geoprocess_name.value,
            "mock": True,
            "input_json": request.input_json,
        },
    )


async def _execute_real_gee(request: GeeToolRequest) -> GeeToolResponse:
    # Integration point for the existing Earth Engine implementation.
    # Keep the public service contract stable and migrate legacy endpoint logic behind this function.
    raise HTTPException(
        status_code=501,
        detail={
            "code": "real_gee_not_migrated",
            "message": "Real GEE execution is disabled in this overlay. Migrate existing Earth Engine logic here or set GEE_REAL_EXECUTION=false.",
            "operation": request.geoprocess_name.value,
        },
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="LLM Geoprocessing GEE Plugin API",
        version="0.2.0",
        description="Typed GEE plugin boundary for the production geoprocessing agent.",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        return {
            "status": "ready",
            "real_execution": settings.gee_real_execution,
            "artifact_base_dir": str(settings.artifact_base_dir),
        }

    @app.get("/capabilities", response_model=GeeCapabilitiesResponse)
    async def capabilities() -> GeeCapabilitiesResponse:
        return GeeCapabilitiesResponse(
            operations=sorted(SUPPORTED_GEE_OPERATIONS),
            default_max_tiles=settings.gee_max_tiles_default,
            hard_max_tiles=settings.gee_max_tiles_hard_limit,
        )

    @app.get("/tools")
    async def tools() -> dict[str, list[dict[str, Any]]]:
        return {"tools": [descriptor.model_dump() for descriptor in _tool_descriptors()]}

    @app.post("/tools/{operation}/invoke", response_model=GeeToolResponse)
    async def invoke(operation: GeeOperation, request: GeeToolRequest) -> GeeToolResponse:
        if operation != request.geoprocess_name:
            raise HTTPException(status_code=400, detail="operation path and payload mismatch")
        if int(request.input_json.get("max_tiles", settings.gee_max_tiles_default)) > settings.gee_max_tiles_hard_limit:
            raise HTTPException(status_code=422, detail="max_tiles exceeds hard limit")
        if settings.gee_real_execution:
            return await _execute_real_gee(request)
        artifact = _mock_artifact(request)
        logger.info("mock_gee_artifact_created", extra={"artifact_uri": artifact.uri})
        return GeeToolResponse(
            action_id=request.output_id,
            artifacts=[artifact],
            metadata={"mock": True, "operation": request.geoprocess_name.value},
        )

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(), host=settings.api_host, port=8000)


if __name__ == "__main__":
    main()
