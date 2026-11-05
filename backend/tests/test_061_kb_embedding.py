"""Feature 061: query embeddings that finish inside search's budget (sc-428), go out together
(sc-319), and show up on D8 when the budget cancels them (sc-503). No Vertex call: fake genai
clients and fake ``google.genai.Client`` constructors stand in for the SDK."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.app.kb import embedder as kb_embedder
from backend.app.kb import search as kb
from backend.app.kb.embedder import DIMENSIONS, QUERY_CONCURRENCY, VertexEmbedder, get_embedder, set_embedder
from backend.app.kb.search import SearchFilters, SearchRequest
from backend.tests.test_telemetry_metrics import QUERY, assert_clean, metric_reader  # noqa: F401 - fixture
from wcl_agent.llm import generation, provider
from wcl_agent.llm.model_retry import RetryPolicy

MODEL = "gemini-embedding-001"
TENANT = uuid.UUID("06100000-0000-0000-0000-000000000061")


class SlowGenai:
    """``aio.models.embed_content`` that waits on ``gate`` (or ``delay_s``) and tracks how many
    requests are in flight at once."""

    def __init__(self, *, delay_s: float = 0.0, gate: asyncio.Event | None = None):
        self.delay_s = delay_s
        self.gate = gate
        self.in_flight = 0
        self.peak = 0
        self.calls = 0
        self.aio = SimpleNamespace(models=SimpleNamespace(embed_content=self.embed_content))

    async def embed_content(self, *, model, contents, config):
        self.calls += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            if self.gate is not None:
                await self.gate.wait()
            await asyncio.sleep(self.delay_s)
        finally:
            self.in_flight -= 1
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] + [0.0] * (DIMENSIONS - 1)) for _ in contents])


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    set_embedder(None)
    kb_embedder._vertex_embedder.cache_clear()
    generation._located_genai_client.cache_clear()
    monkeypatch.setattr(kb_embedder, "_POLICY", RetryPolicy(attempts=1, initial_s=0, jitter_s=0))
    yield
    set_embedder(None)
    kb_embedder._vertex_embedder.cache_clear()
    generation._located_genai_client.cache_clear()


@pytest.fixture
def vertex_env(monkeypatch):
    """Vertex with every model call at ``global``, and a capturing ``google.genai.Client``."""
    from google import genai

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-061")
    monkeypatch.setenv("WCL_MODEL_LOCATION", "global")
    built: list[dict] = []
    slow = SlowGenai()

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            built.append(kwargs)
            self.aio = slow.aio

    monkeypatch.setattr(genai, "Client", FakeClient)
    # The model-location client is cached per process: stand in for it without building one.
    monkeypatch.setattr(generation, "_genai_client", lambda: SimpleNamespace(aio=None))
    return built


# --- sc-428: the cause is the global endpoint, so embeddings run at a regional one ----------


def test_the_default_embed_location_is_regional_not_the_model_location():
    """sc-428: global answers gemini-embedding-001's ``:predict`` ~12 s late on every new
    connection (measured 2026-11-05), past search's 3 s budget. The default must stay regional."""
    assert kb_embedder.settings.kb_embed_location not in ("", "global")


async def test_query_embeddings_run_at_the_embed_location_and_chat_stays_global(vertex_env, monkeypatch):
    monkeypatch.setattr(kb_embedder.settings, "kb_embed_location", "europe-west4")
    embedder = get_embedder()
    assert isinstance(embedder, VertexEmbedder)

    await embedder.embed([QUERY], task="RETRIEVAL_QUERY")
    await embedder.embed(["doc"], task="RETRIEVAL_DOCUMENT")
    provider.genai_client()  # what chat, guides and reports build

    assert vertex_env[-1]["location"] == "global"
    embed_clients = vertex_env[:-1]
    assert embed_clients == [{"vertexai": True, "project": "proj-061", "location": "europe-west4"}]  # built once


async def test_an_empty_embed_location_falls_back_to_the_model_location(vertex_env, monkeypatch):
    monkeypatch.setattr(kb_embedder.settings, "kb_embed_location", "")
    monkeypatch.setattr(generation, "_genai_client", lambda: provider.genai_client())
    await get_embedder().embed([QUERY], task="RETRIEVAL_QUERY")
    assert {c["location"] for c in vertex_env} == {"global"}


# --- sc-319: a multi-query search embeds its queries concurrently (bounded) ---------------


async def test_query_requests_go_out_together_and_documents_one_by_one(monkeypatch):
    fake = SlowGenai(delay_s=0.05)
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)

    vectors = await VertexEmbedder(MODEL).embed(["a", "b", "c", "d"], task="RETRIEVAL_QUERY")
    assert len(vectors) == 4 and fake.peak == 4  # sequential requests would peak at 1

    fake.peak = 0
    await VertexEmbedder(MODEL).embed(["a", "b", "c"], task="RETRIEVAL_DOCUMENT")
    assert fake.peak == 1  # the background indexer's load is unchanged


async def test_query_concurrency_is_bounded_across_the_process(monkeypatch):
    """QA BUG-005: one search sends at most 5 queries, so the bound only means something across
    searches (several in one model round, several players)."""
    fake = SlowGenai(delay_s=0.05)
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    searches = [VertexEmbedder(MODEL).embed([f"q{i}" for i in range(4)], task="RETRIEVAL_QUERY") for _ in range(3)]
    await asyncio.gather(*searches)
    assert fake.peak == QUERY_CONCURRENCY and fake.calls == 12


