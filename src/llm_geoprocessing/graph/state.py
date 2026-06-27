from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from llm_geoprocessing.domain.geoprocess import ClarificationRequest, GeoProcessPlan, GeoProcessResult, RunStatus


class ChatMessage(TypedDict):
    role: str
    content: str


class AgentState(TypedDict, total=False):
    run_id: str
    thread_id: str
    messages: list[ChatMessage]
    intent: str
    plan: GeoProcessPlan | None
    clarification: ClarificationRequest | None
    result: GeoProcessResult | None
    status: RunStatus
    error: dict[str, Any] | None
    resume_answer: NotRequired[str]
