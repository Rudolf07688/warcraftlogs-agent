"""The knowledge search eval (feature 044, sc-115 AC2): fixture integrity and metrics on SQLite."""

from __future__ import annotations

import math

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

