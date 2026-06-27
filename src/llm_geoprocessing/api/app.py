from __future__ import annotations

from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from llm_geoprocessing.api.schemas import ResumeRequest, RunRequest, RunResponse
from llm_geoprocessing.domain.config import get_settings
from llm_geoprocessing.domain.errors import GeoLLMError
from llm_geoprocessing.domain.geoprocess import RunStatus
from llm_geoprocessing.graph.builder import build_graph
from llm_geoprocessing.graph.state import AgentState, ChatMessage
from llm_geoprocessing.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)

_RUN_INDEX: dict[str, AgentState] = {}


_CHAT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LLM Geoprocessing Chat</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #0f172a; color: #e2e8f0; }
    main { max-width: 960px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 4px; font-size: 1.5rem; }
    .subtitle { color: #94a3b8; margin-bottom: 20px; }
    #chat { border: 1px solid #334155; border-radius: 14px; min-height: 420px; padding: 16px; background: #020617; overflow-y: auto; }
    .msg { margin: 12px 0; padding: 12px 14px; border-radius: 12px; white-space: pre-wrap; line-height: 1.45; }
    .user { background: #1d4ed8; margin-left: 12%; }
    .assistant { background: #1e293b; margin-right: 12%; }
    .error { background: #7f1d1d; }
    form { display: flex; gap: 10px; margin-top: 14px; }
    textarea { flex: 1; resize: vertical; min-height: 52px; padding: 12px; border-radius: 10px; border: 1px solid #475569; background: #020617; color: #e2e8f0; }
    button { padding: 0 18px; border: 0; border-radius: 10px; background: #22c55e; color: #052e16; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .5; cursor: wait; }
    code { color: #93c5fd; }
    a { color: #93c5fd; }
  </style>
</head>
<body>
<main>
  <h1>LLM Geoprocessing Chat</h1>
  <div class="subtitle">API-backed chat UI for <code>/runs</code>. Default provider can be <code>mock</code>, OpenAI, Gemini, or Ollama.</div>
  <section id="chat"></section>
  <form id="form">
    <textarea id="message" placeholder="Ask for a geoprocess, for example: Calculate NDVI for Sentinel-2 over bbox [-58.4,-34.6,-58.3,-34.5] from 2024-01-01 to 2024-01-31"></textarea>
    <button id="send" type="submit">Send</button>
  </form>
</main>
<script>
const chat = document.getElementById('chat');
const form = document.getElementById('form');
const message = document.getElementById('message');
const send = document.getElementById('send');
const threadId = crypto.randomUUID();
let pendingRunId = null;

function add(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function summarize(data) {
  if (data.status === 'needs_input') {
    pendingRunId = data.run_id;
    return data.clarification || 'I need one more detail before running this.';
  }
  pendingRunId = null;
  if (data.error) return 'Error:\n' + JSON.stringify(data.error, null, 2);
  if (data.result) {
    const artifacts = data.result.artifacts || [];
    const artifactText = artifacts.length
      ? '\n\nArtifacts:\n' + artifacts.map(a => `- ${a.name || a.id}: ${a.uri || a.path || JSON.stringify(a)}`).join('\n')
      : '';
    return (data.result.summary || 'Run completed.') + artifactText + '\n\nStatus: ' + data.status;
  }
  return JSON.stringify(data, null, 2);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = message.value.trim();
  if (!text) return;
  add('user', text);
  message.value = '';
  send.disabled = true;
  try {
    const url = pendingRunId ? `/runs/${pendingRunId}/resume` : '/runs';
    const body = pendingRunId ? { answer: text } : { message: text, thread_id: threadId };
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(data, null, 2));
    add('assistant', summarize(data));
  } catch (err) {
    add('assistant error', String(err));
  } finally {
    send.disabled = false;
    message.focus();
  }
});

add('assistant', 'Ready. Send a geoprocessing request.');
</script>
</body>
</html>"""


def _thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _extract_interrupt(state_or_result: object) -> object | None:
    if isinstance(state_or_result, dict) and "__interrupt__" in state_or_result:
        interrupts = state_or_result["__interrupt__"]
        if interrupts:
            return interrupts[0]
    return None


def _response_from_state(state: AgentState) -> RunResponse:
    return RunResponse(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        status=state.get("status", RunStatus.RUNNING),
        clarification=state.get("clarification"),
        result=state.get("result"),
        error=state.get("error"),
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    graph = build_graph(settings)

    app = FastAPI(
        title="LLM Geoprocessing Agent API",
        version="0.2.0",
        description="API-first production runtime for geospatial LLM agent workflows.",
    )


    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/chat")

    @app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
    async def chat_ui() -> HTMLResponse:
        return HTMLResponse(_CHAT_HTML)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ready", "checkpoint_backend": settings.checkpoint_backend}

    @app.post("/runs", response_model=RunResponse)
    async def create_run(request: RunRequest) -> RunResponse:
        run_id = str(uuid4())
        state: AgentState = {
            "run_id": run_id,
            "thread_id": request.thread_id,
            "messages": [ChatMessage(role="user", content=request.message)],
            "status": RunStatus.CREATED,
        }
        try:
            result = await graph.ainvoke(state, config=_thread_config(request.thread_id))
            interrupt = _extract_interrupt(result)
            if interrupt is not None:
                paused_state = {**state, "status": RunStatus.NEEDS_INPUT}
                _RUN_INDEX[run_id] = paused_state
                return _response_from_state(paused_state)
            assert isinstance(result, dict)
            _RUN_INDEX[run_id] = result
            return _response_from_state(result)
        except GeoLLMError as exc:
            failed = {**state, "status": RunStatus.FAILED, "error": exc.to_dict()}
            _RUN_INDEX[run_id] = failed
            return _response_from_state(failed)

    @app.post("/runs/{run_id}/resume", response_model=RunResponse)
    async def resume_run(run_id: str, request: ResumeRequest) -> RunResponse:
        state = _RUN_INDEX.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="run not found")
        messages = list(state.get("messages", []))
        messages.append(ChatMessage(role="user", content=request.answer))
        resumed_state: AgentState = {**state, "messages": messages, "resume_answer": request.answer}
        try:
            try:
                from langgraph.types import Command

                result = await graph.ainvoke(Command(resume=request.answer), config=_thread_config(state["thread_id"]))
            except Exception:
                result = await graph.ainvoke(resumed_state, config=_thread_config(state["thread_id"]))
            assert isinstance(result, dict)
            _RUN_INDEX[run_id] = result
            return _response_from_state(result)
        except GeoLLMError as exc:
            failed = {**resumed_state, "status": RunStatus.FAILED, "error": exc.to_dict()}
            _RUN_INDEX[run_id] = failed
            return _response_from_state(failed)

    @app.get("/runs/{run_id}", response_model=RunResponse)
    async def get_run(run_id: str) -> RunResponse:
        state = _RUN_INDEX.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _response_from_state(state)

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
