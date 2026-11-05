"""Application metrics of the API process (feature 056, spec §6.4): one definition each.

On the OTel metrics API only: without a meter provider (telemetry off, the test suite) every
instrument is a no-op. Attribute values are bounded enums; the keys must be in
``setup.METRIC_ATTRIBUTES`` or the View drops them. The WCL cache counter lives in
``wcl_agent/cache/cache.py``, because that package never imports the backend.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from opentelemetry import metrics

_meter = metrics.get_meter("wcl-agent.app")

_retrieval_duration = _meter.create_histogram(
    "app.rag.retrieval.duration", unit="s", description="Knowledge-base search latency, embedding included."
)
_retrieved_chunks = _meter.create_histogram(
    "app.rag.retrieved_chunks", unit="{chunk}", description="Hits a knowledge-base search returned."
)
_top_score = _meter.create_histogram(
    "app.rag.top_score", unit="1", description="Fused score of a knowledge-base search's best hit."
)
_empty_results = _meter.create_counter(
    "app.rag.empty_results", unit="{search}", description="Knowledge-base searches that returned nothing."
)
_stream_ttft = _meter.create_histogram(
    "app.llm.stream.ttft", unit="s", description="Seconds from the start of a turn to its first answer text."
)
# Feature 059 (sc-462, spec §6.4).
_finish_reasons = _meter.create_counter(
    "app.llm.finish_reasons", unit="{response}", description="Model responses by the reason they ended."
)
_turns_per_conversation = _meter.create_histogram(
    "app.agent.turns_per_conversation", unit="{turn}", description="Turns a conversation has had, at the end of each chat turn."
)
_embedding_duration = _meter.create_histogram(
    "app.embedding.duration", unit="s", description="Latency of one embedding request, retries included."
)
_embedding_batch_size = _meter.create_histogram(
    "app.embedding.batch_size", unit="{text}", description="Texts in one embedding request."
)
# google-genai's FinishReason names, lower case. The enum makes up a member for any value it
# doesn't know, so the label comes from this fixed set and everything else is "other".
FINISH_REASONS = frozenset(
    {
        "stop",
        "max_tokens",
        "safety",
        "recitation",
        "language",
        "blocklist",
        "prohibited_content",
        "spii",
        "malformed_function_call",
        "image_safety",
        "unexpected_tool_call",
        "too_many_tool_calls",
        "other",
    }
)


def record_retrieval(index: str, strategy: str, seconds: float, scores: Sequence[float]) -> None:
    """One finished knowledge-base search: ``index`` is the kind filter or ``all``, ``strategy``
    the result mode, ``scores`` its hits' scores."""
    labels = {"app.rag.index": index}
    _retrieval_duration.record(seconds, {**labels, "app.rag.strategy": strategy})
    _retrieved_chunks.record(len(scores), labels)
    if scores:
        _top_score.record(max(scores), labels)
    else:
        _empty_results.add(1, labels)


def record_ttft(model: str, agent: str, seconds: float) -> None:
    _stream_ttft.record(seconds, {"gen_ai.request.model": model, "gen_ai.agent.name": agent})


def record_finish_reason(model: str, reason: object) -> None:
    """One finished model response; ``None`` and ``FINISH_REASON_UNSPECIFIED`` aren't counted
    (ADK doesn't report them either)."""
    name = reason.name if isinstance(reason, Enum) else reason
    if not isinstance(name, str) or name.upper() in ("", "FINISH_REASON_UNSPECIFIED"):
        return
    label = name.lower() if name.lower() in FINISH_REASONS else "other"
    _finish_reasons.add(1, {"gen_ai.request.model": model, "app.llm.finish_reason": label})


def record_conversation_depth(agent: str, turns: int) -> None:
    _turns_per_conversation.record(turns, {"gen_ai.agent.name": agent})


def record_embedding(model: str, task: str, texts: int, seconds: float, error: BaseException | None = None) -> None:
    """One embedding request: ``task`` is ``document`` (indexing) or ``query`` (search). A failed
    one carries ``error.type``, its exception's class name (live check #78: D8 shows an outage)."""
    labels = {"gen_ai.request.model": model, "app.embedding.task": task}
    if error is not None:
        labels["error.type"] = type(error).__name__
    _embedding_duration.record(seconds, labels)
    _embedding_batch_size.record(texts, labels)
