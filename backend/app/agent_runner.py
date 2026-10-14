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

The sync Warcraft Logs tools are wrapped with ``wcl_agent.threading_utils.off_loop`` in
``build_agent``, so each runs in a worker thread. ADK itself runs sync tools inline on the
event loop in SSE mode. As a result, several tool calls issued by the model in one turn
overlap without blocking the event loop. (Native async I/O via httpx is a documented later
improvement.)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.sessions.base_session_service import GetSessionConfig
from google.genai import types

from wcl_agent.agent import WEB_SEARCH_AGENT_NAME, build_agent
from wcl_agent.model_retry import ModelRateLimited, RetryPolicy, TurnStats, current_turn

from .config import settings
from .scratch import TurnScratch

logger = logging.getLogger(__name__)

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
        # Feature 011: rate-limit retry + round cap are operator-tunable (FR-006). Runners
        # are cached per model, so a settings change takes effect on the next restart.
        policy = RetryPolicy(
            attempts=settings.wcl_model_retry_attempts,
            initial_s=settings.wcl_model_retry_initial_s,
            max_s=settings.wcl_model_retry_max_s,
            budget_s=settings.wcl_model_retry_budget_s,
            round_cap=settings.wcl_turn_round_cap,
        )
        runner = Runner(
            agent=build_agent(model, retry=policy),
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


async def _ensure_session(session_id: str, user_id: str = USER_ID) -> None:
    """Create the ADK session for this conversation if it doesn't exist yet.

    With the DatabaseSessionService (US2), the session — including tool/turn
    context — is loaded from Postgres, so reopening a conversation after a restart
    restores the model's context, not just the displayed transcript.

    ``user_id`` isolates ADK session state per tenant (feature 006): the WS layer passes
    ``str(tenant_id)`` so one tenant can never load another's ADK context. Defaults to the
    legacy ``USER_ID`` for the disposable greeting session (no tenant).
    """
    service = _get_session_service()
    # Existence check only: load no events (PERF-008). The runner loads the history itself.
    existing = await service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        config=GetSessionConfig(num_recent_events=0),
    )
    if existing is None:
        await service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id, state={}
        )


_DONE = object()  # producer -> consumer sentinel (feature 011)


class _Failure:
    """Carries a producer exception across the queue so the consumer re-raises it."""

    __slots__ = ("exc",)

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


async def stream_response(
    model: str,
    session_id: str,
    user_text: str,
    scratch: TurnScratch | None = None,
    context_preamble: str | None = None,
    *,
    user_id: str = USER_ID,
    retry: bool = True,
) -> AsyncIterator[dict]:
    """Run one turn and yield stream records (see ``_run_turn`` for the record shapes).

    Feature 011: the ADK iteration runs in a producer task that feeds an ``asyncio.Queue``;
    this generator drains it. The model wrapper (``wcl_agent.model_retry``) pushes
    ``{"type": "model_retry", ...}`` records into the same queue via the per-turn
    ``TurnStats`` installed in ``current_turn``, so a retry status reaches the client while
    the producer is asleep in a backoff. ``retry=False`` makes rate limits fail fast
    (helper calls such as the greeting, FR-012). One ``turn stats`` INFO line is logged
    when the turn ends, whatever the outcome (FR-013).
    """
    queue: asyncio.Queue[Any] = asyncio.Queue()
    # PERF-004: the preamble rides on the turn and is injected per model request by the
    # agent's before-model callback, so it is never stored in the ADK session history.
    stats = TurnStats(
        model=model,
        retry_enabled=retry,
        notify=queue.put_nowait,
        preamble=context_preamble or None,
    )
    token = current_turn.set(stats)

    async def produce() -> None:
        try:
            async for record in _run_turn(
                model,
                session_id,
                user_text,
                scratch,
                user_id=user_id,
            ):
                queue.put_nowait(record)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised by the consumer
            queue.put_nowait(_Failure(exc))
        else:
            queue.put_nowait(_DONE)

    producer = asyncio.create_task(produce())
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            if isinstance(item, _Failure):
                raise item.exc
            yield item
        stats.outcome = "answered"
    except ModelRateLimited:
        stats.outcome = "rate_limited"
        raise
    except Exception:
        stats.outcome = "error"
        raise
    finally:
        if not producer.done():
            producer.cancel()  # consumer went away mid-turn (e.g. WebSocket closed)
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await producer
        if stats.outcome is None:
            stats.outcome = "abandoned"
        try:
            current_turn.reset(token)
        except ValueError:  # finalised from another context (GC); just clear it
            current_turn.set(None)
        logger.info(
            "turn stats model=%s requests=%d rounds=%d retries=%d waited_s=%.1f outcome=%s "
            "prompt_tokens=%s max_prompt_tokens=%s cached_tokens=%s trimmed=%d",
            stats.model,
            stats.model_requests,
            stats.tool_rounds,
            stats.retries,
            stats.waited_s,
            stats.outcome,
            stats.last_prompt_tokens,
            stats.max_prompt_tokens,
            stats.last_cached_tokens,
            stats.trimmed_results,
        )


async def _run_turn(
    model: str,
    session_id: str,
    user_text: str,
    scratch: TurnScratch | None = None,
    *,
    user_id: str = USER_ID,
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
    await _ensure_session(session_id, user_id)

    # US1: the KNOWN PLAYER CONTEXT preamble is not part of this message. It travels on the
    # turn's TurnStats and is injected per model request (PERF-004), so the ADK history
    # stores only what the user typed.
    message = types.Content(role="user", parts=[types.Part(text=user_text)])
    stats = current_turn.get()
    streamed_any = False
    final_text = ""
    grounding_emitted = False
    # Correlate function_response back to its originating function_call by id, so
    # tool_end can carry the arguments (e.g. report_code) the call was made with.
    pending_args: dict[str, dict] = {}
    # US6: monotonic start time per call id, to report each tool call's elapsed ms.
    pending_started: dict[str, float] = {}

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
        run_config=_RUN_CONFIG,
    ):
        usage = getattr(event, "usage_metadata", None)
        if stats is not None and usage is not None:
            stats.record_prompt_tokens(
                getattr(usage, "prompt_token_count", None),
                getattr(usage, "cached_content_token_count", None),
            )
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
                    pending_started[call_id] = time.monotonic()
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
                started = pending_started.pop(call_id, None) if call_id else None
                result = _to_plain(getattr(response, "response", None))
                ok = result.get("status") == "success"
                record = {
                    "type": "tool_end",
                    "name": response.name,
                    "ok": ok,
                    "args": args,
                    "result": result,
                }
                if started is not None:
                    record["ms"] = int((time.monotonic() - started) * 1000)
                # US2: deposit the full result on the shared per-turn scratch so large
                # concurrent outputs are preserved and can be picked up when done.
                if scratch is not None:
                    key = call_id or f"{response.name}-{len(pending_args)}"
                    try:
                        # Off the event loop: results can be tens of KB (PERF-016).
                        record["result_path"] = await asyncio.to_thread(scratch.write, key, record)
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
