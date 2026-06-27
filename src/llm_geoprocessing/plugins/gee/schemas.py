from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, PositiveInt, model_validator

from llm_geoprocessing.domain.geoprocess import Artifact, BBox


class GeeOperation(StrEnum):
    BANDS_SINGLE_DATE = "bands_single_date"
    BANDS_COMPOSITE = "bands_composite"
    RGB_SINGLE_DATE = "rgb_single_date"
    RGB_COMPOSITE = "rgb_composite"
    INDEX_SINGLE_DATE = "index_single_date"
    INDEX_COMPOSITE = "index_composite"
    LATEST_AVAILABLE_DATE = "latest_available_date"
    HAS_IMAGERY = "has_imagery"


SUPPORTED_GEE_OPERATIONS = {operation.value for operation in GeeOperation}


class GeeToolRequest(BaseModel):
    geoprocess_name: GeeOperation
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_id: str

    @model_validator(mode="after")
    def validate_common_safety_fields(self) -> "GeeToolRequest":
        bbox = self.input_json.get("bbox")
        if bbox is not None:
            BBox.from_list([float(value) for value in bbox])
        return self


class GeeToolResponse(BaseModel):
    action_id: str
    status: Literal["succeeded", "failed"] = "succeeded"
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeeCapabilitiesResponse(BaseModel):
    plugin: str = "gee"
    version: str = "v1"
    operations: list[str]
    default_max_tiles: PositiveInt
    hard_max_tiles: PositiveInt
