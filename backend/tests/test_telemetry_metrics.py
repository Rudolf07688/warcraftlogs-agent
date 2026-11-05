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
from backend.tests.test_wcl_cache import dead_redis  # noqa: F401 - fixture
from wcl_agent.cache import cache
from wcl_agent.cache.cache import CacheFamily, Outcome
from wcl_agent.cache.cache_models import CharacterRef
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


def _lookups(points: Points) -> dict[str, int]:
    """app.cache.requests by result."""
    return {p.attributes["app.cache.result"]: p.value for p in points["app.cache.requests"]}


class _BatchLoader:
    async def __call__(self, missing):
        return [CharacterRef(id=i, name="Rudolf", realm="area-52", region="eu", class_id=4) for i in missing]


_MANY = [cache.keys.char_zone(i, 0, "dps", 0) for i in range(4)]


async def test_a_corrupt_entry_counts_once(metric_reader, fake_redis):
    """BUG-003: the dropped entry and its reload are one lookup."""
    key = cache.keys.char_zone(7, 0, "dps", 0)
    await fake_redis.set(key, b"{not json")

    async def load():
        return CharacterRef(id=7, name="Rudolf", realm="area-52", region="eu", class_id=4)

    await cache.get_or_load(CacheFamily.CHAR_OVERVIEW, key, CharacterRef, load)

    assert _lookups(metric_reader()) == {"miss": 1}


async def test_a_failed_write_after_a_load_counts_once(metric_reader, fake_redis, monkeypatch):
    """BUG-003: a value that loaded but could not be stored is one miss, not a miss and a
    redis_error."""
    client = cache._client()
    real_set = client.set

    async def refuse_values(name, value, *args, **kwargs):
        if kwargs.get("ex"):
            raise cache.RedisError("read-only replica")
        return await real_set(name, value, *args, **kwargs)

    monkeypatch.setattr(client, "set", refuse_values)
    key = cache.keys.char_zone(8, 0, "dps", 0)

    async def load():
        return CharacterRef(id=8, name="Rudolf", realm="area-52", region="eu", class_id=4)

    await cache.get_or_load(CacheFamily.CHAR_OVERVIEW, key, CharacterRef, load)

    assert _lookups(metric_reader()) == {"miss": 1}


async def test_a_batch_counts_one_lookup_per_key(metric_reader, fake_redis):
    await fake_redis.set(_MANY[1], CharacterRef(id=1, name="Rudolf", realm="area-52", region="eu", class_id=4).model_dump_json())
    await fake_redis.set(_MANY[3], b"{corrupt")

    await cache.get_many_or_load(CacheFamily.CHAR_OVERVIEW, _MANY, CharacterRef, _BatchLoader())

    assert _lookups(metric_reader()) == {"hit": 1, "miss": 3}


async def test_a_batch_with_redis_down_counts_one_miss_per_key(metric_reader, dead_redis):
    """BUG-003: N keys with Redis down are N misses, on the failing call and with the
    circuit open."""
    for _ in range(2):
        await cache.get_many_or_load(CacheFamily.CHAR_OVERVIEW, _MANY, CharacterRef, _BatchLoader())

    assert _lookups(metric_reader()) == {"miss": 8}


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


async def test_a_search_scoped_by_report_is_labelled_by_the_index_it_searched(metric_reader):
    """BUG-005: a report code narrows the search to WCL chunks, so the label says wcl."""
    searched: list[kb_search.SearchFilters] = []

    async def runner(query, vector, filters, tenant_id, legs):
        searched.append(filters)
        return [_hit(1.0)]

    request = kb_search.SearchRequest(
        queries=(QUERY,), filters=kb_search.SearchFilters(report_code="a1B2c3"), hard=frozenset(), k=1,
        tenant_id=uuid.uuid4(),
    )
    await kb_search.search(request, embedder=None, runner=runner)

    assert kb_search.searched_kinds(searched[0]) == ["wcl"]
    assert metric_reader().labels("app.rag.retrieved_chunks") == [{"app.rag.index": "wcl"}]


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


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now


