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

The Warcraft Logs tools are coroutines over the native async WCL client (feature 013), so
ADK awaits them on the event loop and several tool calls issued by the model in one turn
overlap their I/O without worker threads or blocking the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import unicodedata
from collections.abc import AsyncIterator
from typing import Any

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.sessions.base_session_service import GetSessionConfig
from google.genai import types

from wcl_agent.agent import WEB_SEARCH_AGENT_NAME, build_agent
from wcl_agent.llm.model_retry import ModelRateLimited, RetryPolicy, TurnStats, current_turn

from .agent_tools.kb_tools import KB_TOOLS
from .agent_tools.profile_tools import PROFILE_TOOLS, propose_profile_changes
from .agent_tools.stored_data_tools import STORED_DATA_TOOLS
from .config import settings
from .scratch import TurnScratch
from .services.artifacts import CHART_TOOL_NAME
from .telemetry.metrics import record_conversation_depth, record_finish_reason, record_ttft

logger = logging.getLogger(__name__)

APP_NAME = "wcl_app"
USER_ID = "local_user"
# sc-302: the closing token of a chat turn whose model produced no answer after its tools.
EMPTY_ANSWER_MESSAGE = (
    "I couldn't put an answer together this time: the lookups ran, but no answer came back. "
    "Please try again, or ask a narrower question (one boss, one player or one metric)."
)
PARAGRAPH = "\n\n"

# Feature 080 (sc-569): the status line made from the model's thinking summaries. At most one
# ``thinking`` record per THINKING_INTERVAL_S per turn, at most STATUS_LINE_CHARS long. Only the
# last THOUGHT_KEEP_CHARS of a model call's thought text are kept and scanned.
THINKING_INTERVAL_S = 1.0
STATUS_LINE_CHARS = 80
THOUGHT_KEEP_CHARS = 4000
_thinking_clock = time.monotonic  # tests swap it for a fake clock
# 080 (sc-572), scope:080:retraction-guard: only progress-sized text is retracted as interim.
# Longer text, and text next to a tool that presents (a chart, a profile proposal: the prompt
# asks for the explanation in text), is answer and stays.
INTERIM_MAX_CHARS = 600
PRESENTING_TOOLS = frozenset({CHART_TOOL_NAME, propose_profile_changes.__name__})
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
_MARKDOWN = re.compile(r"[*`~_]{2,}|[*`]|^\s*(?:#{1,6}\s|>\s?|[-+]\s)", re.M)
_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")
# 084 (SPEC L1): a paragraph that opens with a finished heading line ("# Plan", "**Analyzing X**")
# has that heading as its first sentence.
_HEADING_LINE = re.compile(r"[ \t]*(?:#{1,6}[ \t]+[^\n]*|\*\*[^*\n]+\*\*[ \t]*)\n")


def _status_line(text: str, *, complete: bool = False) -> str:
    """One plain line from model text: the first sentence of its latest paragraph (080).

    Model text is untrusted: ANSI sequences, control and format characters (bidi overrides,
    zero-width) and markdown markers are removed and whitespace collapsed, so the line is
    inert wherever it is shown. A still-streaming last paragraph (``complete`` false) counts
    once it has a sentence end or STATUS_LINE_CHARS characters; before that the previous
    paragraph's sentence is used. A paragraph opening with a finished heading line has that
    heading as its sentence (084, SPEC L1). Empty when there is nothing to show.
    """
    text = _ANSI.sub("", text[-THOUGHT_KEEP_CHARS:])
    text = "".join(
        ch for ch in text if ch == "\n" or unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs")
    )
    paragraphs = re.split(r"\n\s*\n", text)
    for i in range(len(paragraphs) - 1, -1, -1):
        heading = _HEADING_LINE.match(paragraphs[i].lstrip("\n"))
        para = " ".join(_MARKDOWN.sub("", heading.group() if heading else paragraphs[i]).split())
        if not para:
            continue
        end = _SENTENCE_END.search(para)
        if heading:
            sentence = para
        elif end:
            sentence = para[: end.end()]
        elif complete or i < len(paragraphs) - 1 or len(para) >= STATUS_LINE_CHARS:
            sentence = para
        else:
            continue
        if len(sentence) > STATUS_LINE_CHARS:
            sentence = sentence[:STATUS_LINE_CHARS].rstrip() + "…"
        return sentence
    return ""

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
            # Feature 029 (C6): the backend-side profile tool joins the WCL tools and the
            # generated capability summary; 044 adds the knowledge search and 045 the exact
            # stored-data lookups. Outside an authenticated chat turn (greeting, guide jobs)
            # they fail closed.
            agent=build_agent(
                model, retry=policy, extra_groups=(PROFILE_TOOLS, KB_TOOLS, STORED_DATA_TOOLS)
            ),
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


