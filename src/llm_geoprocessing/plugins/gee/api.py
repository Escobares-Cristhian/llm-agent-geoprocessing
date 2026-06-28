from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
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
_EE_INITIALIZED = False


def _tool_descriptors() -> list[ToolDescriptor]:
    base_input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "product_id": {"type": "string"},
            "product": {"type": "string"},
            "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
            "date": {"type": "string", "format": "date"},
            "date_initial": {"type": "string", "format": "date"},
            "date_end": {"type": "string", "format": "date"},
            "bands": {"type": "array", "items": {"type": "string"}},
            "reducer": {"type": "string"},
            "projection": {"type": "string"},
            "resolution": {"oneOf": [{"type": "string"}, {"type": "number"}]},
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


def _init_ee() -> Any:
    """Initialize Earth Engine lazily inside the GEE plugin container."""
    global _EE_INITIALIZED
    try:
        import ee  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - only exercised without optional dependency
        raise HTTPException(
            status_code=500,
            detail={
                "code": "earthengine_dependency_missing",
                "message": "earthengine-api is not installed in the GEE plugin image.",
            },
        ) from exc

    if _EE_INITIALIZED:
        return ee

    settings = get_settings()
    key_path = Path(settings.ee_private_key_path)
    try:
        if key_path.exists():
            import json

            key = json.loads(key_path.read_text(encoding="utf-8"))
            service_account = key.get("client_email")
            project = key.get("project_id")
            credentials = ee.ServiceAccountCredentials(service_account, str(key_path))
            ee.Initialize(credentials, project=project)
        else:
            # Useful for dev containers with already-provisioned EE credentials.
            ee.Initialize()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "earthengine_init_failed",
                "message": str(exc),
                "key_path": str(key_path),
            },
        ) from exc

    _EE_INITIALIZED = True
    return ee


def _date_text(value: Any, *, field_name: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        # Validate shape early for friendlier errors.
        datetime.strptime(value[:10], "%Y-%m-%d")
        return value[:10]
    raise HTTPException(status_code=400, detail={"code": "missing_date", "field": field_name})


def _end_exclusive(end: str) -> str:
    return (datetime.strptime(end, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def _bbox_list(params: dict[str, Any]) -> list[float]:
    bbox = params.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise HTTPException(status_code=400, detail={"code": "invalid_bbox", "message": "bbox must be [west,south,east,north]"})
    return [float(v) for v in bbox]


def _bands(params: dict[str, Any], *, default: list[str] | None = None) -> list[str]:
    value = params.get("bands")
    if value is None:
        value = default or []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _product(params: dict[str, Any]) -> str:
    value = params.get("product") or params.get("product_name") or params.get("collection")
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_product",
                "message": "Real GEE execution requires input_json.product. The graph should hydrate product_id from plan.products.",
                "received_keys": sorted(params.keys()),
            },
        )
    return value.strip()


def _resolution(params: dict[str, Any], product: str) -> float:
    value = params.get("resolution", params.get("res", "default"))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.lower() != "default":
        return float(value)
    upper = product.upper()
    if "S2" in upper or "SENTINEL" in upper:
        return 10.0
    if "LANDSAT" in upper or "LC08" in upper or "LC09" in upper:
        return 30.0
    if "MODIS" in upper:
        return 250.0
    return 30.0


def _reducer_name(params: dict[str, Any]) -> str:
    value = str(params.get("reducer") or "median").lower()
    aliases = {
        "avg": "mean",
        "promedio": "mean",
        "mediana": "median",
        "mínimo": "min",
        "minimo": "min",
        "minimum": "min",
        "máximo": "max",
        "maximo": "max",
        "maximum": "max",
        "mosaico": "mosaic",
    }
    value = aliases.get(value, value)
    if value not in {"mean", "median", "min", "max", "mosaic"}:
        raise HTTPException(status_code=400, detail={"code": "invalid_reducer", "reducer": value})
    return value


def _apply_s2_cloud_mask(ee: Any, image: Any) -> Any:
    # Sentinel-2 SR cloud mask: prefer SCL, otherwise leave image untouched.
    def from_scl(img: Any) -> Any:
        scl = img.select("SCL")
        mask = (
            scl.neq(3)
            .And(scl.neq(7))
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10))
            .And(scl.neq(11))
        )
        return img.updateMask(mask)

    has_scl = image.bandNames().contains("SCL")
    return ee.Image(ee.Algorithms.If(has_scl, from_scl(image), image))


def _collection(ee: Any, product: str, bbox: list[float], start: str, end_exclusive: str, *, cloud_mask: bool) -> Any:
    region = ee.Geometry.Rectangle(bbox, proj="EPSG:4326", geodesic=False)
    collection = ee.ImageCollection(product).filterBounds(region).filterDate(start, end_exclusive)
    if cloud_mask and ("S2_SR" in product.upper() or "SENTINEL" in product.upper()):
        collection = collection.map(lambda img: _apply_s2_cloud_mask(ee, ee.Image(img)))
    return collection, region


def _reduce_collection(collection: Any, reducer: str) -> Any:
    if reducer == "mosaic":
        return collection.mosaic()
    return getattr(collection, reducer)()


