from __future__ import annotations

from llm_geoprocessing.domain.config import Settings
from llm_geoprocessing.domain.geoprocess import RunStatus
from llm_geoprocessing.graph.builder import SimpleGeoGraph
from llm_geoprocessing.graph.state import ChatMessage


def test_simple_graph_non_geospatial_finishes_without_tool() -> None:
    graph = SimpleGeoGraph(Settings(GEO_LLM_PROVIDER="mock", POSTGIS_ENABLED=False))
    state = graph.invoke(
        {
            "run_id": "r1",
            "thread_id": "t1",
            "messages": [ChatMessage(role="user", content="hello")],
        }
    )
    assert state["status"] == RunStatus.SUCCEEDED
    assert state["result"] is not None
