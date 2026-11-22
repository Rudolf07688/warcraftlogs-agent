"""Model rate-limit relief (feature 011): retry policy, per-turn stats, error classification.

Why this exists instead of the SDKs' own retries: both google-genai (``HttpRetryOptions``)
and the Anthropic SDK (``max_retries``) can retry a 429 natively, but a native retry is
invisible to the application — nothing can show the player a "busy, retrying" status or
count retries per turn — and the two SDKs back off on different schedules with no shared
wait budget. So the SDK retries stay off and one loop here (see ``RetryingGemini`` /
``RetryingClaude``) owns the waiting for both providers.

Plumbing: ``backend.app.agent_runner.stream_response`` creates a ``TurnStats`` for each
turn and installs it in the ``current_turn`` ContextVar. ADK runs the model call (and
parallel tool calls) in tasks spawned from the turn's task, which inherit the context, so
the model wrapper and the ``before_model_callback`` always find the right turn. Without a
turn (the CLI, unit tests) everything degrades to "retry with the policy, notify nobody".

Feature 021: when a chat turn's request stays rate limited after the retries, the wrappers
switch it once to the same-class sibling model (``generate_with_fallback``); the chat
socket sets the sibling on the turn's ``TurnStats``. sc-176: while that switch is still
possible the turn's model gets only a short retry, and a model whose retries ran out is
remembered for a few minutes, so the next turns start on the sibling straight away.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import random
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Any

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types
from pydantic import Field

from .context_trim import keep_turns, trim_old_tool_results, user_turn_indices
from .provider import adk_client_kwargs, async_anthropic_client

logger = logging.getLogger(__name__)

# Statuses that mean "try again shortly" rather than "this request is wrong".
_RATE_LIMIT_HTTP_CODES = frozenset({429, 503, 529})
_RATE_LIMIT_GRPC_STATUSES = frozenset({"RESOURCE_EXHAUSTED", "UNAVAILABLE"})


@dataclass(frozen=True)
class RetryPolicy:
    """Operator configuration for rate-limit retries (FR-006). Immutable per process."""

    attempts: int = 5  # including the first try; 1 = never retry
    initial_s: float = 2.0
    max_s: float = 30.0
    budget_s: float = 90.0  # total wall-clock spent waiting, per model request
    exp_base: float = 2.0
    jitter_s: float = 1.0
    round_cap: int = 6  # lookup rounds a turn may use before being told to wrap up

    def delay_for(self, attempt: int, hint_s: float | None = None) -> float:
        """Seconds to wait before retry number ``attempt`` (1-based).

        A server-provided wait hint (``Retry-After``) wins over the computed schedule
        (FR-007); the caller still bounds it by the remaining budget.
        """
        if hint_s is not None and hint_s >= 0:
            return float(hint_s)
        base = min(self.initial_s * (self.exp_base ** max(attempt - 1, 0)), self.max_s)
        return base + random.uniform(0, self.jitter_s)


@dataclass
class TurnStats:
    """Per-turn tally + signal channel (FR-013). Logged once when the turn ends."""

    model: str
    retry_enabled: bool = True
    notify: Callable[[dict], None] | None = None
    model_requests: int = 0
    retries: int = 0
    waited_s: float = 0.0
    outcome: str | None = None  # answered | empty | rate_limited | error | abandoned
    # PERF-004: per-turn standing context (KNOWN PLAYER CONTEXT), injected into each model
    # request by the before-model callback so it is never stored in the session history.
    preamble: str | None = None
    # PERF-004: prompt size of the turn's model requests, for the turn stats log line.
    last_prompt_tokens: int | None = None
    max_prompt_tokens: int | None = None
    # How much of the last prompt the provider served from its cache (implicit caching).
    last_cached_tokens: int | None = None
    # Old tool results replaced by stubs across the turn's requests (context_trim).
    trimmed_results: int = 0
    # Feature 021: the same-class sibling this turn may switch to once (set by the chat
    # socket only), the model it switched to, and the request length at the switch.
    fallback_model: str | None = None
    switched_to: str | None = None
    switch_index: int | None = None
    # 079 sc-568: the instruction's time block as the turn's first Claude request sent it, so
    # every later request of the turn repeats it and its cached prompt stays valid.
    pinned_time: str | None = None
    # 079 sc-567: Claude calls that ended on max_tokens with only thinking and were re-run
    # (084 sc-580: also those cut at CLAUDE_CALL_TIMEOUT_S before any answer text).
    budget_retries: int = 0
    # 084 sc-586: Gemini calls that ended STOP with nothing in them and were re-run.
    empty_retries: int = 0
    # 088a BUG-003: answer text is on screen (set by the runner, cleared when it is retracted as
    # progress). A Gemini empty STOP is re-run only while it is False.
    answer_shown: bool = False
    # 088a BUG-001: Claude calls cut at CLAUDE_CALL_TIMEOUT_S after answer text (ended with CUT_LINE).
    time_cuts: int = 0

    def record_prompt_tokens(self, count: int | None, cached: int | None = None) -> None:
        if count is None:
            return
        self.last_prompt_tokens = count
        self.max_prompt_tokens = max(self.max_prompt_tokens or 0, count)
        self.last_cached_tokens = cached

    @property
    def reruns(self) -> int:
        """Re-runs of this turn's model calls so far (at most one per call, any kind)."""
        return self.budget_retries + self.empty_retries

    @property
    def tool_rounds(self) -> int:
        """Model requests that carried tool results back — i.e. lookup rounds."""
        return max(self.model_requests - 1, 0)

    def cap_reached(self, policy: RetryPolicy) -> bool:
        return self.tool_rounds >= policy.round_cap

    def emit(self, record: dict) -> None:
        """Push a record to the turn's output stream; never let a UI hiccup break a turn."""
        if self.notify is None:
            return
        try:
            self.notify(record)
        except Exception:  # noqa: BLE001
            logger.debug("turn notify failed", exc_info=True)


