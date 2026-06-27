from __future__ import annotations

from fastapi.testclient import TestClient

from llm_geoprocessing.plugins.gee.api import create_app


def test_gee_plugin_exposes_tools() -> None:
    client = TestClient(create_app())
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert any(tool["name"] == "index_composite" for tool in tools)


def test_gee_plugin_mock_invoke() -> None:
    client = TestClient(create_app())
    payload = {
        "geoprocess_name": "index_composite",
        "input_json": {"bbox": [-58.6, -34.7, -58.3, -34.5], "max_tiles": 1},
        "output_id": "ndvi_result",
    }
    response = client.post("/tools/index_composite/invoke", json=payload)
    assert response.status_code == 200
    assert response.json()["artifacts"]
