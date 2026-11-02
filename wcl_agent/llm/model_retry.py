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
from dataclasses import dataclass, replace
from functools import cached_property
from typing import Any

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types
from pydantic import Field

from .context_trim import trim_old_tool_results, user_turn_indices
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

    def record_prompt_tokens(self, count: int | None, cached: int | None = None) -> None:
        if count is None:
            return
        self.last_prompt_tokens = count
        self.max_prompt_tokens = max(self.max_prompt_tokens or 0, count)
        self.last_cached_tokens = cached

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
        async for response in generate_with_fallback(
            lambda: super(RetryingGemini, self).generate_content_async(llm_request, stream),
            llm_request,
            self.policy,
            may_switch=self.may_switch,
        ):
            yield response


# Lets a request set ``thinking.block_binding`` (Claude API and Vertex alike).
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"

try:  # the Anthropic provider is optional at runtime
    from google.adk.models.anthropic_llm import Claude as _Claude
except Exception:  # noqa: BLE001 - missing optional dependency
    _Claude = None  # type: ignore[assignment]

if _Claude is not None:

    class RetryingClaude(_Claude):
        """ADK ``Claude`` with the shared retry loop, on the active provider (feature 032).

        Its client comes from the provider layer: the Anthropic API under ``anthropic``, Vertex
        at the model location under ``vertex`` (feature 016: ADK's own would read
        GOOGLE_CLOUD_LOCATION). A preset ``client`` is still honoured, as in ADK. The Anthropic
        SDK's built-in retries are off so the waits never nest.
        """

        policy: RetryPolicy = RetryPolicy()

        @cached_property
        def _anthropic_client(self):  # type: ignore[override]
            return (self.client or async_anthropic_client()).with_options(max_retries=0)

        def _build_anthropic_kwargs(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            """ADK's request, plus ``drop_block`` for thinking blocks the history no longer matches.

            A replayed thinking block is valid only while everything before it is unchanged, and
            every request edits that history (old tool results stubbed, the per-turn preamble,
            the instruction's timestamp). Without this the API rejects such requests with a 400
            for newer accounts; with it, it drops the stale blocks and answers (feature 032).
            """
            request = super()._build_anthropic_kwargs(*args, **kwargs)
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
            async for response in generate_with_fallback(
                lambda: super(RetryingClaude, self).generate_content_async(llm_request, stream),
                llm_request,
                self.policy,
            ):
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
