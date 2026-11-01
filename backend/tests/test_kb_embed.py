"""The knowledge base embedder (feature 043, contract 2) and the provider layer's embedding call.
No Vertex call: a fake genai client stands in for the SDK, and tests inject fakes through
``set_embedder``."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from backend.app.kb import embedder as kb_embedder
from backend.app.kb.embedder import DIMENSIONS, VertexEmbedder, get_embedder, normalise, set_embedder
from wcl_agent.llm import generation
from wcl_agent.llm.model_retry import RetryPolicy


class FakeGenai:
    """``client.aio.models.embed_content`` recording each request; ``fail`` queues errors."""

    def __init__(self, dims: int = DIMENSIONS, fail: list[Exception] | None = None):
        self.calls: list[dict] = []
        self.dims = dims
        self.fail = list(fail or [])
        self.aio = SimpleNamespace(models=SimpleNamespace(embed_content=self.embed_content))

    async def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        if self.fail:
            raise self.fail.pop(0)
        # Not unit length on purpose: truncated Gemini vectors aren't.
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[3.0, 4.0] + [0.0] * (self.dims - 2)) for _ in contents]
        )


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    set_embedder(None)
    kb_embedder._vertex_embedder.cache_clear()
    monkeypatch.setattr(kb_embedder, "_POLICY", RetryPolicy(attempts=3, initial_s=0, jitter_s=0))
    yield
    set_embedder(None)
    kb_embedder._vertex_embedder.cache_clear()


@pytest.fixture
def client(monkeypatch) -> FakeGenai:
    fake = FakeGenai()
    monkeypatch.setattr(generation, "_genai_client", lambda: fake)
    return fake


def test_normalise_gives_unit_length_and_keeps_zero():
    assert normalise([3.0, 4.0]) == [0.6, 0.8]
    assert math.isclose(math.fsum(v * v for v in normalise([1.0, 2.0, 2.0])), 1.0)
    assert normalise([0.0, 0.0]) == [0.0, 0.0]


async def test_vertex_embedder_sends_task_and_768_dims_and_returns_unit_vectors(client):
    vectors = await VertexEmbedder("gemini-embedding-001", request_batch=2).embed(
        ["a", "b"], task="RETRIEVAL_DOCUMENT"
    )
    assert len(vectors) == 2 and all(len(v) == DIMENSIONS for v in vectors)
    assert all(math.isclose(math.fsum(x * x for x in v), 1.0) for v in vectors)
    call = client.calls[0]
    assert call["model"] == "gemini-embedding-001" and call["contents"] == ["a", "b"]
    assert (call["config"].task_type, call["config"].output_dimensionality, call["config"].auto_truncate) == (
        "RETRIEVAL_DOCUMENT", DIMENSIONS, True,
    )


async def test_vertex_embedder_batches_requests(client):
    await VertexEmbedder("m", request_batch=2).embed(["a", "b", "c"], task="RETRIEVAL_QUERY")
    assert [c["contents"] for c in client.calls] == [["a", "b"], ["c"]]
    client.calls.clear()
    await VertexEmbedder("m").embed(["a", "b"], task="RETRIEVAL_QUERY")
    assert len(client.calls) == 2  # the default sends one text per request


async def test_vertex_embedder_refuses_a_wrong_dimension(monkeypatch):
    monkeypatch.setattr(generation, "_genai_client", lambda: FakeGenai(dims=3072))
    with pytest.raises(ValueError, match="dimensions"):
        await VertexEmbedder("m").embed(["a"], task="RETRIEVAL_DOCUMENT")


async def test_rate_limit_is_retried_through_the_shared_loop(client):
    client.fail = [genai_errors.APIError(429, {"error": {"message": "slow down"}})]
    vectors = await VertexEmbedder("m").embed(["a"], task="RETRIEVAL_DOCUMENT")
    assert len(vectors) == 1 and len(client.calls) == 2


async def test_other_errors_raise_without_retry(client):
    client.fail = [genai_errors.APIError(400, {"error": {"message": "bad"}})]
    with pytest.raises(genai_errors.APIError):
        await VertexEmbedder("m").embed(["a"], task="RETRIEVAL_DOCUMENT")
    assert len(client.calls) == 1


def test_get_embedder_returns_the_injected_one_until_cleared(client):
    fake = SimpleNamespace(model="fake")
    set_embedder(fake)
    assert get_embedder() is fake
    set_embedder(None)
    assert get_embedder() is not fake


def test_get_embedder_is_none_when_no_client_can_be_built(monkeypatch):
    def boom():
        raise ValueError("no credentials")

    monkeypatch.setattr(generation, "_genai_client", boom)
    assert generation.embeddings_available() is False
    assert get_embedder() is None


def test_get_embedder_is_none_when_switched_off(client, monkeypatch):
    monkeypatch.setattr(kb_embedder.settings, "kb_embed_enabled", False)
    assert get_embedder() is None


def test_get_embedder_builds_one_vertex_embedder_from_settings(client, monkeypatch):
    monkeypatch.setattr(kb_embedder.settings, "kb_embed_model", "text-embedding-005")
    first = get_embedder()
    assert isinstance(first, VertexEmbedder) and first.model == "text-embedding-005"
    assert get_embedder() is first


# --- the background indexer (sc-112 AC4-AC8, sc-305 AC3) ------------------------------------

import asyncio  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from sqlalchemy import select, update  # noqa: E402

from backend.app.db import session as db_session  # noqa: E402
from backend.app.db.models import Conversation, KbChatChunk, KbChunk, RawFetch, UserCharacter  # noqa: E402
from backend.app.kb import indexer as kb_indexer  # noqa: E402
from backend.app.kb.indexer import ExchangeJob, GuideJob, KbIndexer  # noqa: E402
from backend.app.services.fetch_persistence import PendingWrite, store_batch  # noqa: E402
from wcl_agent.client.queries import REPORT_SUMMARY  # noqa: E402
from wcl_agent.client.wcl_client import FetchedResponse, _flight_key  # noqa: E402

NOW = datetime(2026, 11, 1, tzinfo=UTC)
CODE = "AbCdEf123456"


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self, fail: bool = False):
        self.calls: list[list[str]] = []
        self.fail = fail

    async def embed(self, texts, *, task):
        assert task == "RETRIEVAL_DOCUMENT"
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("vertex down")
        return [normalise([1.0, 2.0] + [0.0] * (DIMENSIONS - 2)) for _ in texts]


def summary_fetch(fights: list[int], title: str = "Raid night") -> FetchedResponse:
    report = {"code": CODE, "title": title, "startTime": 1_760_000_000_000, "zone": {"id": 44, "name": "Zone"},
              "masterData": {"actors": [{"id": 1, "name": "Vagxsu", "subType": "Warrior"}]},
              "fights": [{"id": f, "name": f"Boss{f}", "encounterID": 3000 + f, "difficulty": 4, "kill": True,
                          "friendlyPlayers": [1], "startTime": 0} for f in fights]}
    variables = {"code": CODE}
    body = json.dumps({"data": {"reportData": {"report": report}}}).encode()
    return FetchedResponse(_flight_key(REPORT_SUMMARY, variables), REPORT_SUMMARY, variables, body, NOW)


@pytest.fixture
def db(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    return session_factory


@pytest.fixture
def indexer() -> KbIndexer:
    return KbIndexer(max_items=10, batch=2, sweep_s=600)


async def add_raw(db, fetched: FetchedResponse) -> None:
    async with db() as s:
        s.add(RawFetch(query_key=fetched.query_key, params=fetched.variables, report_codes=[CODE],
                       fetched_at=NOW, payload={}))
        await s.commit()


async def chunks(db, model=KbChunk):
    async with db() as s:
        return list(await s.scalars(select(model).order_by(model.label)))


async def test_a_stored_fetch_is_chunked_and_embedded_with_unit_vectors(db, indexer):
    fake = FakeEmbedder()
    set_embedder(fake)
    fetched = summary_fetch([1, 2, 3])
    await add_raw(db, fetched)
    await indexer.handle(fetched)
    rows = await chunks(db)
    assert [r.label for r in rows] == ["fight 1 summary", "fight 2 summary", "fight 3 summary"]
    assert all(math.isclose(math.fsum(x * x for x in r.embedding), 1.0) for r in rows)
    assert {r.embed_model for r in rows} == {"fake-embed"} and all(r.embedded_at for r in rows)
    assert [len(c) for c in fake.calls] == [2, 1]  # batched by kb_embed_batch


async def test_an_unchanged_chunk_is_never_embedded_again(db, indexer):
    fake = FakeEmbedder()
    set_embedder(fake)
    await add_raw(db, summary_fetch([1, 2]))
    await indexer.handle(summary_fetch([1, 2]))
    assert sum(map(len, fake.calls)) == 2
    await indexer.handle(summary_fetch([1, 2]))  # same text: nothing to embed
    assert sum(map(len, fake.calls)) == 2
    await indexer.handle(summary_fetch([1, 2, 3]))  # one new fight: one call for it alone
    assert fake.calls[-1] == [(await chunks(db))[2].text] and sum(map(len, fake.calls)) == 3


async def test_a_replaced_fetch_loses_chunks_it_no_longer_produces(db, indexer):
    set_embedder(FakeEmbedder())
    await add_raw(db, summary_fetch([1, 2]))
    await indexer.handle(summary_fetch([1, 2]))
    await indexer.handle(summary_fetch([2], title="Renamed"))
    [row] = await chunks(db)
    assert row.fight_id == 2 and "Renamed" in row.text and row.embedding is not None


async def test_a_failing_embedder_leaves_keyword_rows_and_the_sweep_embeds_them(db, indexer):
    fake = FakeEmbedder(fail=True)
    set_embedder(fake)
    await add_raw(db, summary_fetch([1]))
    await indexer.handle(summary_fetch([1]))  # never raises
    [row] = await chunks(db)
    assert row.embedding is None and row.text.startswith(f"Report {CODE}")
    await indexer.handle(GuideJob(uuid.uuid4(), "Warrior", "Arms", "raid", "## Rotation\nMortal Strike."))
    assert len(fake.calls) == 1  # paused until the sweep: no hammering a failing Vertex
    fake.fail = False
    await indexer.sweep()
    assert all(r.embedding is not None for r in await chunks(db))


async def test_a_vector_is_not_stored_when_the_text_changed_meanwhile(db, indexer):
    class Racing(FakeEmbedder):
        async def embed(self, texts, *, task):
            async with db() as s:  # a newer chunk text lands while Vertex is answering
                await s.execute(update(KbChunk).values(text="newer", content_hash="other"))
                await s.commit()
            return await super().embed(texts, task=task)

    set_embedder(Racing())
    await add_raw(db, summary_fetch([1]))
    await indexer.handle(summary_fetch([1]))
    [row] = await chunks(db)
    assert row.text == "newer" and row.embedding is None


async def test_without_an_embedder_chunks_are_still_written(db, indexer, monkeypatch):
    monkeypatch.setattr(kb_embedder, "get_embedder", lambda: None)
    monkeypatch.setattr(kb_indexer, "get_embedder", lambda: None)
    await add_raw(db, summary_fetch([1]))
    await indexer.handle(summary_fetch([1]))
    [row] = await chunks(db)
    assert row.embedding is None


async def test_a_fetch_naming_no_report_is_never_chunked(db, indexer):
    set_embedder(FakeEmbedder())
    q = "query CharRef($name: String!) { characterData { character(name: $name) { id } } }"
    fetched = FetchedResponse(_flight_key(q, {"name": "x"}), q, {"name": "x"}, b'{"data": {}}', NOW)
    await indexer.handle(fetched)
    assert await chunks(db) == []


async def test_offers_enqueue_only_and_a_full_queue_drops(db):
    indexer = KbIndexer(max_items=1, batch=2, sweep_s=600)
    indexer.start()
    try:
        job = GuideJob(uuid.uuid4(), "Warrior", "Arms", "raid", "## A\nb")
        kb_indexer.offer_guide(job)
        kb_indexer.offer_guide(job)
        kb_indexer.offer_guide(job)
        assert indexer.stats.dropped == 2
    finally:
        await indexer.stop(grace_s=1)
    kb_indexer.offer_guide(job)  # no indexer: a no-op, never raises


async def test_the_writer_offers_changed_fetches_after_its_commit(db, monkeypatch):
    offered: list[FetchedResponse] = []
    monkeypatch.setattr(kb_indexer, "offer_fetch", offered.append)
    fetched = summary_fetch([1])
    await store_batch([PendingWrite(fetched, None)])
    assert offered == [fetched]
    await store_batch([PendingWrite(summary_fetch([1]), None)])  # unchanged body: not offered
    assert offered == [fetched]


async def test_an_exchange_lands_in_its_workspace_with_mentions(db, indexer, tenant_id):
    fake = FakeEmbedder()
    set_embedder(fake)
    async with db() as s:
        conv = Conversation(tenant_id=tenant_id, model="m")
        s.add(conv)
        s.add(UserCharacter(tenant_id=tenant_id, role="self", name="Vagxsu", server="tarren-mill", region="EU",
                            class_name="Warrior", active_spec="Arms"))
        await s.commit()
    job = ExchangeJob(tenant_id, conv.id, 2, "How is vagxsu's Arms build?", "Fine, keep Mortal Strike up.", NOW)
    await indexer.handle(job)
    await indexer.handle(job)  # unchanged: not embedded again
    [row] = await chunks(db, KbChatChunk)
    assert (row.tenant_id, row.conversation_id, row.message_seq) == (tenant_id, conv.id, 2)
    assert row.text == "Question: How is vagxsu's Arms build?\n\nAnswer: Fine, keep Mortal Strike up."
    assert row.characters == [{"name": "Vagxsu", "key": "vagxsu", "class": "Warrior", "spec": "Arms"}]
    assert row.embedding is not None and len(fake.calls) == 1


async def test_the_consumer_runs_jobs_in_the_background(db):
    fake = FakeEmbedder()
    set_embedder(fake)
    indexer = KbIndexer(max_items=10, batch=8, sweep_s=600)
    indexer.start()
    try:
        await add_raw(db, summary_fetch([1]))
        kb_indexer.offer_fetch(summary_fetch([1]))
        for _ in range(100):
            if fake.calls:
                break
            await asyncio.sleep(0.01)
    finally:
        await indexer.stop(grace_s=1)
    assert len(fake.calls) == 1
