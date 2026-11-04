"""Feature 056 (sc-411, sc-412): ADK and app metrics through the production metric pipeline.

The global meter provider can be set once per process. ADK and the app create their
instruments on the API's proxy meter at import, so one session provider serves every test
here: ``setup.meter_provider`` (the production View and its attribute allowlist) around an
in-memory reader with delta temporality, drained at the start of each test so a test reads
only what it recorded.
"""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import Counter, Histogram, UpDownCounter
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader

from backend.app import agent_runner
from backend.app.kb import search as kb_search
from backend.app.telemetry import policy, setup
from backend.app.telemetry.config import TelemetryConfig
from backend.tests.test_llm_provider_agent import (  # noqa: F401 - fixture
    CLAUDE,
    SENTINEL_KEY,
    ScriptedApi,
    _message_start,
    _sse,
    text_answer,
    use_provider,
)
from backend.tests.test_telemetry_support import scripted_agent, tool_call_with
from wcl_agent.cache import cache
from wcl_agent.cache.cache import CacheFamily, Outcome
from wcl_agent.llm.model_retry import TurnStats, current_turn

ROOT = Path(__file__).resolve().parents[2]
# Values that must never become a label: ids, session ids, query text.
SESSION = f"session-{uuid.uuid4()}"
QUERY = "QUERY-SENTINEL-056 best trinkets"

_delta = AggregationTemporality.DELTA
_reader: InMemoryMetricReader | None = None


def _session_reader() -> InMemoryMetricReader:
    global _reader
    if _reader is None:
        _reader = InMemoryMetricReader(
            preferred_temporality={Counter: _delta, Histogram: _delta, UpDownCounter: _delta}
        )
        res = setup.resource(TelemetryConfig(enabled=True, environment="ci", version="test"))
        metrics.set_meter_provider(setup.meter_provider(res, _reader, shutdown_on_exit=False))
    return _reader


class Points:
    def __init__(self, reader: InMemoryMetricReader) -> None:
        self.by_name: dict[str, list] = {}
        data = reader.get_metrics_data()
        for rm in data.resource_metrics if data else ():
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    self.by_name.setdefault(metric.name, []).extend(metric.data.data_points)

    def __getitem__(self, name: str) -> list:
        return self.by_name.get(name, [])

    def labels(self, name: str) -> list[dict]:
        return [dict(p.attributes) for p in self[name]]

    def all_labels(self) -> list[dict]:
        return [dict(p.attributes) for points in self.by_name.values() for p in points]


@pytest.fixture
def metric_reader():
    reader = _session_reader()
    reader.get_metrics_data()  # drop what earlier tests recorded

    def read() -> Points:
        return Points(reader)

    return read


def assert_clean(labels: list[dict]) -> None:
    """Every attribute allowlisted, and no id or text from the request anywhere."""
    for attrs in labels:
        assert set(attrs) <= setup.METRIC_ATTRIBUTES, attrs
    text = str(labels)
    assert SESSION not in text and QUERY not in text
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text)


# --- sc-411: ADK core metrics -------------------------------------------------------------


async def report_title(code: str) -> dict:
    """The title of a Warcraft Logs report."""
    return {"status": "success", "title": "Raid Night"}


