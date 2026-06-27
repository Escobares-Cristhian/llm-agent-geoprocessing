from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from llm_geoprocessing.domain.geoprocess import ActionSpec, Artifact


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    version: str = "v1"


class ToolExecutionResponse(BaseModel):
    action_id: str
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolClient(ABC):
    @abstractmethod
    async def list_tools(self) -> list[ToolDescriptor]:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, action: ActionSpec) -> ToolExecutionResponse:
        raise NotImplementedError
