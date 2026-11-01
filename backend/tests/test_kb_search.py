"""Knowledge search without a database (feature 044, sc-114): validation, fusion, relaxation,
the output cap, the keyword fallback and the tool's fail-closed identity check. The SQL legs and
visibility are proved on Postgres in test_kb_search_pg.py."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.app.agent_tools import kb_tools
from backend.app.agent_tools.kb_tools import KB_TOOLS, search_knowledge
from backend.app.kb import search as kb
from backend.app.kb.search import (
    Candidate,
    SearchFilters,
    SearchRequest,
    SearchResult,
    Hit,
    cap,
    fuse,
    payload,
    truncate,
)
from backend.app.services import name_resolver as nr
from backend.app.tenancy.context import RequestIdentity, current_identity

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")


def cand(chunk_id: str, leg="keyword", rank=1, *, source=None, kind="guide", text=None) -> Candidate:
    key = source or (kind, chunk_id)
    return Candidate(
        chunk_id, kind, text or f"text of {chunk_id}", key, {"id": chunk_id}, leg, rank  # type: ignore[arg-type]
    )


def request(queries=("q",), *, filters=None, hard=(), k=8) -> SearchRequest:
    return SearchRequest(tuple(queries), filters or SearchFilters(), frozenset(hard), k, TENANT)


# --- fusion (AC2) -----------------------------------------------------------------------


def test_rrf_within_a_query_sums_both_legs():
    # a: vector 1 + keyword 3; b: keyword 1 only; c: vector 2 + keyword 2.
    query = [
        cand("a", "vector", 1), cand("c", "vector", 2),
        cand("b", "keyword", 1), cand("c", "keyword", 2), cand("a", "keyword", 3),
    ]
    scored = fuse([query])
    assert [s.candidate.chunk_id for s in scored] == ["a", "c", "b"]
    # one query: the cross-query RRF is over that query's fused rank
    assert scored[0].score == pytest.approx(1 / 61)
    assert scored[2].score == pytest.approx(1 / 63)


def test_rrf_across_queries_rewards_a_chunk_found_by_several_phrasings():
    q1 = [cand("x", rank=1), cand("y", rank=2)]
    q2 = [cand("z", rank=1), cand("y", rank=2)]
    scored = fuse([q1, q2])
    assert scored[0].candidate.chunk_id == "y"
    assert scored[0].score == pytest.approx(2 / 62)
    assert {s.candidate.chunk_id for s in scored} == {"x", "y", "z"}


def test_dedupe_by_source_keeps_the_best_chunk():
    same = ("wcl", "ABC", 32, "fight 32 summary")
    q = [cand("from-fetch-1", rank=1, source=same), cand("from-fetch-2", rank=2, source=same), cand("other", rank=3)]
    ids = [s.candidate.chunk_id for s in fuse([q])]
    assert ids == ["from-fetch-1", "other"]


def test_ties_break_on_chunk_id():
    assert [s.candidate.chunk_id for s in fuse([[cand("b")], [cand("a")]])] == ["a", "b"]


# --- the output (AC6) -------------------------------------------------------------------


def test_truncate_cuts_at_a_word_with_an_ellipsis():
    text = "word " * 200
    cut = truncate(text)
    assert len(cut) <= kb.HIT_TEXT_CHARS and cut.endswith("…") and "  " not in cut
    assert truncate("short  text") == "short text"


def test_cap_holds_at_max_k_with_maximal_chunks():
    big = "Ü" * 5000
    hits = [
        Hit("chat", {"conversation_id": str(uuid.uuid4()), "message_seq": i}, truncate(big), 0.0163)
        for i in range(kb.MAX_K)
    ]
    capped = cap(SearchResult(hits, "hybrid", ["spec", "class_name"], note=kb.KEYWORD_ONLY_NOTE))
    assert len(json.dumps(payload(capped), ensure_ascii=False)) <= kb.OUTPUT_CAP
    assert capped.capped is True and 0 < len(capped.hits) < kb.MAX_K
    assert capped.hits == hits[: len(capped.hits)]  # the lowest-ranked are the ones dropped


def test_small_result_is_not_capped():
    result = SearchResult([Hit("guide", {"section": "Rotation"}, "x", 0.01)], "hybrid", [])
    assert cap(result) is result
    assert payload(result) == {
        "status": "success", "mode": "hybrid", "relaxed": [], "capped": False, "note": None,
        "hits": [{"kind": "guide", "source": {"section": "Rotation"}, "text": "x", "score": 0.01}],
    }


# --- search orchestration -----------------------------------------------------------------


class FakeEmbedder:
    model = "fake"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[list[str], str]] = []

    async def embed(self, texts, *, task):
        self.calls.append((list(texts), task))
        if self.fail:
            raise RuntimeError("vertex down")
        return [[1.0] + [0.0] * 767 for _ in texts]


class FakeRunner:
    """Answers each pass from ``by_filters``: a function of the filters it is given."""

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[tuple[str, bool, SearchFilters, frozenset]] = []

    async def __call__(self, query, vector, filters, tenant_id, legs):
        assert tenant_id == TENANT
        self.calls.append((query, vector is not None, filters, legs))
        return self.answer(query, filters, legs)


async def test_queries_share_one_query_embedding_and_run_per_query():
    embedder = FakeEmbedder()
    runner = FakeRunner(lambda q, f, legs: [cand(f"{q}-1")])
    result = await kb.search(request(("a", "b", "c")), runner=runner, embedder=embedder)
    assert embedder.calls == [(["a", "b", "c"], "RETRIEVAL_QUERY")]
    assert sorted(c[0] for c in runner.calls) == ["a", "b", "c"]
    assert all(c[1] and c[3] == {"vector", "keyword"} for c in runner.calls)
    assert result.mode == "hybrid" and len(result.hits) == 3


async def test_queries_run_concurrently():
    import asyncio

    started: list[str] = []
    gate = asyncio.Event()

    async def runner(query, vector, filters, tenant_id, legs):
        started.append(query)
        if len(started) == 3:
            gate.set()
        await asyncio.wait_for(gate.wait(), 1)  # deadlocks unless all three run at once
        return [cand(query)]

    result = await kb.search(request(("a", "b", "c")), runner=runner, embedder=None)
    assert len(result.hits) == 3


@pytest.mark.parametrize("embedder", [None, FakeEmbedder(fail=True)])
async def test_keyword_only_when_embeddings_are_unavailable(embedder):
    runner = FakeRunner(lambda q, f, legs: [cand("g1")])
    result = await kb.search(request(), runner=runner, embedder=embedder)
    assert result.mode == "keyword_only"
    assert result.note == kb.KEYWORD_ONLY_NOTE
    assert runner.calls[0][1] is False and runner.calls[0][3] == {"keyword"}
    assert payload(result)["mode"] == "keyword_only"


async def test_eval_modes_run_one_leg():
    runner = FakeRunner(lambda q, f, legs: [cand("g1")])
    await kb.search(request(), runner=runner, embedder=FakeEmbedder(), mode="vector")
    await kb.search(request(), runner=runner, embedder=FakeEmbedder(), mode="keyword")
    assert [c[3] for c in runner.calls] == [{"vector"}, {"keyword"}]


async def test_no_hits_says_so():
    result = await kb.search(request(), runner=FakeRunner(lambda q, f, legs: []), embedder=FakeEmbedder())
    assert result.hits == [] and result.note == kb.NO_HITS_NOTE and result.relaxed == []


# --- relaxation (AC5) ---------------------------------------------------------------------

ALL_SOFT = SearchFilters(
    kind="wcl", report_code="ABC", class_name="Warrior", spec="Arms", encounter_id=3101,
    difficulty=4, character_key="vagxsu", since=datetime(2026, 10, 1, tzinfo=UTC),
)


def _strictness(f: SearchFilters) -> int:
    return len(f.soft_present())


async def test_soft_filters_relax_in_order_until_k_hits():
    # 4 soft filters present: 1 hit with all, 1 more after dropping spec, 6 more after class.
    def answer(q, f, legs):
        n = {4: 1, 3: 2, 2: 8, 1: 8, 0: 8}[_strictness(f)]
        return [cand(f"c{i}") for i in range(n)]

    runner = FakeRunner(answer)
    result = await kb.search(request(filters=ALL_SOFT, k=8), runner=runner, embedder=FakeEmbedder())
    assert result.relaxed == ["spec", "class_name"]
    assert [c[2].soft_present() for c in runner.calls] == [
        ["spec", "class_name", "encounter", "dates"],
        ["class_name", "encounter", "dates"],
        ["encounter", "dates"],
    ]
    kept = runner.calls[-1][2]
    # hard filters survive every pass
    assert (kept.kind, kept.report_code, kept.difficulty, kept.character_key) == ("wcl", "ABC", 4, "vagxsu")
    assert [h.relaxed for h in result.hits] == [False, True] + [True] * 6
    assert result.hits[0].source == {"id": "c0"}  # the strict hit ranks first


async def test_user_stated_filters_never_relax():
    runner = FakeRunner(lambda q, f, legs: [])
    result = await kb.search(
        request(filters=ALL_SOFT, hard={"spec", "encounter"}), runner=runner, embedder=FakeEmbedder()
    )
    final = runner.calls[-1][2]
    assert final.spec == "Arms" and final.encounter_id == 3101
    assert final.class_name is None and final.since is None
    assert result.relaxed == []  # nothing came back from a relaxed pass


async def test_relaxed_lists_only_drops_that_produced_hits():
    def answer(q, f, legs):
        return [cand("only")] if _strictness(f) <= 3 else []

    result = await kb.search(request(filters=ALL_SOFT), runner=FakeRunner(answer), embedder=FakeEmbedder())
    assert result.relaxed == ["spec"] and result.hits[0].relaxed is True


async def test_no_relaxation_when_k_is_met():
    runner = FakeRunner(lambda q, f, legs: [cand(f"c{i}") for i in range(8)])
    result = await kb.search(request(filters=ALL_SOFT), runner=runner, embedder=FakeEmbedder())
    assert len(runner.calls) == 1 and result.relaxed == []


def test_filter_without_and_pairs():
    f = SearchFilters(class_name="Paladin", spec="Holy", since=datetime(2026, 1, 1, tzinfo=UTC))
    assert f.pairs() == (nr.ClassSpec("Paladin", "Holy", "healer"),)
    assert {p.class_name for p in f.without("class_name").pairs()} == {"Paladin", "Priest"}
    assert f.without("spec").pairs() == ()
    assert f.without("dates").since is None


# --- the tool (AC1, AC4) ------------------------------------------------------------------


def _decl():
    from google.adk.tools.function_tool import FunctionTool

    return FunctionTool(search_knowledge)._get_declaration().parameters_json_schema


def _enum(prop: dict) -> list:
    schema = prop["anyOf"][0] if "anyOf" in prop else prop
    return (schema.get("items") or schema)["enum"]


def test_schema_has_the_enums():
    props = _decl()["properties"]
    assert _enum(props["kind"]) == ["wcl", "guide", "chat"]
    assert "Warrior" in _enum(props["class_name"]) and "DeathKnight" in _enum(props["class_name"])
    assert {"Arms", "BeastMastery", "Devourer"} <= set(_enum(props["spec"]))
    assert _enum(props["difficulty"]) == ["LFR", "Normal", "Heroic", "Mythic", "Mythic+"]
    assert _enum(props["user_stated"]) == ["spec", "class_name", "encounter", "dates"]
    assert _decl()["required"] == ["queries"]


def test_tool_group_line_fits_the_capability_budget():
    from wcl_agent.capabilities import MAX_TOOL_LINE_CHARS, _tool_line

    line = _tool_line(search_knowledge)
    assert line.startswith("- search_knowledge: Search stored knowledge first")
    assert len(line) <= MAX_TOOL_LINE_CHARS
    assert KB_TOOLS.tools == (search_knowledge,)


def _ctx(user_id: str | None = None):
    return SimpleNamespace(user_id=user_id or str(TENANT), session=SimpleNamespace(id=str(uuid.uuid4())))


@pytest.fixture
def identity():
    ident = RequestIdentity(uuid.uuid4(), TENANT, "owner", False, uuid.uuid4())
    token = current_identity.set(ident)
    yield ident
    current_identity.reset(token)


@pytest.fixture
def fake_search(monkeypatch):
    seen: list[SearchRequest] = []

    monkeypatch.setattr(kb_tools, "get_embedder", lambda: None)

    async def fake(req, *, embedder, runner=None, mode="hybrid"):
        seen.append(req)
        return SearchResult([Hit("guide", {"section": "Rotation"}, "x", 0.02)], "hybrid", [])

    monkeypatch.setattr(kb_tools.kb_search, "search", fake)
    return seen


async def test_fails_closed_outside_an_authenticated_turn(fake_search):
    result = await search_knowledge(["arms opener"], _ctx())
    assert result == {"status": "error", "error_message": "Knowledge search is unavailable in this session."}
    assert fake_search == []


async def test_fails_closed_when_the_session_belongs_to_another_tenant(identity, fake_search):
    result = await search_knowledge(["arms opener"], _ctx(user_id=str(uuid.uuid4())))
    assert result["status"] == "error" and fake_search == []


async def test_resolves_filters_into_canonical_values(identity, fake_search, patched_db, monkeypatch):
    async def zones():
        return [{"id": 46, "name": "Abyss", "encounters": [{"id": 3101, "name": "Ula'tek"}]}]

    monkeypatch.setattr(nr, "load_world_zones", zones)
    result = await search_knowledge(
        ["arms opener", "arms opener", "rotation"], _ctx(), kind="wcl", class_name="warr",
        spec="arms", encounter="heroic ulatek", report_code="BKNtypgnhrxXvj84",
        since="2026-10-01", until="2026-10-31", k=5, user_stated=["spec"],
    )
    assert result["status"] == "success"
    req = fake_search[0]
    assert req.queries == ("arms opener", "rotation") and req.k == 5 and req.tenant_id == TENANT
    f = req.filters
    assert (f.kind, f.class_name, f.spec, f.encounter_id, f.difficulty) == ("wcl", "Warrior", "Arms", 3101, 4)
    assert f.until == datetime(2026, 11, 1, tzinfo=UTC)  # a bare date includes that day
    assert req.hard == {"spec"}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"queries": []}, "1 to 5 queries"),
        ({"queries": ["a", "b", "c", "d", "e", "f"]}, "1 to 5 queries"),
        ({"queries": ["?!"]}, "needs words"),
        ({"queries": ["x" * 301]}, "at most 300"),
        ({"report_code": "%"}, "report_code"),
        ({"report_code": "ABC' OR 1=1 --"}, "report_code"),
        ({"report_code": "*"}, "report_code"),
        ({"report_code": "A" * 33}, "report_code"),
        ({"kind": "raw_fetches"}, "kind must be"),
        ({"k": 0}, "k must be"),
        ({"k": 16}, "k must be"),
        ({"since": "last week"}, "ISO date"),
        ({"since": "2026-10-10", "until": "2026-10-01"}, "before until"),
        ({"user_stated": ["kind"]}, "user_stated"),
        ({"class_name": "Warrior", "spec": "Holy"}, 'Unknown spec "Holy"'),
        ({"class_name": "%"}, 'Unknown class "%"'),
        ({"difficulty": "epic"}, "Unknown difficulty"),
    ],
)
async def test_bad_arguments_are_correctable_errors(identity, fake_search, patched_db, kwargs, message):
    args = {"queries": ["arms opener"], **kwargs}
    queries = args.pop("queries")
    result = await search_knowledge(queries, _ctx(), **args)
    assert result["status"] == "error"
    assert message in result["error_message"]
    assert fake_search == []  # nothing searched with an unresolved value


async def test_unknown_character_suggests_a_query_instead(identity, fake_search, patched_db):
    result = await search_knowledge(["deaths"], _ctx(), character="Nobodyhere")
    assert result["status"] == "error"
    assert 'Unknown character "Nobodyhere"' in result["error_message"]
    assert "put the name in a query" in result["error_message"]


async def test_search_failure_is_a_plain_error(identity, monkeypatch, patched_db):
    async def boom(*args, **kwargs):
        raise RuntimeError("db exploded: password=hunter2")

    monkeypatch.setattr(kb_tools.kb_search, "search", boom)
    monkeypatch.setattr(kb_tools, "get_embedder", lambda: None)
    result = await search_knowledge(["arms opener"], _ctx())
    assert result == {"status": "error", "error_message": "Knowledge search failed; use the Warcraft Logs tools."}


def test_only_the_kb_package_reads_the_chunk_tables():
    """P7 SEC-002: kb_chunks holds private-report text; the search runner (with the 039 rule)
    is the only read path for the agent, so nothing outside backend/app/kb touches the models."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path.parent != root / "kb"
        and path != root / "db" / "models.py"
        and re.search(r"\bKbChunk\b|\bKbChatChunk\b|(?i:\b(?:from|join)\s+kb_(?:chat_)?chunks\b)", path.read_text())
    ]
    assert offenders == []