def _image_for_request(ee: Any, request: GeeToolRequest) -> tuple[Any, Any, dict[str, Any]]:
    params = dict(request.input_json)
    product = _product(params)
    bbox = _bbox_list(params)
    operation = request.geoprocess_name.value
    cloud_mask = bool(params.get("apply_cloud_mask") or params.get("cloud_mask") or False)

    if operation.endswith("single_date"):
        day = _date_text(params.get("date") or params.get("date_initial"), field_name="date")
        start = day
        end_exclusive = _end_exclusive(day)
    else:
        start = _date_text(params.get("date_initial") or params.get("start"), field_name="date_initial")
        end = _date_text(params.get("date_end") or params.get("end"), field_name="date_end")
        end_exclusive = _end_exclusive(end)

    collection, region = _collection(ee, product, bbox, start, end_exclusive, cloud_mask=cloud_mask)
    reducer = _reducer_name(params)
    metadata: dict[str, Any] = {
        "operation": operation,
        "product": product,
        "bbox": bbox,
        "date_initial": start,
        "date_end_exclusive": end_exclusive,
        "reducer": reducer,
        "cloud_mask": cloud_mask,
    }

    if operation.startswith("index"):
        band_list = _bands(params, default=["B8", "B4"])
        if len(band_list) < 2:
            raise HTTPException(status_code=400, detail={"code": "missing_index_bands", "message": "index operations require two bands"})
        band1, band2 = band_list[0], band_list[1]
        nd_collection = collection.map(lambda img: ee.Image(img).normalizedDifference([band1, band2]).rename("nd"))
        image = nd_collection.mosaic() if operation.endswith("single_date") else _reduce_collection(nd_collection, reducer)
        metadata.update({"bands": [band1, band2], "band_names": ["nd"]})
    elif operation.startswith("rgb"):
        band_list = _bands(params)
        if len(band_list) != 3:
            raise HTTPException(status_code=400, detail={"code": "invalid_rgb_bands", "message": "RGB operations require exactly three bands"})
        selected = collection.select(band_list)
        image = selected.mosaic() if operation.endswith("single_date") else _reduce_collection(selected, reducer)
        metadata.update({"bands": band_list, "band_names": band_list})
    elif operation.startswith("bands"):
        band_list = _bands(params)
        selected = collection.select(band_list) if band_list else collection
        image = selected.mosaic() if operation.endswith("single_date") else _reduce_collection(selected, reducer)
        metadata.update({"bands": band_list or "all"})
    else:
        raise HTTPException(status_code=400, detail={"code": "unsupported_real_gee_operation", "operation": operation})

    image = ee.Image(image).clip(region)
    return image, region, metadata


async def _download_to_file(url: str, artifact_path: Path) -> int:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        raise HTTPException(status_code=500, detail={"code": "invalid_download_url", "scheme": parsed.scheme})
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        response = await client.get(url)
        response.raise_for_status()
    artifact_path.write_bytes(response.content)
    return len(response.content)


async def _execute_real_gee(request: GeeToolRequest) -> GeeToolResponse:
    ee = _init_ee()
    settings = get_settings()
    base_dir = Path(settings.artifact_base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    if request.geoprocess_name in {GeeOperation.LATEST_AVAILABLE_DATE, GeeOperation.HAS_IMAGERY}:
        raise HTTPException(
            status_code=501,
            detail={"code": "metadata_operation_not_implemented", "operation": request.geoprocess_name.value},
        )

    image, region, metadata = _image_for_request(ee, request)
    params = dict(request.input_json)
    product = metadata["product"]
    scale = _resolution(params, product)
    projection = str(params.get("projection") or params.get("proj") or "default")

    download_params: dict[str, Any] = {
        "region": region,
        "scale": scale,
        "format": "GEO_TIFF",
    }
    if projection and projection.lower() != "default":
        download_params["crs"] = projection
        metadata["projection"] = projection
    metadata["scale"] = scale

    try:
        url = image.getDownloadURL(download_params)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "gee_download_url_failed", "message": str(exc), "params": {k: str(v) for k, v in download_params.items()}},
        ) from exc

    artifact_path = base_dir / f"{request.output_id}.tif"
    try:
        byte_count = await _download_to_file(url, artifact_path)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "gee_download_failed", "status_code": exc.response.status_code, "body": exc.response.text[:1000]},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "gee_download_failed", "message": str(exc)}) from exc

    artifact = Artifact(
        kind=ArtifactKind.GEOTIFF,
        uri=str(artifact_path),
        mime_type="image/tiff",
        metadata={**metadata, "byte_count": byte_count, "input_json": request.input_json},
    )
    logger.info("real_gee_artifact_created", extra={"artifact_uri": str(artifact_path), "bytes": byte_count})
    return GeeToolResponse(action_id=request.output_id, artifacts=[artifact], metadata=metadata)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="LLM Geoprocessing GEE Plugin API",
        version="0.3.0",
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
            "ee_private_key_path": str(settings.ee_private_key_path),
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
        max_tiles = int(request.input_json.get("max_tiles", settings.gee_max_tiles_default))
        if max_tiles > settings.gee_max_tiles_hard_limit:
            raise HTTPException(status_code=400, detail="max_tiles exceeds hard limit")
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
