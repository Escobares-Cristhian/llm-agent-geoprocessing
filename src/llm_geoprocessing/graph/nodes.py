from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from llm_geoprocessing.domain.config import Settings, get_settings
from llm_geoprocessing.domain.errors import ErrorCode, GeoLLMError
from llm_geoprocessing.domain.geoprocess import (
    ActionResult,
    ActionStatus,
    ClarificationRequest,
    GeoProcessPlan,
    GeoProcessResult,
    RunStatus,
)
from llm_geoprocessing.graph.prompts import INTERPRETER_PROMPT, SYSTEM_PLANNER_PROMPT
from llm_geoprocessing.graph.state import AgentState, ChatMessage
from llm_geoprocessing.llm.factory import LLMFactory
from llm_geoprocessing.observability.tracing import traceable
from llm_geoprocessing.plugins.gee.client import GeeToolClient
from llm_geoprocessing.plugins.gee.schemas import SUPPORTED_GEE_OPERATIONS


def _last_user_message(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _strip_json_markdown_fence(content: str) -> str:
    """Return the most likely JSON object from a model response.

    Gemini and other chat models sometimes obey the schema semantically but wrap
    the payload in ```json fences. Pydantic's model_validate_json intentionally
    expects raw JSON, so we normalize transport noise before validation.
    """
    text = content.strip()
    fence_match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1].strip()
    return text