# Feature 059: the chat turns a conversation has had, in its ADK session state (session scope).
# Conversations from before 059 count from their first turn after it.
TURNS_KEY = "app_turns"


async def _ensure_session(session_id: str, user_id: str = USER_ID) -> int:
    """Create the ADK session for this conversation if it doesn't exist yet; return the chat
    turns it has had (``TURNS_KEY``, 0 for a new session).

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
        return 0
    turns = (getattr(existing, "state", None) or {}).get(TURNS_KEY)
    return turns if isinstance(turns, int) and not isinstance(turns, bool) and turns > 0 else 0


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
    fallback_model: str | None = None,
) -> AsyncIterator[dict]:
    """Run one turn and yield stream records (see ``_run_turn`` for the record shapes).

    Feature 011: the ADK iteration runs in a producer task that feeds an ``asyncio.Queue``;
    this generator drains it. The model wrapper (``wcl_agent.llm.model_retry``) pushes
    ``{"type": "model_retry", ...}`` records into the same queue via the per-turn
    ``TurnStats`` installed in ``current_turn``, so a retry status reaches the client while
    the producer is asleep in a backoff. ``retry=False`` makes rate limits fail fast
    (helper calls such as the greeting, FR-012). One ``turn stats`` INFO line is logged
    when the turn ends, whatever the outcome (FR-013).

    Feature 021: ``fallback_model`` is the same-class sibling the turn may switch to once
    when its model stays rate limited (only the chat socket passes one). The switch is
    announced as ``{"type": "model_fallback", "from_model", "to_model"}``.
    """
    queue: asyncio.Queue[Any] = asyncio.Queue()
    # PERF-004: the preamble rides on the turn and is injected per model request by the
    # agent's before-model callback, so it is never stored in the ADK session history.
    stats = TurnStats(
        model=model,
        retry_enabled=retry,
        notify=queue.put_nowait,
        preamble=context_preamble or None,
        fallback_model=fallback_model,
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
    tool_calls = 0
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            if isinstance(item, _Failure):
                raise item.exc
            if item.get("type") == "tool_start":
                tool_calls += 1
            yield item
        stats.outcome = stats.outcome or "answered"  # _run_turn may have said "empty"
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
            "prompt_tokens=%s max_prompt_tokens=%s cached_tokens=%s trimmed=%d tool_calls=%d "
            "budget_retries=%d empty_retries=%d time_cuts=%d fallback=%s",
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
            tool_calls,
            stats.budget_retries,
            stats.empty_retries,
            stats.time_cuts,
            stats.switched_to or "-",
        )


def _record_ttft(model: str, stats: TurnStats | None, agent: str, started: float) -> None:
    """Feature 056: the turn's wait for its first answer text, under the model then in use."""
    record_ttft((stats.switched_to if stats else None) or model, agent, time.monotonic() - started)


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
    - `{"type": "tool_start", "name", "args"}` — a tool call began (once per call, with its
      complete args: sent when the model's final event for the call arrives).
    - `{"type": "tool_end", "name", "ok", "args", "result", "result_path"?}` — a
      tool returned; `ok` reflects `result["status"] == "success"`, `args` is the
      originating call's arguments (correlated by id), `result` is the raw tool
      payload. When a per-turn `scratch` store is supplied, the full result is also
      written to disk keyed by the call id and `result_path` points at that file, so
      large concurrent outputs are preserved and picked up after all calls finish (US2).
    - `{"type": "token", "text"}` — a streamed answer chunk; the closing no-answer message
      (below) also carries `"empty": True`, so the caller can tell it from model text (048).
    - `{"type": "thinking", "text"}` — chat turns only (080, sc-569): a transient status line
      from the model's thinking summary (:func:`_status_line`: plain, at most
      STATUS_LINE_CHARS). At most one per THINKING_INTERVAL_S, only from the root agent's
      events, and never while the current segment has answer text. Never part of the answer.
    - `{"type": "interim", "text"}` — chat turns only (080, sc-572): all answer text streamed
      so far was progress, not answer (the model went on to call a tool): drop it, and show
      ``text`` (its first sentence, may be empty) as the status line. Yielded before the
      round's first new `tool_start`, or before its `tool_end` for text written after a call.
      Only for text of at most INTERIM_MAX_CHARS next to no PRESENTING_TOOLS call, and never
      once text was kept as answer (scope:080:retraction-guard). A turn that ends with no
      answer after a retraction gets the retracted text back as a `token` before the
      no-answer message, so nothing the model wrote is lost.

    The agent uses the native thinking planner, so reasoning arrives as separate
    `thought`-marked parts: never answer text, only the source of `thinking` lines.
    The answer is the `token` records after the last `interim` (all of them without one).

    sc-302: for the greeting, guide jobs and evals (the default local user), which get no
    `interim`, text after a tool round starts a new paragraph when text came before it, so an
    interim line ("Let me get the totals.") never runs into the answer. A chat turn (one run
    for a workspace) whose model gives no answer text after its last tool result, with no call
    left pending, ends with :data:`EMPTY_ANSWER_MESSAGE` as its last token and the outcome
    ``empty``.
    """
    turn_started = time.monotonic()
    runner = _get_runner(model)
    # Feature 059: chat turns advance the conversation's turn count with the user's message.
    # The greeting and guide jobs run disposable sessions as the default local user.
    chat = user_id != USER_ID
    turns = (await _ensure_session(session_id, user_id) or 0) + 1
    count_turn = {"state_delta": {TURNS_KEY: turns}} if chat else {}

    # US1: the KNOWN PLAYER CONTEXT preamble is not part of this message. It travels on the
    # turn's TurnStats and is injected per model request (PERF-004), so the ADK history
    # stores only what the user typed.
    message = types.Content(role="user", parts=[types.Part(text=user_text)])
    stats = current_turn.get()
    # Per round, i.e. since the last tool result: streamed text, a final (non-partial) text,
    # and whether either was more than whitespace. ``text_sent``: any text this turn.
    streamed = False
    final_text = ""
    final_author = ""
    timed = False  # feature 056: the first non-blank answer text was timed
    answered = False
    text_sent = False
    grounding_emitted = False
    # Correlate function_response back to its originating function_call by id, so
    # tool_end can carry the arguments (e.g. report_code) the call was made with.
    pending_args: dict[str, dict] = {}
    # US6: monotonic start time per call id, to report each tool call's elapsed ms.
    pending_started: dict[str, float] = {}
    # sc-289: call ids already announced, so a repeated function_call part cannot start a
    # second card.
    started_ids: set[str] = set()
    # 080 (chat turns): ``segment`` holds the answer text streamed since the last ``interim``;
    # ``thought`` the current model call's thought text (reset when the call or round ends).
    root = getattr(getattr(runner, "agent", None), "name", None)
    # ``kept``: answer text stays on screen, so nothing is retracted any more this turn;
    # ``held``: the last retracted text; ``presenting``: this round calls a PRESENTING_TOOLS tool.
    segment: list[str] = []
    kept = False
    held = ""
    presenting = False
    thought = ""
    thinking_at: float | None = None
    thinking_line = ""
    thought_dirty = False  # thought text not yet cleaned into a status line (083 F6)
    # 084 (BUG-005): a model call re-run by the wrapper streams afresh; its thoughts start anew.
    reruns = stats.reruns if stats is not None else 0

    def think(now: float, complete: bool) -> dict | None:
        """Clean ``thought`` into a ``thinking`` record, or ``None`` when the line is empty or
        unchanged. Every run spends the 1/s slot (SEC-003); callers decide when to run it."""
        nonlocal thinking_at, thinking_line, thought_dirty
        thinking_at, thought_dirty = now, False
        line = _status_line(thought, complete=complete)
        if not line or line == thinking_line:
            return None
        thinking_line = line
        return {"type": "thinking", "text": line}

    def retract() -> dict | None:
        """The ``interim`` record for a segment the model followed with a tool call, or
        ``None`` when the segment is answer (scope:080:retraction-guard)."""
        nonlocal text_sent, kept, held, answered
        text = "".join(segment)
        segment.clear()
        if not text:
            return None
        if kept or presenting or len(text) > INTERIM_MAX_CHARS:
            kept = kept or bool(text.strip())
            return None
        held = text
        text_sent = False  # nothing kept: the next text starts the answer, no paragraph join
        answered = False  # 084 (BUG-006): retracted text is no answer, even with the call pending
        if stats is not None:
            stats.answer_shown = False  # 088a BUG-003: progress, so no answer on screen
        return {"type": "interim", "text": _status_line(text, complete=True)}

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
        run_config=_RUN_CONFIG,
        **count_turn,
    ):
        if stats is not None and stats.reruns != reruns:
            reruns = stats.reruns
            thought, thought_dirty = "", False  # the re-run's thoughts are not the cut-off call's
        usage = getattr(event, "usage_metadata", None)
        if not getattr(event, "partial", False):  # a streamed response repeats it on its partials
            record_finish_reason(
                (stats.switched_to if stats else None) or model, getattr(event, "finish_reason", None)
            )
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
        partial = bool(getattr(event, "partial", False))
        for part in event.content.parts:
            call = getattr(part, "function_call", None)
            if call:
                # sc-289: partial events only carry fragments of a call (Anthropic: one per
                # argument chunk, no complete args; Gemini: a copy the aggregated final event
                # repeats). The final event always carries every call with its complete args
                # and id, so the card starts there, exactly once.
                call_id = getattr(call, "id", None)
                if getattr(event, "partial", False) or (call_id and call_id in started_ids):
                    continue
                args = _to_plain(getattr(call, "args", None))
                presenting = presenting or any(
                    getattr(getattr(p, "function_call", None), "name", None) in PRESENTING_TOOLS
                    for p in event.content.parts
                )
                if chat and (interim := retract()):
                    yield interim
                if chat and thought_dirty and not kept and (status := think(_thinking_clock(), complete=True)):
                    yield status  # the call ended with its line held back by the throttle (083 F6)
                if call_id:
                    started_ids.add(call_id)
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
                if chat and (interim := retract()):
                    yield interim  # text the model wrote after its call, in the same round
                if not pending_args:
                    presenting = False  # the round's calls are all answered
                thought, thinking_line, thought_dirty = "", "", False  # the next call thinks afresh
                # US2: deposit the full result on the shared per-turn scratch so large
                # concurrent outputs are preserved and can be picked up when done.
                if scratch is not None:
                    key = call_id or f"{response.name}-{len(pending_args)}"
                    try:
                        # Off the event loop: results can be tens of KB (PERF-016).
                        record["result_path"] = await asyncio.to_thread(scratch.write, key, record)
                    except OSError:
                        pass  # scratch is a durability aid; never fail the turn over it
                streamed, final_text, answered = False, "", False  # a new round starts
                yield record
                continue
            if getattr(part, "thought", False):
                # Model reasoning: never answer text. On a chat turn its summary becomes the
                # status line while no answer text is showing (080).
                text = getattr(part, "text", None)
                if not (chat and text and getattr(event, "author", None) == root):
                    continue
                if kept or "".join(segment).strip():
                    continue  # the answer has started: no status after it
                if partial:
                    thought = (thought + text)[-THOUGHT_KEEP_CHARS:]
                    thought_dirty = True
                elif not thought:
                    thought = text[-THOUGHT_KEEP_CHARS:]  # the call streamed no thought partials
                else:
                    # The call's final event repeats what streamed: the call has ended, so a line
                    # the throttle held back goes out now (083 F6).
                    if thought_dirty and (status := think(_thinking_clock(), complete=True)):
                        yield status
                    continue
                # A clean-up runs at most once a second however small the chunks (080 review
                # SEC-003), and only for a chunk that can yield a line (a sentence end, a
                # paragraph break, or enough text), so an unfinished first chunk spends no slot.
                if partial and not (
                    "\n" in text or _SENTENCE_END.search(text) or len(thought) >= STATUS_LINE_CHARS
                ):
                    continue
                now = _thinking_clock()
                if thinking_at is not None and now - thinking_at < THINKING_INTERVAL_S:
                    continue
                if status := think(now, complete=not partial):
                    yield status
                continue
            text = getattr(part, "text", None)
            if not text:
                continue
            if getattr(event, "partial", False):
                if not timed and text.strip():
                    timed = True
                    _record_ttft(model, stats, getattr(event, "author", ""), turn_started)
                if text_sent and not streamed:
                    text = PARAGRAPH + text
                streamed = text_sent = True
                answered = answered or bool(text.strip())
                if stats is not None and text.strip():
                    stats.answer_shown = True  # 088a BUG-003: read by the Gemini empty-STOP re-run
                if chat:
                    segment.append(text)
                yield {"type": "token", "text": text}
            elif event.is_final_response():
                final_text, final_author = text, getattr(event, "author", "")
        if not partial:
            thought, thought_dirty = "", False  # a model call ended

    # If the last round's text only arrived in the final (non-partial) event, emit it once.
    if not streamed and final_text.strip():
        if not timed:
            _record_ttft(model, stats, final_author, turn_started)
        yield {"type": "token", "text": PARAGRAPH + final_text if text_sent else final_text}
        answered = True
    if not answered and chat:
        if held and not kept:
            # scope:080:retraction-guard: no answer came after the last retraction, so what the
            # model last wrote comes back (ahead of the no-answer message) instead of being lost;
            # also when the turn ends on a call that was never answered (084 BUG-006).
            yield {"type": "token", "text": held}
            text_sent = True
        if not pending_args:
            if stats is not None:
                stats.outcome = "empty"
            closing = PARAGRAPH + EMPTY_ANSWER_MESSAGE if text_sent else EMPTY_ANSWER_MESSAGE
            yield {"type": "token", "text": closing, "empty": True}
    if chat:
        record_conversation_depth(getattr(getattr(runner, "agent", None), "name", ""), turns)
