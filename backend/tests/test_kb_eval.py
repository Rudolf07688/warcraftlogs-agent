"""The knowledge search eval (feature 044, sc-115 AC2): fixture integrity and metrics on SQLite."""

from __future__ import annotations

import math
import os

import pytest

from backend.evals.kb import harness
from backend.evals.kb.standin import DIMENSIONS, StandInEmbedder, embed_one


def test_fixture_corpus_covers_all_three_kinds():
    corpus = harness.load_corpus()
    assert set(corpus) == {"wcl", "guide", "chat"}
    assert all(len(chunks) >= 10 for chunks in corpus.values())
    ids = [c["id"] for chunks in corpus.values() for c in chunks]
    assert len(ids) == len(set(ids))


def test_about_thirty_labelled_questions_point_at_real_chunks():
    corpus, questions = harness.load_corpus(), harness.load_questions()
    ids = harness.chunk_ids(corpus)
    assert 28 <= len(questions) <= 35
    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        assert q["question"].strip() and q["expected"], q["id"]
        assert set(q["expected"]) <= ids, q["id"]
    # every kind is the target of some question
    kinds = {kind for kind, chunks in corpus.items() for c in chunks if any(c["id"] in q["expected"] for q in questions)}
    assert kinds == {"wcl", "guide", "chat"}


def test_labelled_filters_use_the_tool_arguments():
    allowed = {"kind", "class_name", "spec", "encounter", "difficulty", "report_code", "character"}
    for q in harness.load_questions():
        assert set(q["filters"]) <= allowed, q["id"]


def test_recall_at_k():
    assert harness.recall_at_k(["a", "b"], ["a", "x", "b"], 2) == 0.5
    assert harness.recall_at_k(["a", "b"], ["a", "x", "b"], 3) == 1.0
    assert harness.recall_at_k(["a"], [], 8) == 0.0


def test_percentile_is_nearest_rank():
    assert harness.percentile([5, 1, 3, 2, 4], 50) == 3
    assert harness.percentile([5, 1, 3, 2, 4], 95) == 5
    assert harness.percentile([], 95) == 0.0


def test_only_recorded_real_embeddings_count_as_real():
    assert harness.is_real("vertex:gemini-embedding-001")
    assert not harness.is_real("stand-in")


async def test_stand_in_is_deterministic_and_unit_norm():
    a, b = embed_one("Arms Warrior opener"), embed_one("Arms Warrior opener")
    assert a == b and len(a) == DIMENSIONS
    assert math.isclose(math.fsum(v * v for v in a), 1.0, rel_tol=1e-9)
    assert (await StandInEmbedder().embed(["x", "y"], task="RETRIEVAL_QUERY"))[0] == embed_one("x")
    # related texts are closer than unrelated ones
    def cos(u, v):
        return sum(x * y for x, y in zip(u, v, strict=True))

    q = embed_one("arms warrior rotation")
    assert cos(q, embed_one("Arms Warrior raid rotation: Mortal Strike")) > cos(q, embed_one("Holy Priest Divine Hymn"))



# --- the run, on Postgres (skipped without TEST_DATABASE_URL) ----------------------------------

_PG_URL = os.getenv("TEST_DATABASE_URL", "")


@pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"), reason="the eval run needs a migrated Postgres with pgvector"
)
async def test_eval_run_reports_recall_and_latency_per_mode(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.db import session as db_session

    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    try:
        report = await harness.run(maker, k=8)
    finally:
        await engine.dispose()
    print(report)  # visible with -s: the numbers the write-up quotes
    assert report["questions"] == len(harness.load_questions())
    assert set(report["modes"]) == {"hybrid", "vector", "keyword"}
    for numbers in report["modes"].values():
        assert 0.0 <= numbers["recall"] <= 1.0 and numbers["p95_ms"] >= numbers["p50_ms"] > 0
    assert report["modes"]["hybrid"]["recall"] > 0.5  # the harness finds the labelled chunks
    if harness.is_real(report["set"]):  # SC-004: asserted only on recorded real embeddings
        assert report["modes"]["hybrid"]["recall"] >= report["modes"]["vector"]["recall"]


# --- the live mode's pure helpers (the live calls themselves are team-lead's) -------------------


def test_without_variant_drops_only_the_search_first_clause():
    from backend.evals.kb.live import strip_search_first
    from wcl_agent.agent import INSTRUCTION

    stripped = strip_search_first(INSTRUCTION)
    assert "Local first:" in INSTRUCTION and "Local first:" not in stripped
    assert "search_knowledge" not in stripped
    assert "Plan the evidence before the first lookup" in stripped
    assert len(INSTRUCTION) - len(stripped) < 600


def test_filter_accuracy_compares_resolved_values():
    from backend.evals.kb.live import filter_matches

    expected = {"kind": "wcl", "class_name": "Warrior", "encounter": "Ula'tek", "character": "Vagxsu"}
    assert filter_matches({"kind": "wcl", "class_name": "warr", "encounter": "ulatek", "character": "vagxsu"}, expected) == (4, 4)
    assert filter_matches({"kind": "guide", "class_name": "nonsense"}, expected) == (0, 4)


async def test_record_refuses_without_an_embedder(monkeypatch, capsys):
    from backend.app.kb import embedder
    from backend.evals.kb import live

    monkeypatch.setattr(embedder, "get_embedder", lambda: None)
    assert await live.record() == 2
    assert "nothing recorded" in capsys.readouterr().out
    assert not harness.EMBEDDINGS.exists()
