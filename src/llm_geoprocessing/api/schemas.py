from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from llm_geoprocessing.domain.geoprocess import ClarificationRequest, GeoProcessResult, RunStatus


class RunRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResumeRequest(BaseModel):
    answer: str = Field(min_length=1)


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: RunStatus
    clarification: ClarificationRequest | None = None
    result: GeoProcessResult | None = None
    error: dict[str, Any] | None = None
