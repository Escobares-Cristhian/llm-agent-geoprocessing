from fastapi.testclient import TestClient

from llm_geoprocessing.api.app import create_app


def test_chat_ui_served() -> None:
    client = TestClient(create_app())
    response = client.get("/chat")
    assert response.status_code == 200
    assert "LLM Geoprocessing Chat" in response.text
    assert "/runs" in response.text