def _event(part, *, partial: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        author="wcl_agent",
        partial=partial,
        content=SimpleNamespace(parts=[part]),
        usage_metadata=None,
        grounding_metadata=None,
        is_final_response=lambda: not partial,
    )


def _part(**fields) -> SimpleNamespace:
    return SimpleNamespace(**{"function_call": None, "function_response": None, "thought": False, "text": None, **fields})


class _ToolThenText:
    """Thinks 1.0 s, calls a tool that answers 0.2 s later (under ``response_id``), streams
    its answer 0.5 s after that."""

    def __init__(self, clock: _Clock, response_id: str | None) -> None:
        self.clock, self.response_id = clock, response_id

    async def run_async(self, **kwargs):
        self.clock.now += 1.0
        yield _event(_part(function_call=SimpleNamespace(id="c1", name="report_title", args={"code": "a1B2c3"})))
        self.clock.now += 0.2
        response = SimpleNamespace(id=self.response_id, name="report_title", response={"status": "success"})
        yield _event(_part(function_response=response))
        self.clock.now += 0.5
        yield _event(_part(text="It was Raid Night."), partial=True)


@pytest.mark.parametrize("response_id", ["c1", None, "never-started"])
async def test_time_to_first_token_runs_from_the_turn_start_across_a_tool_round(metric_reader, monkeypatch, response_id):
    """BUG-001: the tool timer must not replace the turn's start, and a tool response without
    a matching call id must not break the turn."""
    clock = _Clock()

    async def no_session(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_runner, "time", clock)
    monkeypatch.setattr(agent_runner, "_ensure_session", no_session)
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _ToolThenText(clock, response_id))

    records = [r async for r in agent_runner._run_turn(CLAUDE, SESSION, QUERY)]
    assert [r["type"] for r in records] == ["tool_start", "tool_end", "token"]

    [point] = metric_reader()["app.llm.stream.ttft"]
    assert point.count == 1
    assert point.sum == pytest.approx(1.7)


# --- sc-462 (feature 059): finish reasons, conversation depth, embeddings -----------------

TENANT = "tenant-059"  # a workspace run: chat turns, not the greeting's local user