async def test_one_turn_exports_the_adk_core_metrics_by_model_and_agent(metric_reader, monkeypatch, use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(
        monkeypatch,
        ScriptedApi(tool_call_with("report_title", {"code": "a1B2c3"}), text_answer("It was Raid Night.")),
        report_title,
    )

    records = [r async for r in agent_runner.stream_response(CLAUDE, SESSION, QUERY)]
    assert "".join(r.get("text", "") for r in records) == "It was Raid Night."

    points = metric_reader()
    tokens = points.labels("gen_ai.client.token.usage")
    assert {(t["gen_ai.request.model"], t["gen_ai.token.type"]) for t in tokens} == {
        (CLAUDE, "input"),
        (CLAUDE, "output"),
    }
    agent = tokens[0]["gen_ai.agent.name"]
    for name in ("gen_ai.invoke_agent.duration", "gen_ai.invoke_agent.inference_calls", "gen_ai.invoke_agent.tool_calls"):
        assert {"gen_ai.agent.name": agent} in points.labels(name), name
    [inference] = [p for p in points["gen_ai.invoke_agent.inference_calls"] if p.attributes["gen_ai.agent.name"] == agent]
    [tool_calls] = [p for p in points["gen_ai.invoke_agent.tool_calls"] if p.attributes["gen_ai.agent.name"] == agent]
    assert (inference.sum, tool_calls.sum) == (2, 1)
    assert_clean(points.all_labels())


def test_a_forbidden_attribute_is_dropped_before_export(metric_reader):
    meter = metrics.get_meter("test-056")
    meter.create_counter("test.forbidden").add(
        1, {"gen_ai.agent.name": "a", "session.id": SESSION, "gen_ai.conversation.id": SESSION, "user.id": "u"}
    )

    assert metric_reader().labels("test.forbidden") == [{"gen_ai.agent.name": "a"}]


def test_no_id_or_session_attribute_is_ever_allowlisted():
    """contract:session-id and spec §9.3."""
    banned = {"session.id", "prompt.id", "user.id", "user.email", "gen_ai.conversation.id", "request_id"}
    assert not banned & setup.METRIC_ATTRIBUTES
    assert not [key for key in setup.METRIC_ATTRIBUTES if key.endswith((".id", "_id"))]


def test_versions_are_pinned_and_the_semconv_opt_in_is_set():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    pins = dict(d.split("==") for d in deps if "==" in d)
    for package in ("google-adk", "opentelemetry-exporter-otlp-proto-http"):
        assert pins[package] == importlib.metadata.version(package), package
    for allowed in (True, False):
        assert policy.content_env(allowed, {})["OTEL_SEMCONV_STABILITY_OPT_IN"] == "gen_ai_latest_experimental"


# --- sc-412: app metrics ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "result"),
    [
        (Outcome.HIT, "hit"),
        (Outcome.NEG_HIT, "hit"),
        (Outcome.MISS, "miss"),
        (Outcome.LOCK_TIMEOUT, "miss"),
        (Outcome.REDIS_ERROR, "miss"),
        (Outcome.ERROR, "error"),
    ],
)
def test_each_cache_outcome_counts_under_its_family_and_result(metric_reader, outcome, result):
    cache._record(CacheFamily.REPORT_SUMMARY, outcome)

    [point] = metric_reader()["app.cache.requests"]
    assert (dict(point.attributes), point.value) == (
        {"app.cache.name": "report_summary", "app.cache.result": result},
        1,
    )


async def test_cache_lookups_count_a_miss_then_a_hit(metric_reader, fake_redis):
    code = f"r{uuid.uuid4().hex[:12]}"

    async def load():
        return None

    for _ in range(2):
        await cache.get_or_load(CacheFamily.REPORT_SUMMARY, cache.keys.report_summary(code), cache.BaseModel, load)

    labels = metric_reader().labels("app.cache.requests")
    assert sorted(label["app.cache.result"] for label in labels) == ["hit", "miss"]
    assert_clean(labels)


def _hit(score: float) -> kb_search.Candidate:
    return kb_search.Candidate(f"c{score}", "guide", "text", (score,), {"section": "s"})


def _request(kind: kb_search.Kind | None = None) -> kb_search.SearchRequest:
    return kb_search.SearchRequest(
        queries=(QUERY,), filters=kb_search.SearchFilters(kind=kind), hard=frozenset(), k=8, tenant_id=uuid.uuid4()
    )


