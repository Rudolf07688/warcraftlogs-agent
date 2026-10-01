"""Bridge between the ADK agent and the WebSocket stream.

Builds one cached `Runner` per model (over a single shared in-memory session
service, so conversation memory survives a model switch within a process), and
exposes an async generator that maps ADK events to stream frames:
`tool_start` / `tool_end` / `token`.

Sync Warcraft Logs tools are executed by ADK's own worker thread, so several
tool calls issued by the model in one turn overlap without blocking the event
loop. (Native async I/O via httpx is a documented later improvement.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from wcl_agent.agent import build_agent

APP_NAME = "wcl_app"
USER_ID = "local_user"

_session_service = InMemorySessionService()
_runners: dict[str, Runner] = {}
_RUN_CONFIG = RunConfig(streaming_mode=StreamingMode.SSE)


def _get_runner(model: str) -> Runner:
    runner = _runners.get(model)
    if runner is None:
        runner = Runner(
            agent=build_agent(model),
            app_name=APP_NAME,
            session_service=_session_service,
        )
        _runners[model] = runner
    return runner


async def _ensure_session(session_id: str) -> None:
    """Create the ADK session for this conversation if it doesn't exist yet.

    In-process memory only (v1): reopening a conversation after a restart shows
    stored history in the UI but does not re-seed the model's context. Seeding
    from the DB is a documented later improvement.
    """
    existing = await _session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if existing is None:
        await _session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id, state={}
        )


async def stream_response(
    model: str, session_id: str, user_text: str
) -> AsyncIterator[dict]:
    """Run one turn and yield stream frames (tool_start/tool_end/token).

    Concatenating all `token` frames in order yields the final message text.
    """
    runner = _get_runner(model)
    await _ensure_session(session_id)

    message = types.Content(role="user", parts=[types.Part(text=user_text)])
    streamed_any = False
    final_text = ""

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
        run_config=_RUN_CONFIG,
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            call = getattr(part, "function_call", None)
            if call:
                yield {"type": "tool_start", "name": call.name}
            response = getattr(part, "function_response", None)
            if response:
                yield {"type": "tool_end", "name": response.name, "ok": True}
            text = getattr(part, "text", None)
            if text:
                if getattr(event, "partial", False):
                    streamed_any = True
                    yield {"type": "token", "text": text}
                elif event.is_final_response():
                    final_text = text

    # If the model returned text only in the final (non-partial) event, emit it once.
    if not streamed_any and final_text:
        yield {"type": "token", "text": final_text}