async def test_chat_turns_count_finish_reasons_and_record_the_conversation_depth(metric_reader, monkeypatch, use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(
        monkeypatch,
        ScriptedApi(
            tool_call_with("report_title", {"code": "a1B2c3"}),
            text_answer("It was Raid Night."),
            text_answer("Yes, the same night."),
        ),
        report_title,
    )

    for question in (QUERY, "and the second?"):
        [r async for r in agent_runner.stream_response(CLAUDE, SESSION, question, user_id=TENANT)]

    points = metric_reader()
    [reasons] = points["app.llm.finish_reasons"]  # tool_use and end_turn are both STOP
    assert dict(reasons.attributes) == {"gen_ai.request.model": CLAUDE, "app.llm.finish_reason": "stop"}
    assert reasons.value == 3  # one per model response, never per streamed chunk
    [depth] = points["app.agent.turns_per_conversation"]
    assert (depth.count, depth.sum, depth.min, depth.max) == (2, 3, 1, 2)  # turn 1, then turn 2
    assert set(depth.attributes) == {"gen_ai.agent.name"} and depth.attributes["gen_ai.agent.name"]
    session = await agent_runner._session_service.get_session(
        app_name=agent_runner.APP_NAME, user_id=TENANT, session_id=SESSION
    )
    assert session.state[agent_runner.TURNS_KEY] == 2
    assert_clean(points.all_labels())


async def test_the_greeting_and_guide_runs_record_no_conversation_depth(metric_reader, monkeypatch, use_provider):
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(monkeypatch, ScriptedApi(text_answer("Welcome back.")), report_title)

    [r async for r in agent_runner.stream_response(CLAUDE, SESSION, QUERY)]

    points = metric_reader()
    assert points["app.agent.turns_per_conversation"] == []
    assert points.labels("app.llm.finish_reasons") == [{"gen_ai.request.model": CLAUDE, "app.llm.finish_reason": "stop"}]
    session = await agent_runner._session_service.get_session(
        app_name=agent_runner.APP_NAME, user_id=agent_runner.USER_ID, session_id=SESSION
    )
    assert agent_runner.TURNS_KEY not in session.state


@pytest.mark.parametrize(
    ("state", "turns"),
    [({}, 0), ({"app_turns": 4}, 4), ({"app_turns": "4"}, 0), ({"app_turns": True}, 0), ({"app_turns": -1}, 0)],
)
async def test_the_turn_count_comes_from_the_session_state(monkeypatch, state, turns):
    class _Service:
        async def get_session(self, **kwargs):
            return SimpleNamespace(state=state)

    monkeypatch.setattr(agent_runner, "_get_session_service", lambda: _Service())
    assert await agent_runner._ensure_session("s1", TENANT) == turns


def test_finish_reasons_are_a_fixed_set(metric_reader):
    from google.genai import types

    from backend.app.telemetry import metrics as app_metrics

    for reason in (
        types.FinishReason.MAX_TOKENS,
        types.FinishReason("SOMETHING_NEW_FROM_THE_API"),  # google-genai makes up a member
        "free text from a provider",
        None,
        types.FinishReason.FINISH_REASON_UNSPECIFIED,
        42,
    ):
        app_metrics.record_finish_reason(CLAUDE, reason)

    counted = {p.attributes["app.llm.finish_reason"]: p.value for p in metric_reader()["app.llm.finish_reasons"]}
    assert counted == {"max_tokens": 1, "other": 2}
    assert set(counted) <= app_metrics.FINISH_REASONS


async def test_each_embedding_request_records_latency_and_batch_size(metric_reader, monkeypatch):
    from backend.app.kb.embedder import VertexEmbedder
    from backend.tests.test_kb_embed import FakeGenai
    from wcl_agent.llm import generation

    monkeypatch.setattr(generation, "_genai_client", lambda: FakeGenai())
    await VertexEmbedder("gemini-embedding-001", request_batch=2).embed([QUERY, "b", "c"], task="RETRIEVAL_QUERY")
    await VertexEmbedder("gemini-embedding-001", request_batch=2).embed(["d"], task="RETRIEVAL_DOCUMENT")

    points = metric_reader()
    sizes = {p.attributes["app.embedding.task"]: (p.count, p.sum) for p in points["app.embedding.batch_size"]}
    assert sizes == {"query": (2, 3), "document": (1, 1)}  # requests of 2 + 1 texts, then 1
    durations = {p.attributes["app.embedding.task"]: p.count for p in points["app.embedding.duration"]}
    assert durations == {"query": 2, "document": 1}
    assert {"gen_ai.request.model": "gemini-embedding-001", "app.embedding.task": "query"} in points.labels(
        "app.embedding.duration"
    )
    assert_clean(points.all_labels())


class _StreamedWithReason:
    """Gemini-style streaming: the last partial chunk and the aggregated final event both
    carry the finish reason."""

    async def run_async(self, **kwargs):
        from google.genai import types

        for partial in (True, True, False):
            event = _event(_part(text="Raid Night."), partial=partial)
            event.finish_reason = types.FinishReason.STOP
            yield event


async def test_a_streamed_response_counts_its_finish_reason_once(metric_reader, monkeypatch):
    async def no_session(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_runner, "_ensure_session", no_session)
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: _StreamedWithReason())
    [r async for r in agent_runner._run_turn(CLAUDE, SESSION, QUERY, user_id=TENANT)]

    [point] = metric_reader()["app.llm.finish_reasons"]
    assert point.value == 1
