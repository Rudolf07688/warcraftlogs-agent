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
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import random
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types

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
    outcome: str | None = None  # answered | rate_limited | error | abandoned
    # PERF-004: per-turn standing context (KNOWN PLAYER CONTEXT), injected into each model
    # request by the before-model callback so it is never stored in the session history.
    preamble: str | None = None
    # PERF-004: prompt size of the turn's model requests, for the turn stats log line.
    last_prompt_tokens: int | None = None
    max_prompt_tokens: int | None = None

    def record_prompt_tokens(self, count: int | None) -> None:
        if count is None:
            return
        self.last_prompt_tokens = count
        self.max_prompt_tokens = max(self.max_prompt_tokens or 0, count)

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
) -> AsyncGenerator[Any, None]:
    """Drive ``inner()`` (a fresh model-call generator per attempt) with rate-limit retries.

    Retries only when the failure is a rate limit (FR-002), nothing has been yielded yet
    (a mid-stream retry would duplicate streamed text), attempts remain, and the next
    delay still fits the wait budget. Each retry is announced on the current turn as a
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
            if waited + delay > policy.budget_s:
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


class RetryingGemini(Gemini):
    """ADK ``Gemini`` with the shared retry loop; the SDK's own retries are disabled."""

    policy: RetryPolicy = RetryPolicy()
    # attempts=1 means "no SDK retry": the loop above owns the waiting and the budget.
    retry_options: genai_types.HttpRetryOptions | None = genai_types.HttpRetryOptions(attempts=1)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        async for response in generate_with_retry(
            lambda: super(RetryingGemini, self).generate_content_async(llm_request, stream),
            self.policy,
        ):
            yield response


try:  # the Anthropic provider is optional at runtime
    from google.adk.models.anthropic_llm import Claude as _Claude
except Exception:  # noqa: BLE001 - missing optional dependency
    _Claude = None  # type: ignore[assignment]

if _Claude is not None:

    class RetryingClaude(_Claude):
        """ADK ``Claude`` (Anthropic on Vertex) with the shared retry loop.

        Reuses ADK's project/region resolution for the client and only turns off the
        Anthropic SDK's built-in retries so the waits never nest.
        """

        policy: RetryPolicy = RetryPolicy()

        @cached_property
        def _anthropic_client(self):  # type: ignore[override]
            return super()._anthropic_client.with_options(max_retries=0)

        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            async for response in generate_with_retry(
                lambda: super(RetryingClaude, self).generate_content_async(llm_request, stream),
                self.policy,
            ):
                yield response

else:  # pragma: no cover - only without the anthropic extra
    RetryingClaude = None  # type: ignore[assignment,misc]


# --- per-turn request counting and the lookup-round cap (US2) ----------------------------


def is_anthropic_model(model: str | None) -> bool:
    """Anthropic-on-Vertex (Claude) ids vs Gemini ids — one definition for the package."""
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
    for i in range(len(contents) - 1, -1, -1):
        content = contents[i]
        parts = content.parts or []
        if content.role != "user" or any(getattr(p, "function_response", None) for p in parts):
            continue
        if not any(getattr(p, "text", None) for p in parts):
            continue
        contents[i] = genai_types.Content(
            role="user", parts=[genai_types.Part(text=f"{preamble}\n\n"), *parts]
        )
        return


def make_before_model_callback(policy: RetryPolicy):
    """ADK ``before_model_callback`` that counts model requests and enforces the round cap.

    Fires once per model request. With a turn installed in ``current_turn`` it increments
    ``model_requests`` (FR-013); once the turn's lookup rounds reach ``policy.round_cap``
    it appends ``WRAP_UP_INSTRUCTION`` to the request's system instruction (FR-011) and,
    for Gemini, disables function calling for that request as a hard stop. The Anthropic
    adapter does not map ``tool_config``, so Claude relies on the instruction. Without a
    turn (CLI, tests) it is a no-op. Always returns ``None`` so the request proceeds.
    """

    def before_model(callback_context, llm_request: LlmRequest):  # noqa: ARG001 - ADK shape
        stats = current_turn.get()
        if stats is None:
            return None
        stats.model_requests += 1
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