def _bbox_to_list(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4:
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return None
    if isinstance(value, dict):
        try:
            return [
                float(value["west"]),
                float(value["south"]),
                float(value["east"]),
                float(value["north"]),
            ]
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _product_for_sensor(sensor: str | None) -> str:
    normalized = (sensor or "").upper().replace("-", "_").replace(" ", "_")
    if normalized in {"SENTINEL_2", "S2", "COPERNICUS_S2"}:
        return "COPERNICUS/S2_SR_HARMONIZED"
    if normalized in {"LANDSAT_8", "LANDSAT8", "L8"}:
        return "LANDSAT/LC08/C02/T1_L2"
    if normalized in {"LANDSAT_9", "LANDSAT9", "L9"}:
        return "LANDSAT/LC09/C02/T1_L2"
    return sensor or "COPERNICUS/S2_SR_HARMONIZED"


def _legacy_plan_payload_to_v1(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Translate the old PoC/Gemini-friendly {"plan": [...]} shape to v1.

    This keeps the production API resilient while the prompts and models settle.
    The canonical contract remains GeoProcessPlan v1.
    """
    legacy_actions = payload.get("plan")
    if not isinstance(legacy_actions, list):
        return None

    products: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    assumptions: list[str] = ["Normalized legacy planner JSON shape to GeoProcessPlan v1."]

    for idx, item in enumerate(legacy_actions, start=1):
        if not isinstance(item, dict):
            continue
        operation = str(item.get("operation") or item.get("geoprocess_name") or "").strip()
        if not operation:
            continue

        output_id = str(item.get("id") or item.get("output_id") or f"action_{idx}")
        product_id = f"P{idx}"
        date_value = str(item.get("date") or item.get("initial_date") or item.get("date_initial") or "")
        end_date_value = str(item.get("end_date") or item.get("date_end") or date_value)
        if not date_value:
            date_value = "1970-01-01"
            end_date_value = "1970-01-01"
            assumptions.append(f"Action {output_id} omitted a date; validator may request clarification.")

        product = {
            "id": product_id,
            "name": _product_for_sensor(item.get("sensor")),
            "date": {"initial_date": date_value, "end_date": end_date_value},
            "proj": str(item.get("proj") or "default"),
            "res": item.get("res", "default"),
        }
        products.append(product)

        input_json = dict(item.get("input_json") or {})
        input_json.setdefault("product_id", product_id)
        if bbox := _bbox_to_list(item.get("bbox") or input_json.get("bbox")):
            input_json["bbox"] = bbox
        if item.get("index"):
            input_json.setdefault("index", item["index"])
        if operation.startswith("index"):
            # Default Sentinel-2 NDVI bands; real-GEE implementation can override
            # based on product/index if needed.
            input_json.setdefault("bands", ["B8", "B4"])
        if date_value:
            input_json.setdefault("date", date_value)
            input_json.setdefault("date_initial", date_value)
            input_json.setdefault("date_end", end_date_value)
        if item.get("cloud_cover") is not None:
            input_json.setdefault("cloud_cover", item["cloud_cover"])

        actions.append(
            {
                "geoprocess_name": operation,
                "input_json": input_json,
                "output_id": output_id,
            }
        )

    return {
        "schema_version": "v1",
        "products": products,
        "actions": actions,
        "other_params": {},
        "assumptions": assumptions,
    }


def _parse_geoprocess_plan(content: str) -> GeoProcessPlan:
    normalized = _strip_json_markdown_fence(content)

    # Handle legacy/incorrect-but-common planner shapes before Pydantic silently
    # ignores unknown top-level keys such as {"plan": [...]}.
    payload: Any | None = None
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        converted = _legacy_plan_payload_to_v1(payload)
        if converted is not None:
            return GeoProcessPlan.model_validate(converted)

    return GeoProcessPlan.model_validate_json(normalized)


@traceable("classify_intent")
def classify_intent(state: AgentState) -> AgentState:
    text = _last_user_message(state).lower()
    geospatial_terms = ["ndvi", "gee", "sentinel", "landsat", "bbox", "raster", "geotiff", "composite"]
    intent = "geoprocessing" if any(term in text for term in geospatial_terms) else "conversation"
    return {**state, "intent": intent, "status": RunStatus.RUNNING}


@traceable("plan_geoprocess")
def plan_geoprocess(state: AgentState, settings: Settings | None = None) -> AgentState:
    settings = settings or get_settings()
    if state.get("intent") != "geoprocessing":
        result = GeoProcessResult(
            run_id=state.get("run_id", str(uuid4())),
            status=RunStatus.SUCCEEDED,
            answer="This request does not require a geoprocessing tool. Ask for a spatial product, bbox/date range, and operation to run GEE.",
        )
        return {**state, "result": result, "status": RunStatus.SUCCEEDED}

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PLANNER_PROMPT},
        {"role": "system", "content": f"Allowed operations: {sorted(SUPPORTED_GEE_OPERATIONS)}"},
        *[{"role": m["role"], "content": m["content"]} for m in state.get("messages", [])],
    ]

    if answer := state.get("resume_answer"):
        messages.append({"role": "user", "content": answer})

    model = LLMFactory(settings=settings).create_chat_model()
    raw = model.invoke(messages)
    content = getattr(raw, "content", raw)
    if not isinstance(content, str):
        content = str(content)

    try:
        plan = _parse_geoprocess_plan(content)
    except ValidationError as exc:
        raise GeoLLMError(
            ErrorCode.LLM_OUTPUT_ERROR,
            "planner returned invalid GeoProcessPlan JSON",
            {"errors": exc.errors(), "raw": content[:2000]},
        ) from exc
    except json.JSONDecodeError as exc:
        raise GeoLLMError(
            ErrorCode.LLM_OUTPUT_ERROR,
            "planner did not return JSON",
            {"raw": content[:2000]},
        ) from exc

    return {**state, "plan": plan, "status": RunStatus.RUNNING, "clarification": None}


@traceable("validate_plan")
def validate_plan(state: AgentState, settings: Settings | None = None) -> AgentState:
    settings = settings or get_settings()
    plan = state.get("plan")
    if plan is None:
        clarification = ClarificationRequest(questions=["What geoprocessing operation, product, date range, and bbox should I use?"])
        return {**state, "clarification": clarification, "status": RunStatus.NEEDS_INPUT}

    questions: list[str] = []
    if not plan.products:
        questions.append("Which Earth Engine product should be used?")
    if not plan.actions:
        questions.append("Which geoprocessing action should be executed?")
    for action in plan.actions:
        if action.geoprocess_name not in SUPPORTED_GEE_OPERATIONS:
            questions.append(f"The operation '{action.geoprocess_name}' is not available. Choose one of: {', '.join(sorted(SUPPORTED_GEE_OPERATIONS))}.")
        if "bbox" not in action.input_json:
            questions.append(f"Provide bbox [west, south, east, north] for action '{action.output_id}'.")
        if "max_tiles" not in action.input_json:
            action.input_json["max_tiles"] = settings.gee_max_tiles_default

    if questions:
        return {
            **state,
            "clarification": ClarificationRequest(questions=questions, partial_plan=plan),
            "status": RunStatus.NEEDS_INPUT,
        }

    plan.enforce_safety(
        max_bbox_area_degrees=settings.max_bbox_area_degrees,
        max_actions=settings.max_run_actions,
        max_tiles=settings.gee_max_tiles_hard_limit,
    )
    return {**state, "plan": plan, "status": RunStatus.RUNNING, "clarification": None}


@traceable("human_clarification")
def human_clarification(state: AgentState) -> AgentState:
    clarification = state.get("clarification")
    if clarification is None:
        return state

    try:
        from langgraph.types import interrupt

        answer = interrupt(clarification.model_dump(mode="json"))
        messages = list(state.get("messages", []))
        messages.append(ChatMessage(role="user", content=str(answer)))
        return {**state, "messages": messages, "resume_answer": str(answer), "clarification": None}
    except ImportError:
        return state


@traceable("execute_tools")
async def execute_tools(state: AgentState, settings: Settings | None = None) -> AgentState:
    settings = settings or get_settings()
    plan = state.get("plan")
    run_id = state.get("run_id", str(uuid4()))
    if plan is None:
        return {
            **state,
            "result": GeoProcessResult(
                run_id=run_id,
                status=RunStatus.FAILED,
                error={"code": "missing_plan", "message": "No plan to execute"},
            ),
            "status": RunStatus.FAILED,
        }

    client = GeeToolClient(settings)
    action_results: list[ActionResult] = []
    artifacts = []
    for action in plan.actions:
        try:
            tool_response = await client.execute(action)
            action_result = ActionResult(
                action=action,
                status=ActionStatus.SUCCEEDED,
                artifacts=tool_response.artifacts,
            )
            artifacts.extend(tool_response.artifacts)
        except GeoLLMError as exc:
            action_result = ActionResult(
                action=action,
                status=ActionStatus.FAILED,
                error=exc.to_dict(),
            )
            result = GeoProcessResult(
                run_id=run_id,
                status=RunStatus.FAILED,
                plan=plan,
                action_results=[*action_results, action_result],
                artifacts=artifacts,
                error=exc.to_dict(),
            )
            return {**state, "result": result, "status": RunStatus.FAILED, "error": exc.to_dict()}
        action_results.append(action_result)

    result = GeoProcessResult(
        run_id=run_id,
        status=RunStatus.SUCCEEDED,
        plan=plan,
        action_results=action_results,
        artifacts=artifacts,
    )
    return {**state, "result": result, "status": RunStatus.SUCCEEDED}


@traceable("interpret_result")
def interpret_result(state: AgentState, settings: Settings | None = None) -> AgentState:
    settings = settings or get_settings()
    result = state.get("result")
    if result is None:
        return state
    if result.status == RunStatus.FAILED:
        result.answer = f"The geoprocessing run failed: {result.error}"
        return {**state, "result": result}
    if not result.artifacts:
        result.answer = "The run completed, but no artifacts were produced."
        return {**state, "result": result}

    artifact_lines = [f"- {artifact.kind}: {artifact.uri}" for artifact in result.artifacts]
    assumptions = []
    if result.plan:
        assumptions = result.plan.assumptions
    assumption_text = "\n".join(f"- {item}" for item in assumptions) if assumptions else "- none"
    result.answer = (
        f"Geoprocessing completed successfully.\n\nArtifacts:\n"
        f"{chr(10).join(artifact_lines)}\n\nAssumptions:\n{assumption_text}\n\n"
        f"{INTERPRETER_PROMPT}"
    )
    return {**state, "result": result}


def route_after_plan(state: AgentState) -> str:
    if state.get("result") is not None:
        return "end"
    return "validate"


def route_after_validation(state: AgentState) -> str:
    if state.get("clarification") is not None:
        return "clarify"
    return "execute"


def route_after_clarification(state: AgentState) -> str:
    if state.get("clarification") is not None:
        return "end"
    return "plan"
