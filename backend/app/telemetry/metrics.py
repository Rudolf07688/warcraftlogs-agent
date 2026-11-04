"""Application metrics of the API process (feature 056, spec §6.4): one definition each.

On the OTel metrics API only: without a meter provider (telemetry off, the test suite) every
instrument is a no-op. Attribute values are bounded enums; the keys must be in
``setup.METRIC_ATTRIBUTES`` or the View drops them. The WCL cache counter lives in
``wcl_agent/cache/cache.py``, because that package never imports the backend.
"""

from __future__ import annotations

from collections.abc import Sequence

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
