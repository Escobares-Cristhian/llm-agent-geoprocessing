from __future__ import annotations

import asyncio
from typing import Any

import httpx
try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except ImportError:  # pragma: no cover - production image installs tenacity
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def retry_if_exception_type(*args, **kwargs):
        return None

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None

from llm_geoprocessing.domain.config import Settings
from llm_geoprocessing.domain.errors import ErrorCode, GeoLLMError
from llm_geoprocessing.domain.geoprocess import ActionSpec
from llm_geoprocessing.plugins.base import ToolClient, ToolDescriptor, ToolExecutionResponse
from llm_geoprocessing.plugins.gee.schemas import SUPPORTED_GEE_OPERATIONS, GeeToolResponse


class GeeToolClient(ToolClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.gee_plugin_url.rstrip("/")

    async def list_tools(self) -> list[ToolDescriptor]:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/tools")
            response.raise_for_status()
            data = response.json()
        return [ToolDescriptor.model_validate(item) for item in data["tools"]]

    async def execute(self, action: ActionSpec) -> ToolExecutionResponse:
        if action.geoprocess_name not in SUPPORTED_GEE_OPERATIONS:
            raise GeoLLMError(
                ErrorCode.UNSUPPORTED_TOOL,
                f"unsupported GEE operation: {action.geoprocess_name}",
                {"allowed": sorted(SUPPORTED_GEE_OPERATIONS)},
            )
        response = await self._invoke(action)
        return ToolExecutionResponse(
            action_id=response.action_id,
            artifacts=response.artifacts,
            metadata=response.metadata,
        )

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _invoke(self, action: ActionSpec) -> GeeToolResponse:
        payload: dict[str, Any] = {
            "geoprocess_name": action.geoprocess_name,
            "input_json": action.input_json,
            "output_id": action.output_id,
        }
        timeout = httpx.Timeout(self.settings.tool_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self.base_url}/tools/{action.geoprocess_name}/invoke", json=payload)
                response.raise_for_status()
                return GeeToolResponse.model_validate(response.json())
        except httpx.TimeoutException as exc:
            raise GeoLLMError(
                ErrorCode.TOOL_TIMEOUT,
                "GEE tool invocation timed out",
                {"operation": action.geoprocess_name},
                retryable=True,
            ) from exc
        except httpx.HTTPStatusError as exc:
            body: Any
            try:
                body = exc.response.json()
            except Exception:
                body = exc.response.text
            raise GeoLLMError(
                ErrorCode.TOOL_EXECUTION_ERROR,
                "GEE tool returned an error",
                {"status_code": exc.response.status_code, "body": body},
                retryable=500 <= exc.response.status_code < 600,
            ) from exc


async def execute_sync_compatible(client: GeeToolClient, action: ActionSpec) -> ToolExecutionResponse:
    return await client.execute(action)


def execute_in_new_loop(client: GeeToolClient, action: ActionSpec) -> ToolExecutionResponse:
    return asyncio.run(execute_sync_compatible(client, action))
