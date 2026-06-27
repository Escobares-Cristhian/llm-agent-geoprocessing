from __future__ import annotations

import pytest

from llm_geoprocessing.domain.config import Settings
from llm_geoprocessing.domain.errors import GeoLLMError
from llm_geoprocessing.domain.geoprocess import ActionSpec
from llm_geoprocessing.plugins.gee.client import GeeToolClient


@pytest.mark.asyncio
async def test_gee_client_rejects_unsupported_tool_before_network() -> None:
    client = GeeToolClient(Settings(GEO_LLM_PROVIDER="mock"))
    with pytest.raises(GeoLLMError) as exc:
        await client.execute(ActionSpec(geoprocess_name="rm_rf", input_json={}, output_id="x"))
    assert exc.value.code == "unsupported_tool"