current_turn: contextvars.ContextVar[TurnStats | None] = contextvars.ContextVar(
    "wcl_current_turn", default=None
)


class ModelRateLimited(Exception):
    """The model stayed rate-limited for longer than the policy allows (FR-004)."""

    def __init__(self, attempts: int, waited_s: float, last_error: BaseException) -> None:
        self.attempts = attempts
        self.waited_s = waited_s
        self.last_error = last_error
        super().__init__(
            f"model rate-limited after {attempts} attempt(s) and {waited_s:.1f}s of waiting: "
            f"{type(last_error).__name__}: {last_error}"
        )


def is_rate_limited(exc: BaseException) -> bool:
    """True for transient rate-limit / overloaded refusals from either provider (FR-002).

    google-genai: ``APIError`` with HTTP 429/503 or gRPC status RESOURCE_EXHAUSTED /
    UNAVAILABLE. Anthropic: ``RateLimitError`` (429), ``OverloadedError`` (529), or any
    ``APIStatusError`` carrying one of those codes (ADK re-raises the SDK's own classes,
    so isinstance checks hold). Everything else is not fixed by waiting.
    """
    try:
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover - genai is a hard dependency in practice
        genai_errors = None
    if genai_errors is not None and isinstance(exc, genai_errors.APIError):
        if getattr(exc, "code", None) in _RATE_LIMIT_HTTP_CODES:
            return True
        return (getattr(exc, "status", None) or "").upper() in _RATE_LIMIT_GRPC_STATUSES

    try:
        import anthropic
    except ImportError:  # pragma: no cover - optional provider
        return False
    if isinstance(exc, (anthropic.RateLimitError, anthropic.OverloadedError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return getattr(exc, "status_code", None) in _RATE_LIMIT_HTTP_CODES
    return False


def retry_after_hint(exc: BaseException) -> float | None:
    """Seconds from a ``Retry-After`` header on the failed response, if numeric."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")
    except Exception:  # noqa: BLE001 - exotic header containers
        return None
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form: fall back to the computed schedule
    return value if value >= 0 else None


# --- the retry loop and the ADK model wrappers (US1) -------------------------------------


async def generate_with_retry(
    inner: Callable[[], AsyncGenerator[Any, None]],
    policy: RetryPolicy,
    *,
    deadline: float | None = None,
) -> AsyncGenerator[Any, None]:
    """Drive ``inner()`` (a fresh model-call generator per attempt) with rate-limit retries.

    Retries only when the failure is a rate limit (FR-002), nothing has been yielded yet
    (a mid-stream retry would duplicate streamed text), attempts remain, and the next
    delay still fits the wait budget and ends by ``deadline`` (a :data:`_clock` time, so
    requests count too; 052 sc-297). Each retry is announced on the current turn as a
    ``model_retry`` record (FR-003) and counted (FR-013). When the turn has
    ``retry_enabled=False`` (helper calls, FR-012) the first rate limit fails fast.
    """
    stats = current_turn.get()
    attempts_allowed = policy.attempts if stats is None or stats.retry_enabled else 1
    attempts_allowed = max(attempts_allowed, 1)
    attempt = 1
    waited = 0.0
    while True:
        yielded = False
        try:
            async for response in inner():
                yielded = True
                yield response
            return
        except Exception as exc:  # noqa: BLE001 - classified below
            if yielded or not is_rate_limited(exc):
                raise
            if attempt >= attempts_allowed:
                raise ModelRateLimited(attempt, waited, exc) from exc
            delay = policy.delay_for(attempt, retry_after_hint(exc))
            if waited + delay > policy.budget_s or (
                deadline is not None and _clock() + delay > deadline
            ):
                raise ModelRateLimited(attempt, waited, exc) from exc
            logger.warning(
                "model rate-limited (%s: %s); retry %d/%d in %.1fs",
                type(exc).__name__,
                exc,
                attempt,
                attempts_allowed - 1,
                delay,
            )
            if stats is not None:
                stats.emit(
                    {
                        "type": "model_retry",
                        "attempt": attempt,
                        "max_attempts": attempts_allowed,
                        "wait_s": round(delay, 1),
                    }
                )
            await asyncio.sleep(delay)
            waited += delay
            if stats is not None:
                stats.retries += 1
                stats.waited_s += delay
            attempt += 1


# sc-176: while a turn can still switch, its model gets one retry within a few seconds
# rather than the full schedule (5 attempts, up to the 90 s budget) before the sibling.
_PRIMARY_ATTEMPTS = 2
_PRIMARY_BUDGET_S = 10.0
# sc-268: when both the turn's model and its sibling are remembered as limited, the turn
# gets this one wait budget in all: the primary's short probe and the sibling's retries
# together, so it fails with the "both busy" outcome in about this long, not probe + the
# sibling's full schedule (about 40 s, up to 100 s). 052 sc-297: a deadline on ``_clock``
# (monotonic) that the requests count against too, so it is 10 s plus at most one request.
_BOTH_LIMITED_BUDGET_S = 10.0
_clock = time.monotonic
# How long a model whose retries ran out is skipped in favour of its sibling.
RATE_LIMIT_MEMORY_S = 300.0
_limited_until: dict[str, float] = {}


def _remember_limited(model: str | None, stats: TurnStats | None) -> None:
    """Remember ``model`` only when a chat turn's retries really ran out (QA BUG-002): a
    retry-disabled helper (the greeting) fails on its first 429, and a turn without a
    sibling (background jobs) has nothing to switch to."""
    if model and stats is not None and stats.retry_enabled and stats.fallback_model:
        _limited_until[model] = time.monotonic() + RATE_LIMIT_MEMORY_S


def _short(policy: RetryPolicy) -> RetryPolicy:
    """The quick probe a model gets while its turn can still switch (sc-176)."""
    return replace(
        policy,
        attempts=min(policy.attempts, _PRIMARY_ATTEMPTS),
        budget_s=min(policy.budget_s, _PRIMARY_BUDGET_S),
    )


def recently_limited(model: str | None) -> bool:
    """Whether ``model`` ran out of rate-limit retries within ``RATE_LIMIT_MEMORY_S``."""
    until = _limited_until.get(model or "")
    if until is None:
        return False
    if until <= time.monotonic():
        del _limited_until[model]
        return False
    return True


def forget_rate_limits() -> None:
    """Clear the memory (tests, or after an operator raises the quota)."""
    _limited_until.clear()


# Google's documented stand-in for a function-call thought signature from another model.
_FOREIGN_SIGNATURE = b"skip_thought_signature_validator"


def _route_to_sibling(llm_request: LlmRequest, stats: TurnStats) -> None:
    """Point this request at the turn's sibling model (feature 021).

    Gemini validates the current turn's function-call thought signatures, and the parts
    before the switch were signed by the other version, so a Gemini request gets the
    documented bypass value on those parts. Only this request's copies change: its
    contents belong to the stored session events, which are never mutated.
    """
    llm_request.model = stats.switched_to
    if is_anthropic_model(stats.switched_to) or stats.switch_index is None:
        return
    contents = llm_request.contents
    starts = user_turn_indices(contents)
    if not starts:
        return
    for i in range(starts[-1], min(stats.switch_index, len(contents))):
        parts = contents[i].parts or []
        if not any(p.thought_signature for p in parts):
            continue
        contents[i] = contents[i].model_copy(
            update={
                "parts": [
                    p.model_copy(update={"thought_signature": _FOREIGN_SIGNATURE})
                    if p.thought_signature
                    else p
                    for p in parts
                ]
            }
        )


async def generate_with_fallback(
    inner: Callable[[], AsyncGenerator[Any, None]],
    llm_request: LlmRequest,
    policy: RetryPolicy,
    *,
    may_switch: bool = True,
) -> AsyncGenerator[Any, None]:
    """``generate_with_retry``, then at most once per turn the same-class sibling (021).

    Acts only on the chat turn's own model (``llm_request.model == stats.model``), so the
    web-search sub-agent and helper calls are untouched. ``inner`` reads
    ``llm_request.model`` on each call, as ADK's Gemini and Claude do. When the request is
    still rate limited and nothing was yielded (``ModelRateLimited``), the turn switches to
    ``stats.fallback_model``: one ``model_fallback`` record, then this request and every
    later one of the turn go to the sibling. A rate limit on the sibling propagates.

    sc-176: while the switch is still open the turn's model gets a short retry
    (``_PRIMARY_ATTEMPTS`` within ``_PRIMARY_BUDGET_S``); the sibling keeps ``policy``. A
    model whose retries ran out is remembered (``recently_limited``), and a turn whose
    model is remembered switches on its first request, unless the sibling is remembered too
    (sc-268: then probe and sibling share one ``_BOTH_LIMITED_BUDGET_S`` deadline, requests
    included (052 sc-297), and the turn fails fast).

    sc-184: ``may_switch=False`` (the web-search sub-agent, pinned to the turn's model)
    follows a switch the turn already made but never makes one; its own conversation is
    all on the sibling, so no signature guard is needed. While the turn could still switch
    it gets the same short probe, and a spent probe is remembered, so the root's next
    request switches at once (QA PERF-001).
    """
    stats = current_turn.get()
    own = stats is not None and llm_request.model == stats.model
    can_switch = own and bool(stats.fallback_model) and stats.switched_to is None
    both_limited = (
        can_switch and recently_limited(stats.model) and recently_limited(stats.fallback_model)
    )
    deadline = _clock() + _BOTH_LIMITED_BUDGET_S if both_limited else None
    if not may_switch:
        if own and stats.switched_to:
            llm_request.model = stats.switched_to
        try:
            async for response in generate_with_retry(inner, _short(policy) if can_switch else policy):
                yield response
        except ModelRateLimited:
            if own:
                _remember_limited(llm_request.model, stats)
            raise
        return
    if can_switch and recently_limited(stats.model) and not recently_limited(stats.fallback_model):
        _switch(llm_request, stats, "was rate-limited moments ago")
    elif own and stats.switched_to:
        _route_to_sibling(llm_request, stats)
    else:
        try:
            async for response in generate_with_retry(
                inner, _short(policy) if can_switch else policy, deadline=deadline
            ):
                yield response
            return
        except ModelRateLimited:
            if own:
                _remember_limited(llm_request.model, stats)
            if not can_switch:
                raise
            _switch(llm_request, stats, "still rate-limited")
            if deadline is not None and _clock() >= deadline:
                raise  # the probe ended past the shared deadline: "both busy" without the sibling
    try:
        async for response in generate_with_retry(inner, policy, deadline=deadline):
            yield response
    except ModelRateLimited:
        _remember_limited(llm_request.model, stats)
        raise


def _switch(llm_request: LlmRequest, stats: TurnStats, why: str) -> None:
    """Move the turn to its sibling: one ``model_fallback`` record, then route this request."""
    stats.switched_to = stats.fallback_model
    stats.switch_index = len(llm_request.contents)
    logger.warning("model %s %s; switching this turn to %s", stats.model, why, stats.switched_to)
    stats.emit({"type": "model_fallback", "from_model": stats.model, "to_model": stats.switched_to})
    _route_to_sibling(llm_request, stats)


class RetryingGemini(Gemini):
    """ADK ``Gemini`` with the shared retry loop; the SDK's own retries are disabled."""

    policy: RetryPolicy = RetryPolicy()
    # attempts=1 means "no SDK retry": the loop above owns the waiting and the budget.
    retry_options: genai_types.HttpRetryOptions | None = genai_types.HttpRetryOptions(attempts=1)
    # Feature 016: every client this model builds calls the model location, not
    # GOOGLE_CLOUD_LOCATION (ADK applies client_kwargs to each per-event-loop client).
    client_kwargs: dict[str, Any] | None = Field(
        default_factory=adk_client_kwargs, exclude=True, repr=False
    )
    # sc-184: False for a sub-agent's model: it follows the turn's switch, never makes one.
    may_switch: bool = True

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """The retrying call, re-run once when it ends STOP with nothing in it (084 sc-586).

        Gemini sometimes ends a call STOP with no text, no function call and 0 candidate
        tokens, on a first call as well as after a tool round; the turn would end with the
        no-answer message. That final response is held back and the call runs once more; the
        second outcome stands, whatever it is. Counted in ``TurnStats.empty_retries``. Not once
        the turn shows answer text (``TurnStats.answer_shown``, 088a BUG-003): an empty closing
        call after an answer or a chart is a valid end, and a re-run could repeat them.
        """

        def call():
            return generate_with_fallback(
                lambda: super(RetryingGemini, self).generate_content_async(llm_request, stream),
                llm_request,
                self.policy,
                may_switch=self.may_switch,
            )

        watch = _CallWatch()
        async for response in _watch(call(), watch, _empty_stop):
            yield response
        if watch.held is None:
            return
        stats = current_turn.get()
        if stats is not None and stats.answer_shown:
            yield watch.held  # 088a BUG-003: the turn has its answer; an empty closing call ends it
            return
        _count_rerun(stats, "empty")
        logger.warning(
            "gemini call %s ended STOP with no text, no function call and no output tokens; "
            "retrying once",
            llm_request.model,
        )
        async for response in call():
            yield response


# Lets a request set ``thinking.block_binding`` (Claude API and Vertex alike).
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"

# 079 sc-567: the chat's output limit. ADK's default (8,192) let adaptive thinking spend all of
# it on a big analysis, leaving no answer. A non-streamed request (the CLI) gets less: the SDK
# refuses one that could run past 10 minutes (above about 21k tokens).
CLAUDE_MAX_TOKENS = 32_000
CLAUDE_NONSTREAM_MAX_TOKENS = 16_000
# The effort of the one re-run of a call that ended on max_tokens with only thinking.
BUDGET_RETRY_EFFORT = "low"
# 084 sc-580: the longest a streamed Claude chat request may run, thinking included, before it is
# cut off and handled like the thinking-only cut-off (scope:084:claude-call-time). Each request
# gets its own (a rate-limit retry starts a new one); the waits between them are not counted.
CLAUDE_CALL_TIMEOUT_S = 180.0
# 088a BUG-001: the closing line of an answer cut at that bound, so it never passes as complete.
CUT_LINE = "This answer was cut off at the time limit."
# 079 sc-568: the instruction's last section, the only part that changes during a session.
_TIME_OPEN, _TIME_CLOSE = "<CURRENT_TIME>", "</CURRENT_TIME>"


def _split_time_block(system: Any) -> tuple[dict, str, str] | None:
    """ADK's cache-marked system as (head block, time block, rest), or None without one.

    ``system`` is one text block holding the instruction only (tenant text travels in the
    messages), so the split is at the instruction's own last ``<CURRENT_TIME>``.
    """
    if not (isinstance(system, list) and len(system) == 1 and isinstance(system[0], dict)):
        return None
    head, sep, tail = system[0].get("text", "").rpartition(_TIME_OPEN)
    if not sep or not head.strip():
        return None
    time_text, close, rest = tail.partition(_TIME_CLOSE)
    return {**system[0], "text": head}, sep + time_text + close, rest


def _pinned(block: str, stats: TurnStats | None) -> str:
    """The turn's first time block (079): every request of a turn repeats it."""
    if stats is None:
        return block
    if stats.pinned_time is None:
        stats.pinned_time = block
    return stats.pinned_time


def _pin_time_block(system: Any, stats: TurnStats | None) -> Any:
    """Split the cached system block before its time section and pin that section per turn.

    ``system`` is ADK's cache-marked system (one text block with a breakpoint). The prefix
    order is tools, system, messages, so a changed time (every minute) would void the cached
    history behind it. The stable head keeps the breakpoint; the time block follows it,
    repeated from the turn's first request, so all requests of a turn share one prefix.
    Anything after the time block (the round cap's wrap-up) rides along uncached.
    """
    split = _split_time_block(system)
    if split is None:
        return system
    head, block, rest = split
    return [head, {"type": "text", "text": _pinned(block, stats) + rest}]


# Claude rejects a cache breakpoint on a reasoning block (as in ADK's anthropic_llm).
_UNCACHEABLE = frozenset({"thinking", "redacted_thinking"})


def _anthropic_turn_starts(messages: list[dict]) -> list[int]:
    """``user_turn_indices`` over Anthropic messages: user, a text block, no tool result."""
    starts = []
    for i, message in enumerate(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, list):
            continue
        types = {block.get("type") for block in content if isinstance(block, dict)}
        if "text" in types and "tool_result" not in types:
            starts.append(i)
    return starts


def _turn_layout(request: dict[str, Any], stats: TurnStats) -> None:
    """087 sc-581: lay a chat turn's request out so later turns read the history from the cache.

    The prefix order is tools, system, messages. 079 kept the turn's time block in the system,
    so each turn's first request re-wrote the whole history. Here the system is the instruction
    head alone (plus the round cap's wrap-up, uncached), shared by every tenant; the pinned time
    block becomes the first block of the turn's user message, before its preamble. A fourth
    breakpoint marks the end of the turns older than ``keep_turns()``: ``context_trim`` has
    stubbed their results and they no longer change, so the next turn reads them from the cache
    and writes only the kept turns and its new message (board measure:087); from the turn after,
    the previous turn's boundary is marked as well (088a PERF-001, see below). Placement reads
    only roles and block types, never text; at most four breakpoints (tools or the previous
    boundary, head, history, end).
    """
    split = _split_time_block(request.get("system"))
    messages = request.get("messages")
    starts = _anthropic_turn_starts(messages) if isinstance(messages, list) else []
    if split is None or not starts:
        request["system"] = _pin_time_block(request.get("system"), stats)
        return
    head, block, rest = split
    request["system"] = [head, {"type": "text", "text": rest}] if rest.strip() else [head]
    turn = messages[starts[-1]]
    turn["content"] = [{"type": "text", "text": _pinned(block, stats)}, *turn["content"]]
    keep = keep_turns()
    if len(starts) <= keep:
        return
    _mark_history_end(messages[: starts[-keep]], head["cache_control"])
    # 088a PERF-001: Claude looks back only ~20 blocks from a breakpoint, and a heavy turn (rounds
    # of parallel calls) moves the boundary further. So the previous turn start's boundary is
    # marked too: the exact entry it wrote, read with no look-back. The head entry covers the
    # tools, so their breakpoint goes, keeping four (head, previous boundary, boundary, end).
    if len(starts) > keep + 1 and _mark_history_end(messages[: starts[-keep - 1]], head["cache_control"]):
        tools = request.get("tools")
        if isinstance(tools, list) and tools and isinstance(tools[-1], dict):
            tools[-1].pop("cache_control", None)


def _mark_history_end(messages: list[dict], cache_control: Any) -> bool:
    """Put ``cache_control`` on the last cacheable block of ``messages``; False without one."""
    for message in reversed(messages):
        content = message.get("content")
        cacheable = [
            b for b in content if isinstance(b, dict) and b.get("type") not in _UNCACHEABLE
        ] if isinstance(content, list) else []
        if cacheable:
            cacheable[-1]["cache_control"] = cache_control
            return True
    return False


# --- one re-run per model call (079 sc-567, 084 sc-580 / sc-586) -------------------------------


class ModelCallTimedOut(Exception):
    """A streamed model request ran past its time bound and was cut off (084 sc-580)."""


async def _within(gen: AsyncGenerator[Any, None], seconds: float) -> AsyncGenerator[Any, None]:
    """Pass ``gen`` on until it has taken ``seconds`` on :data:`_clock`, then cut it off.

    Only the time spent waiting on ``gen`` counts, not the time the consumer holds each chunk
    (088a PERF-007). The bound holds while waiting for the next chunk (``asyncio.timeout``, in
    this task, so a stream that sends nothing more is cut too) and is checked before each wait,
    so a stream that never yields to the loop is cut as well. A chunk that has arrived is always
    passed on, even past the bound (088a BUG-007: it can be the final response with the tool
    calls). ``gen`` is always closed, so a cut-off stream releases its connection. Raises
    :class:`ModelCallTimedOut` on a cut.
    """
    spent = 0.0
    try:
        while True:
            if spent >= seconds:
                raise ModelCallTimedOut(f"model request cut off after {seconds:g}s")
            started = _clock()
            bound = asyncio.timeout(seconds - spent)
            try:
                async with bound:
                    item = await anext(gen)
            except StopAsyncIteration:
                return
            except TimeoutError:
                if bound.expired():
                    raise ModelCallTimedOut(f"model request cut off after {seconds:g}s") from None
                raise
            spent += _clock() - started
            yield item
    finally:
        await gen.aclose()


@dataclass
class _CallWatch:
    """What one model call did, as :func:`_watch` saw it."""

    held: LlmResponse | None = None  # the final response held back for a re-run
    text: list[str] = field(default_factory=list)  # answer text streamed so far
    final: bool = False  # a final (non-partial) response went out
    timed_out: bool = False


async def _watch(
    responses: AsyncGenerator[LlmResponse, None],
    watch: _CallWatch,
    hold: Callable[[LlmResponse], bool],
) -> AsyncGenerator[LlmResponse, None]:
    """Pass a call's responses on, holding back the final one ``hold`` picks, noting the answer
    text streamed and stopping quietly on a time cut-off (``watch.timed_out``)."""
    try:
        async for response in responses:
            if hold(response):
                watch.held = response
                continue
            if response.partial:
                parts = response.content.parts if response.content else None
                watch.text.extend(p.text for p in parts or [] if p.text and not p.thought)
            else:
                watch.final = True
            yield response
    except ModelCallTimedOut:
        watch.timed_out = True


def _count_rerun(stats: TurnStats | None, kind: str) -> None:
    """A re-run is one more model request, so one more round toward ``round_cap`` (sc-580 SEC-001)."""
    if stats is None:
        return
    stats.model_requests += 1
    if kind == "empty":
        stats.empty_retries += 1
    else:
        stats.budget_retries += 1


def _has_text(text: list[str]) -> bool:
    """Answer text streamed: whitespace alone is none (088a BUG-008)."""
    return bool("".join(text).strip())


def _cut_responses(text: list[str], model: str | None) -> list[LlmResponse]:
    """The end of a call cut off at its time bound.

    Without answer text, an empty final response. With it (scope:084:time-cut-after-text), the
    :data:`CUT_LINE` streamed once as the answer's closing paragraph, then a final response with
    the text and that line, so the turn and its history keep what the player saw and never pass
    a cut answer as complete (088a BUG-001). Counted in ``TurnStats.time_cuts``.
    """
    if not _has_text(text):
        return [LlmResponse(finish_reason=genai_types.FinishReason.MAX_TOKENS, partial=False)]
    stats = current_turn.get()
    if stats is not None:
        stats.time_cuts += 1
    logger.warning("claude call %s cut off after %gs with answer text; ending it there", model, CLAUDE_CALL_TIMEOUT_S)
    line = "\n\n" + CUT_LINE

    def response(value: str, partial: bool) -> LlmResponse:
        return LlmResponse(
            content=genai_types.Content(role="model", parts=[genai_types.Part(text=value)]),
            finish_reason=None if partial else genai_types.FinishReason.MAX_TOKENS,
            partial=partial,
        )

    return [response(line, True), response("".join(text) + line, False)]


def _empty_stop(response: LlmResponse) -> bool:
    """A final response that ended STOP with no answer text, no tool call and no output tokens."""
    if response.partial or response.finish_reason != genai_types.FinishReason.STOP:
        return False
    parts = response.content.parts if response.content else None
    if any((p.text and not p.thought) or p.function_call for p in parts or []):
        return False
    return not getattr(response.usage_metadata, "candidates_token_count", None)


def _thinking_only_cutoff(response: LlmResponse) -> bool:
    """A final response cut off at max_tokens with no answer text and no tool call."""
    if response.partial or response.finish_reason != genai_types.FinishReason.MAX_TOKENS:
        return False
    parts = response.content.parts if response.content else None
    return not any((p.text and not p.thought) or p.function_call for p in parts or [])


try:  # the Anthropic provider is optional at runtime
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.models.anthropic_llm import AnthropicGenerateContentConfig
    from google.adk.models.anthropic_llm import Claude as _Claude
except Exception:  # noqa: BLE001 - missing optional dependency
    _Claude = None  # type: ignore[assignment]

if _Claude is not None:
    # ADK's Claude marks tools, system and the conversation's last block as cache breakpoints
    # when a request carries a cache config; the default lifetime gives the 5-minute cache.
    _CLAUDE_CACHE = ContextCacheConfig()

    def _with_effort(config: genai_types.GenerateContentConfig | None, effort: str):
        """``config`` as ADK's Anthropic config with ``effort`` (its only effort switch)."""
        fields = {}
        if config is not None:
            fields = {
                k: v for k in type(config).model_fields if (v := getattr(config, k)) is not None
            }
        return AnthropicGenerateContentConfig(**{**fields, "effort": effort})

    class RetryingClaude(_Claude):
        """ADK ``Claude`` with the shared retry loop, on the active provider (feature 032).

        Its client comes from the provider layer: the Anthropic API under ``anthropic``, Vertex
        at the model location under ``vertex`` (feature 016: ADK's own would read
        GOOGLE_CLOUD_LOCATION). A preset ``client`` is still honoured, as in ADK. The Anthropic
        SDK's built-in retries are off so the waits never nest.
        """

        policy: RetryPolicy = RetryPolicy()
        max_tokens: int = CLAUDE_MAX_TOKENS

        @cached_property
        def _anthropic_client(self):  # type: ignore[override]
            return (self.client or async_anthropic_client()).with_options(max_retries=0)

        def _build_anthropic_kwargs(
            self, llm_request: LlmRequest, *args: Any, **kwargs: Any
        ) -> dict[str, Any]:
            """ADK's request with prompt caching, plus ``drop_block`` for stale thinking blocks.

            079 sc-568: cache breakpoints on the tools, the instruction's stable head and the
            conversation's last block (ADK places them given a cache config), with the time
            block pinned per turn, so each later request of a turn reads the earlier ones'
            prompt from the cache. In a chat turn (087) the time block moves into the turn's
            user message and a fourth breakpoint ends the stubbed history (``_turn_layout``);
            without a turn (CLI) it follows the head (``_pin_time_block``). Usage comes back through ADK with the
            cache reads and writes folded into ``prompt_token_count`` and the reads in
            ``cached_content_token_count``.

            A replayed thinking block is valid only while everything before it is unchanged, and
            every request edits that history (old tool results stubbed, the per-turn preamble,
            the instruction's timestamp). Without this the API rejects such requests with a 400
            for newer accounts; with it, it drops the stale blocks and answers (feature 032).
            """
            if llm_request.cache_config is None:
                llm_request.cache_config = _CLAUDE_CACHE
            request = super()._build_anthropic_kwargs(llm_request, *args, **kwargs)
            stats = current_turn.get()
            if stats is None:
                request["system"] = _pin_time_block(request.get("system"), None)
            else:
                _turn_layout(request, stats)
            thinking = request.get("thinking")
            if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
                request["thinking"] = {
                    **thinking,
                    "block_binding": {"prefix_mismatch_behavior": "drop_block"},
                }
                request["extra_headers"] = {"anthropic-beta": THINKING_BINDING_BETA}
            return request

        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            """The retrying call, re-run once at low effort when thinking used the whole budget.

            079 sc-567: a final response that stopped on max_tokens with only thoughts would
            end the turn with no answer. It is held back (its thought partials have streamed,
            but no answer text) and the call runs once more at ``BUDGET_RETRY_EFFORT``; that
            second outcome stands, whatever it is. Counted in ``TurnStats.budget_retries``.

            084 sc-580: each streamed request runs at most ``CLAUDE_CALL_TIMEOUT_S`` (thinking
            included). A request cut off before any answer text is handled like the budget
            cut-off; one cut off after answer text began ends with that text and :data:`CUT_LINE`
            (a re-run would repeat it; 088a BUG-001), as does a cut-off re-run.
            """
            if not stream:
                llm_request.config = llm_request.config or genai_types.GenerateContentConfig()
                if llm_request.config.max_output_tokens is None:
                    llm_request.config.max_output_tokens = CLAUDE_NONSTREAM_MAX_TOKENS

            def request():
                responses = super(RetryingClaude, self).generate_content_async(llm_request, stream)
                return _within(responses, CLAUDE_CALL_TIMEOUT_S) if stream else responses

            def call():
                return generate_with_fallback(request, llm_request, self.policy)

            watch = _CallWatch()
            async for response in _watch(call(), watch, _thinking_only_cutoff):
                yield response
            if watch.timed_out and (_has_text(watch.text) or watch.final):
                if not watch.final:
                    for response in _cut_responses(watch.text, llm_request.model):
                        yield response
                return
            if watch.held is None and not watch.timed_out:
                return
            _count_rerun(current_turn.get(), "budget")
            if watch.timed_out:
                logger.warning(
                    "claude call %s ran past %gs with no answer; retrying once at effort=%s",
                    llm_request.model,
                    CLAUDE_CALL_TIMEOUT_S,
                    BUDGET_RETRY_EFFORT,
                )
            else:
                logger.warning(
                    "claude call %s ended on max_tokens with no answer (thoughts_tokens=%s); "
                    "retrying once at effort=%s",
                    llm_request.model,
                    getattr(watch.held.usage_metadata, "thoughts_token_count", None),
                    BUDGET_RETRY_EFFORT,
                )
            llm_request.config = _with_effort(llm_request.config, BUDGET_RETRY_EFFORT)
            rerun = _CallWatch()
            async for response in _watch(call(), rerun, lambda _response: False):
                yield response
            if rerun.timed_out and not rerun.final:
                for response in _cut_responses(rerun.text, llm_request.model):
                    yield response

else:  # pragma: no cover - only without the anthropic extra
    RetryingClaude = None  # type: ignore[assignment,misc]


# --- per-turn request counting and the lookup-round cap (US2) ----------------------------


def is_anthropic_model(model: str | None) -> bool:
    """Claude ids (on either provider) vs Gemini ids — one definition for the package."""
    return "claude" in (model or "").lower()


WRAP_UP_INSTRUCTION = (
    "LOOKUP BUDGET SPENT: this turn has used its allowance of tool rounds. Do not call "
    "any more tools. Answer now with the evidence already gathered, and state plainly "
    "which parts of the question you did not get to investigate."
)


def inject_preamble(llm_request: LlmRequest, preamble: str) -> None:
    """Prepend ``preamble`` to the turn's user message in this request only (PERF-004).

    The turn's user message is the last user content with text and no function response
    (tool results also travel as user contents). It is replaced by a *new* Content with
    the preamble as its first part; the original belongs to the stored session events and
    is never mutated, so the preamble reaches the model without entering the history.
    """
    contents = llm_request.contents
    starts = user_turn_indices(contents)
    if not starts:
        return
    i = starts[-1]
    contents[i] = genai_types.Content(
        role="user", parts=[genai_types.Part(text=f"{preamble}\n\n"), *(contents[i].parts or [])]
    )


def make_before_model_callback(policy: RetryPolicy):
    """ADK ``before_model_callback`` that counts model requests and enforces the round cap.

    Fires once per model request. With a turn installed in ``current_turn`` it increments
    ``model_requests`` (FR-013); once the turn's lookup rounds reach ``policy.round_cap``
    it appends ``WRAP_UP_INSTRUCTION`` to the request's system instruction (FR-011) and,
    for Gemini, disables function calling for that request as a hard stop. The Anthropic
    adapter does not map ``tool_config``, so Claude relies on the instruction. Without a
    turn (CLI, tests) only the trimming below applies. Always returns ``None`` so the
    request proceeds.

    On every request it first replaces large tool results from older turns with compact
    stubs (``context_trim``, PERF-004), then injects the turn's preamble.
    """

    def before_model(callback_context, llm_request: LlmRequest):  # noqa: ARG001 - ADK shape
        trimmed = trim_old_tool_results(llm_request)
        stats = current_turn.get()
        if stats is None:
            return None
        stats.model_requests += 1
        stats.trimmed_results += trimmed
        if stats.preamble:
            inject_preamble(llm_request, stats.preamble)
        if not stats.cap_reached(policy):
            return None
        logger.info(
            "turn round cap reached (rounds=%d cap=%d); asking the model to wrap up",
            stats.tool_rounds,
            policy.round_cap,
        )
        llm_request.append_instructions([WRAP_UP_INSTRUCTION])
        if not is_anthropic_model(llm_request.model):
            llm_request.config.tool_config = genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(mode="NONE")
            )
        return None

    return before_model
