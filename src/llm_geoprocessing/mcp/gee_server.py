from __future__ import annotations

import asyncio
from typing import Any

from llm_geoprocessing.domain.config import get_settings
from llm_geoprocessing.domain.geoprocess import ActionSpec
from llm_geoprocessing.plugins.gee.client import GeeToolClient
from llm_geoprocessing.plugins.gee.schemas import GeeOperation


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install the 'mcp' package to run the GEE MCP server") from exc

    settings = get_settings()
    mcp = FastMCP("llm-geoprocessing-gee")
    client = GeeToolClient(settings)

    @mcp.tool()
    async def invoke_gee_tool(operation: GeeOperation, input_json: dict[str, Any], output_id: str) -> dict[str, Any]:
        """Invoke an allowlisted Google Earth Engine geoprocessing tool."""
        action = ActionSpec(geoprocess_name=operation.value, input_json=input_json, output_id=output_id)
        response = await client.execute(action)
        return response.model_dump(mode="json")

    mcp.run()


if __name__ == "__main__":
    main()