async def test_a_search_records_latency_chunks_and_top_score(metric_reader):
    async def runner(query, vector, filters, tenant_id, legs):
        return [_hit(1.0), _hit(2.0), _hit(3.0)]

    result = await kb_search.search(_request("guide"), embedder=None, runner=runner)

    points = metric_reader()
    [duration] = points["app.rag.retrieval.duration"]
    assert dict(duration.attributes) == {"app.rag.index": "guide", "app.rag.strategy": "keyword_only"}
    [chunks] = points["app.rag.retrieved_chunks"]
    assert (dict(chunks.attributes), chunks.sum) == ({"app.rag.index": "guide"}, 3)
    [top] = points["app.rag.top_score"]
    assert top.max == max(hit.score for hit in result.hits)
    assert points["app.rag.empty_results"] == []
    assert_clean(points.all_labels())


async def test_an_empty_search_counts_as_empty(metric_reader):
    async def runner(query, vector, filters, tenant_id, legs):
        return []

    await kb_search.search(_request(), embedder=None, runner=runner)

    points = metric_reader()
    [empty] = points["app.rag.empty_results"]
    assert (dict(empty.attributes), empty.value) == ({"app.rag.index": "all"}, 1)
    assert points["app.rag.top_score"] == []


async def test_a_streamed_turn_records_its_time_to_first_token_once(metric_reader, monkeypatch, use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(
        monkeypatch,
        ScriptedApi(tool_call_with("report_title", {"code": "a1B2c3"}), text_answer("It was Raid Night.")),
        report_title,
    )

    records = [r async for r in agent_runner.stream_response(CLAUDE, SESSION, QUERY)]
    assert any(r["type"] == "token" for r in records)

    [point] = metric_reader()["app.llm.stream.ttft"]
    assert point.count == 1
    assert point.attributes["gen_ai.request.model"] == CLAUDE
    assert point.attributes["gen_ai.agent.name"]
    assert_clean([dict(point.attributes)])


async def test_a_turn_without_answer_text_records_no_time_to_first_token(metric_reader, monkeypatch, use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(monkeypatch, ScriptedApi(text_answer("   ")), report_title)

    [r async for r in agent_runner.stream_response(CLAUDE, SESSION, QUERY, user_id="workspace-user")]

    assert metric_reader()["app.llm.stream.ttft"] == []



def _text_then_tool(text: str, name: str) -> bytes:
    """A scripted Claude reply: an interim line, then a call to ``name``."""
    return _sse(
        _message_start(CLAUDE),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": name, "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"code": "a1B2c3"}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    )


async def test_text_in_two_rounds_is_timed_once(metric_reader, monkeypatch, use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(
        monkeypatch,
        ScriptedApi(_text_then_tool("Let me look.", "report_title"), text_answer("It was Raid Night.")),
        report_title,
    )

    records = [r async for r in agent_runner.stream_response(CLAUDE, SESSION, QUERY)]
    assert [r["type"] for r in records].count("tool_end") == 1

    [point] = metric_reader()["app.llm.stream.ttft"]
    assert point.count == 1


class _FinalOnly:
    """A runner whose model answers in one final, non-streamed event."""

    def __init__(self, text: str) -> None:
        self.text = text

    async def run_async(self, **kwargs):
        part = SimpleNamespace(function_call=None, function_response=None, thought=False, text=self.text)
        yield SimpleNamespace(
            author="final_agent",
            partial=False,
            content=SimpleNamespace(parts=[part]),
            usage_metadata=None,
            grounding_metadata=None,
            is_final_response=lambda: True,
        )


async def test_a_final_only_answer_is_timed_under_the_model_then_in_use(metric_reader, monkeypatch):
    async def no_session(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", no_session)
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _FinalOnly("Done."))
    stats = TurnStats(model=CLAUDE, retry_enabled=True, notify=lambda record: None, switched_to="claude-haiku-5-5")
    token = current_turn.set(stats)
    try:
        records = [r async for r in agent_runner._run_turn(CLAUDE, SESSION, QUERY)]
    finally:
        current_turn.reset(token)
    assert records == [{"type": "token", "text": "Done."}]

    [point] = metric_reader()["app.llm.stream.ttft"]
    assert dict(point.attributes) == {"gen_ai.request.model": "claude-haiku-5-5", "gen_ai.agent.name": "final_agent"}
