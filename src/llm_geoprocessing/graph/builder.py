from __future__ import annotations

import asyncio
from typing import Any

from llm_geoprocessing.domain.config import Settings, get_settings
from llm_geoprocessing.graph.nodes import (
    classify_intent,
    execute_tools,
    human_clarification,
    interpret_result,
    plan_geoprocess,
    route_after_clarification,
    route_after_plan,
    route_after_validation,
    validate_plan,
)
from llm_geoprocessing.graph.state import AgentState


class SimpleGeoGraph:
    """Fallback graph for tests when LangGraph is not installed.

    The production API uses ``ainvoke`` so tool execution can await HTTP clients
    without nesting event loops. ``invoke`` remains for synchronous unit tests and
    CLI compatibility only.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ainvoke(self, state: AgentState, config: dict[str, Any] | None = None) -> AgentState:
        state = classify_intent(state)
        state = plan_geoprocess(state, self.settings)
        if state.get("result") is not None:
            return state
        state = validate_plan(state, self.settings)
        if state.get("clarification") is not None:
            return state
        state = await execute_tools(state, self.settings)
        return interpret_result(state, self.settings)

    def invoke(self, state: AgentState, config: dict[str, Any] | None = None) -> AgentState:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ainvoke(state, config=config))
        raise RuntimeError("SimpleGeoGraph.invoke() cannot be called from a running event loop; use ainvoke().")


def build_graph(settings: Settings | None = None) -> Any:
    settings = settings or get_settings()
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return SimpleGeoGraph(settings)

    async def execute_node(state: AgentState) -> AgentState:
        return await execute_tools(state, settings)

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_intent)
    graph.add_node("plan", lambda state: plan_geoprocess(state, settings))
    graph.add_node("validate", lambda state: validate_plan(state, settings))
    graph.add_node("clarify", human_clarification)
    graph.add_node("execute", execute_node)
    graph.add_node("interpret", lambda state: interpret_result(state, settings))

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "plan")
    graph.add_conditional_edges("plan", route_after_plan, {"validate": "validate", "end": END})
    graph.add_conditional_edges("validate", route_after_validation, {"clarify": "clarify", "execute": "execute"})
    graph.add_conditional_edges("clarify", route_after_clarification, {"plan": "plan", "end": END})
    graph.add_edge("execute", "interpret")
    graph.add_edge("interpret", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