async def test_a_multi_query_embedding_takes_about_one_request(monkeypatch):
    """The ticket's measure: wall time ~ one request, not N (sequential: 4 x 1 s = 4 s)."""
    fake = SlowGenai(delay_s=1.0)
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    loop = asyncio.get_running_loop()
    started = loop.time()
    await VertexEmbedder(MODEL).embed(["a", "b", "c", "d"], task="RETRIEVAL_QUERY")
    assert loop.time() - started < 3.0


async def test_concurrent_query_vectors_keep_the_query_order(monkeypatch):
    class Ordered(SlowGenai):
        async def embed_content(self, *, model, contents, config):
            index = int(contents[0][1:])
            await asyncio.sleep(0.01 * (5 - index))  # later queries answer first
            values = [0.0] * DIMENSIONS
            values[index] = 1.0
            return SimpleNamespace(embeddings=[SimpleNamespace(values=values)])

    fake = Ordered()
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    vectors = await VertexEmbedder(MODEL).embed([f"q{i}" for i in range(5)], task="RETRIEVAL_QUERY")
    assert [v.index(1.0) for v in vectors] == [0, 1, 2, 3, 4]


# --- sc-503: a query embedding cancelled by search's budget is recorded once ---------------


async def test_a_search_whose_embedding_times_out_records_each_cancelled_request(metric_reader, monkeypatch):
    fake = SlowGenai(gate=asyncio.Event())  # never released: slower than any budget
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    monkeypatch.setattr(kb, "EMBED_TIMEOUT_S", 0.1)

    async def runner(query, vector, filters, tenant_id, legs):
        assert vector is None and legs == frozenset({"keyword"})
        return []

    request = SearchRequest((QUERY, "second phrasing"), SearchFilters(), frozenset(), 8, TENANT)
    result = await kb.search(request, embedder=VertexEmbedder(MODEL), runner=runner)

    assert result.mode == "keyword_only"
    points = metric_reader()
    cancelled = {"gen_ai.request.model": MODEL, "app.embedding.task": "query", "error.type": "CancelledError"}
    assert points.labels("app.embedding.duration") == [cancelled]
    assert [p.count for p in points["app.embedding.duration"]] == [2]  # one per request, not twice
    assert [p.count for p in points["app.embedding.batch_size"]] == [2]
    assert_clean(points.all_labels())


async def test_a_cancelled_request_is_not_swallowed_and_a_document_one_is_not_a_failure(
    metric_reader, monkeypatch
):
    """The cancellation propagates; and QA BUG-006: a document request cancelled by the indexer's
    shutdown (``KbIndexer.stop``) is not recorded as a failed embedding."""
    fake = SlowGenai(gate=asyncio.Event())
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    # Documents await the request directly; for queries the TaskGroup's own cancellation would hide a swallow.
    task = asyncio.create_task(VertexEmbedder(MODEL).embed(["a"], task="RETRIEVAL_DOCUMENT"))
    while fake.calls == 0:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert metric_reader()["app.embedding.duration"] == []


# --- QA BUG-003: one failed query cancels its siblings ----------------------------------------


class FailingFirst(SlowGenai):
    """Query ``bad`` fails at once with ``error``; every other request waits on a gate that is
    never released."""

    def __init__(self, error: BaseException):
        super().__init__(gate=asyncio.Event())
        self.error = error

    async def embed_content(self, *, model, contents, config):
        if contents == ["bad"]:
            self.calls += 1
            await asyncio.sleep(0.01)  # the siblings are in flight by now
            raise self.error
        return await super().embed_content(model=model, contents=contents, config=config)


async def test_a_failed_query_cancels_its_siblings_and_each_is_recorded_once(metric_reader, monkeypatch):
    fake = FailingFirst(RuntimeError("bad request"))
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)

    with pytest.raises(RuntimeError):
        await VertexEmbedder(MODEL).embed(["q1", "bad", "q3"], task="RETRIEVAL_QUERY")

    assert fake.calls == 3 and fake.in_flight == 0  # nothing left running after embed returns
    points = metric_reader()
    counts = {p.attributes["error.type"]: p.count for p in points["app.embedding.duration"]}
    assert counts == {"RuntimeError": 1, "CancelledError": 2}


# --- QA BUG-006: a rate-limited query fails inside search's budget, as a rate limit ----------


def test_the_query_deadline_fits_inside_searchs_budget():
    assert 0 < kb_embedder.QUERY_DEADLINE_S <= kb.EMBED_TIMEOUT_S


async def test_a_rate_limited_query_surfaces_as_a_rate_limit_not_a_timeout(metric_reader, monkeypatch):
    from google.genai import errors as genai_errors

    limited = genai_errors.APIError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    fake = FailingFirst(limited)
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    # The real schedule's shape: the first retry wait (2-3 s) would end past the 3 s budget.
    monkeypatch.setattr(kb_embedder, "_POLICY", RetryPolicy(attempts=4, initial_s=3.5, jitter_s=0))
    loop = asyncio.get_running_loop()
    started = loop.time()

    assert await kb._embed(["bad"], VertexEmbedder(MODEL)) is None  # keyword only
    assert loop.time() - started < 2.0  # failed at once, did not sleep into the budget
    labels = metric_reader().labels("app.embedding.duration")
    assert [attrs["error.type"] for attrs in labels] == ["ModelRateLimited"]
