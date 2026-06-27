from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    UNSUPPORTED_TOOL = "unsupported_tool"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    POLICY_VIOLATION = "policy_violation"
    CONFIGURATION_ERROR = "configuration_error"
    LLM_OUTPUT_ERROR = "llm_output_error"


@dataclass(slots=True)
class GeoLLMError(Exception):
    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details or {},
            "retryable": self.retryable,
        }
