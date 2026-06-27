from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

from llm_geoprocessing.domain.errors import ErrorCode, GeoLLMError


class RunStatus(StrEnum):
    CREATED = "created"
    NEEDS_INPUT = "needs_input"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ActionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ArtifactKind(StrEnum):
    GEOTIFF = "geotiff"
    TILESET = "tileset"
    METADATA = "metadata"
    TABLE = "table"
    MESSAGE = "message"


class BBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    west: float
    south: float
    east: float
    north: float

    @classmethod
    def from_list(cls, values: list[float]) -> "BBox":
        if len(values) != 4:
            raise ValueError("bbox must contain [west, south, east, north]")
        return cls(west=values[0], south=values[1], east=values[2], north=values[3])

    @model_validator(mode="after")
    def validate_bounds(self) -> "BBox":
        if not (-180 <= self.west <= 180 and -180 <= self.east <= 180):
            raise ValueError("bbox longitude must be within [-180, 180]")
        if not (-90 <= self.south <= 90 and -90 <= self.north <= 90):
            raise ValueError("bbox latitude must be within [-90, 90]")
        if self.west >= self.east:
            raise ValueError("bbox west must be less than east")
        if self.south >= self.north:
            raise ValueError("bbox south must be less than north")
        return self

    @property
    def as_list(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]

    @property
    def area_degrees(self) -> float:
        return abs((self.east - self.west) * (self.north - self.south))


class DateRange(BaseModel):
    initial_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_order(self) -> "DateRange":
        if self.initial_date > self.end_date:
            raise ValueError("initial_date cannot be after end_date")
        return self


class ProductSpec(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1)
    date: DateRange
    proj: str = Field(default="default", min_length=1)
    res: float | Literal["default"] = "default"

    @field_validator("name")
    @classmethod
    def validate_product_name(cls, value: str) -> str:
        if value.endswith(("/", "\\")):
            raise ValueError("product name must point to a product, not a folder")
        return value


class ActionSpec(BaseModel):
    geoprocess_name: str = Field(min_length=1)
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")

    @field_validator("geoprocess_name")
    @classmethod
    def normalize_geoprocess_name(cls, value: str) -> str:
        return value.strip()


class GeoProcessPlan(BaseModel):
    schema_version: str = "v1"
    products: list[ProductSpec] = Field(default_factory=list)
    actions: list[ActionSpec] = Field(default_factory=list)
    other_params: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "GeoProcessPlan":
        known_ids = {product.id for product in self.products}
        if len(known_ids) != len(self.products):
            raise ValueError("product ids must be unique")

        output_ids: set[str] = set()
        for index, action in enumerate(self.actions):
            if action.output_id in known_ids or action.output_id in output_ids:
                raise ValueError(f"duplicate output_id: {action.output_id}")
            for key in ("product_id", "product_id1", "product_id2", "input_id", "raster_id"):
                if key in action.input_json:
                    referenced = action.input_json[key]
                    if not isinstance(referenced, str):
                        raise ValueError(f"actions[{index}].input_json.{key} must be a string id")
                    if referenced not in known_ids and referenced not in output_ids:
                        raise ValueError(f"actions[{index}] references unknown id {referenced!r}")
            output_ids.add(action.output_id)
        return self

    def enforce_safety(self, *, max_bbox_area_degrees: float, max_actions: int, max_tiles: int) -> None:
        if len(self.actions) > max_actions:
            raise GeoLLMError(
                ErrorCode.POLICY_VIOLATION,
                f"plan has {len(self.actions)} actions; limit is {max_actions}",
                retryable=False,
            )

        for action in self.actions:
            params = action.input_json
            if "bbox" in params:
                bbox_raw = params["bbox"]
                bbox = BBox.from_list([float(value) for value in bbox_raw])
                if bbox.area_degrees > max_bbox_area_degrees:
                    raise GeoLLMError(
                        ErrorCode.POLICY_VIOLATION,
                        "bbox area exceeds configured safety budget",
                        {"bbox": bbox.as_list, "area_degrees": bbox.area_degrees},
                        retryable=False,
                    )
            if int(params.get("max_tiles", max_tiles)) > max_tiles:
                raise GeoLLMError(
                    ErrorCode.POLICY_VIOLATION,
                    "requested max_tiles exceeds hard limit",
                    {"requested": params.get("max_tiles"), "limit": max_tiles},
                    retryable=False,
                )


class ClarificationRequest(BaseModel):
    question_id: str = Field(default_factory=lambda: str(uuid4()))
    questions: list[str]
    partial_plan: GeoProcessPlan | None = None


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ArtifactKind
    uri: str
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class ActionResult(BaseModel):
    action: ActionSpec
    status: ActionStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class GeoProcessResult(BaseModel):
    run_id: str
    status: RunStatus
    plan: GeoProcessPlan | None = None
    action_results: list[ActionResult] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    answer: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
