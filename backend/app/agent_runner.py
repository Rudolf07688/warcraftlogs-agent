"""Bridge between the ADK agent and the WebSocket stream.

Builds one cached `Runner` per model (over a single shared session service, so
conversation memory survives a model switch within a process), and exposes an
async generator that maps ADK events to stream records.

This generator is the **single source of truth** for tool call/result detail:
each `tool_start` carries the tool `args` (so consumers can read `report_code`)
and each `tool_end` carries the correlated `args` plus the full tool `result`
(so consumers can read `status` and payloads like graph JSON). The WebSocket
layer forwards a user-safe subset to the client and routes the full record to the
raid- and graph-capture services (see services/raids.py, services/graphs.py).

Sync Warcraft Logs tools are executed by ADK's own worker thread, so several
tool calls issued by the model in one turn overlap without blocking the event
loop. (Native async I/O via httpx is a documented later improvement.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from wcl_agent.agent import WEB_SEARCH_AGENT_NAME, build_agent

from .scratch import TurnScratch

APP_NAME = "wcl_app"
USER_ID = "local_user"

# The session service is installed at startup (lifespan) via set_session_service —
# a DatabaseSessionService so conversation *context* survives a restart (US2). If
# never installed (e.g. the CLI or a unit test), it falls back to in-memory.
_session_service: BaseSessionService | None = None
_runners: dict[str, Runner] = {}
_RUN_CONFIG = RunConfig(streaming_mode=StreamingMode.SSE)


def set_session_service(service: BaseSessionService) -> None:
    """Install the process-wide ADK session service and reset cached runners."""
    global _session_service, _runners
    _session_service = service
    _runners = {}  # rebind runners to the new service on next use


def _get_session_service() -> BaseSessionService:
    global _session_service
    if _session_service is None:
        _session_service = InMemorySessionService()
    return _session_service


def _get_runner(model: str) -> Runner:
    runner = _runners.get(model)
    if runner is None:
        runner = Runner(
            agent=build_agent(model),
            app_name=APP_NAME,
            session_service=_get_session_service(),
        )
        _runners[model] = runner
    return runner


def _to_plain(obj: Any) -> dict:
    """Best-effort convert an ADK/genai args or response object to a plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    try:
        return dict(obj)  # MapComposite and similar are dict-like
    except (TypeError, ValueError):
        return {}


def _grounding_sources(gm: Any) -> list[dict]:
    """Extract {title, uri} source entries from an event's grounding_metadata."""
    sources: list[dict] = []
    for chunk in getattr(gm, "grounding_chunks", None) or []:
        web = getattr(chunk, "web", None)
        if web is not None:
            sources.append({"title": getattr(web, "title", None), "uri": getattr(web, "uri", None)})
    return sources


async def _ensure_session(session_id: str) -> None:
    """Create the ADK session for this conversation if it doesn't exist yet.

    With the DatabaseSessionService (US2), the session — including tool/turn
    context — is loaded from Postgres, so reopening a conversation after a restart
    restores the model's context, not just the displayed transcript.
    """
    service = _get_session_service()
    existing = await service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if existing is None:
        await service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id, state={}
        )


async def stream_response(
    model: str, session_id: str, user_text: str, scratch: TurnScratch | None = None
) -> AsyncIterator[dict]:
    """Run one turn and yield stream records.

    Yields dicts of these shapes (the WS layer filters/forwards them):
    - `{"type": "tool_start", "name", "args"}` — a tool call began.
    - `{"type": "tool_end", "name", "ok", "args", "result", "result_path"?}` — a
      tool returned; `ok` reflects `result["status"] == "success"`, `args` is the
      originating call's arguments (correlated by id), `result` is the raw tool
      payload. When a per-turn `scratch` store is supplied, the full result is also
      written to disk keyed by the call id and `result_path` points at that file, so
      large concurrent outputs are preserved and picked up after all calls finish (US2).
    - `{"type": "token", "text"}` — a streamed answer chunk.

    The agent uses the native thinking planner, so reasoning arrives as separate
    `thought`-marked parts which we skip — only the answer text is streamed.
    Concatenating all `token` records yields the answer.
    """
    runner = _get_runner(model)
    await _ensure_session(session_id)

    message = types.Content(role="user", parts=[types.Part(text=user_text)])
    streamed_any = False
    final_text = ""
    grounding_emitted = False
    # Correlate function_response back to its originating function_call by id, so
    # tool_end can carry the arguments (e.g. report_code) the call was made with.
    pending_args: dict[str, dict] = {}

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
        run_config=_RUN_CONFIG,
    ):
        # US3: surface native web grounding once per turn. The grounding sub-agent
        # propagates its grounding_metadata to the parent event stream.
        if not grounding_emitted:
            gm = getattr(event, "grounding_metadata", None)
            if gm is not None:
                grounding_emitted = True
                yield {"type": "grounding", "used": True, "sources": _grounding_sources(gm)}

        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            call = getattr(part, "function_call", None)
            if call:
                args = _to_plain(getattr(call, "args", None))
                call_id = getattr(call, "id", None)
                if call_id:
                    pending_args[call_id] = args
                # Fallback grounding signal: the model invoked the web_search tool
                # (used when grounding_metadata isn't propagated).
                if call.name == WEB_SEARCH_AGENT_NAME and not grounding_emitted:
                    grounding_emitted = True
                    yield {"type": "grounding", "used": True, "sources": []}
                yield {"type": "tool_start", "name": call.name, "args": args}
                continue
            response = getattr(part, "function_response", None)
            if response:
                call_id = getattr(response, "id", None)
                args = pending_args.pop(call_id, {}) if call_id else {}
                result = _to_plain(getattr(response, "response", None))
                ok = result.get("status") == "success"
                record = {
                    "type": "tool_end",
                    "name": response.name,
                    "ok": ok,
                    "args": args,
                    "result": result,
                }
                # US2: deposit the full result on the shared per-turn scratch so large
                # concurrent outputs are preserved and can be picked up when done.
                if scratch is not None:
                    key = call_id or f"{response.name}-{len(pending_args)}"
                    try:
                        record["result_path"] = scratch.write(key, record)
                    except OSError:
                        pass  # scratch is a durability aid; never fail the turn over it
                yield record
                continue
            if getattr(part, "thought", False):
                continue  # model reasoning — never shown to the user
            text = getattr(part, "text", None)
            if not text:
                continue
            if getattr(event, "partial", False):
                streamed_any = True
                yield {"type": "token", "text": text}
            elif event.is_final_response():
                final_text = text

    # If text only arrived in the final (non-partial) event, emit it once.
    if not streamed_any and final_text:
        yield {"type": "token", "text": final_text}
