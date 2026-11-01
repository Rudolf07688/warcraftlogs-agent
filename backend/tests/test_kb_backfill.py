"""Knowledge base backfill (feature 043, sc-113)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.app.db.models import RawFetch
from backend.app.repositories.raw_fetches import list_fetch_keys, load_fetch_for_index

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def raw(key: str, op: str | None, codes: list[str], payload: dict | None = None) -> RawFetch:
    return RawFetch(query_key=key, operation_name=op, params={"code": "X"}, report_codes=codes,
                    fetched_at=NOW, payload=payload or {"data": {"x": 1}})


async def test_fetch_keys_page_summaries_first_and_skip_rows_without_reports(session):
    session.add_all([
        raw("a1", "ReportSummary", ["A"]), raw("a2", "ReportsBatch", ["A", "B"]),
        raw("b1", "ReportQ", ["A"]), raw("b2", None, ["B"]), raw("c1", "CharRef", []),
    ])
    await session.commit()
    assert await list_fetch_keys(session, after=None, limit=10, summaries=True) == ["a1", "a2"]
    assert await list_fetch_keys(session, after=None, limit=10, summaries=False) == ["b1", "b2"]
    assert await list_fetch_keys(session, after="a1", limit=10, summaries=True) == ["a2"]
    assert await list_fetch_keys(session, after=None, limit=1, summaries=False) == ["b1"]


async def test_load_fetch_for_index_returns_the_stored_body(session):
    session.add(raw("k", "ReportQ", ["A"], {"data": {"reportData": {"report": {"table": {"data": {}}}}}}))
    await session.commit()
    row = await load_fetch_for_index(session, "k")
    assert (row.query_key, row.operation_name, row.report_codes) == ("k", "ReportQ", ["A"])
    assert json.loads(row.body) == {"data": {"reportData": {"report": {"table": {"data": {}}}}}}
    assert await load_fetch_for_index(session, "missing") is None


# --- the CLI (sc-113 AC1-AC4) -------------------------------------------------------------------

import uuid  # noqa: E402
from collections import Counter  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from backend.app.db import session as db_session  # noqa: E402
from backend.app.db.models import Conversation, KbChatChunk, KbChunk, Message, SpecGuide, Tenant  # noqa: E402
from backend.app.kb.embedder import DIMENSIONS, set_embedder  # noqa: E402
from backend.cli import kb_backfill  # noqa: E402
from backend.cli.kb_backfill import Options, exchanges  # noqa: E402

CODE = "BackfillCode1"


def summary_payload(fights: int) -> dict:
    return {"data": {"reportData": {"report": {
        "code": CODE, "title": "Old raid", "startTime": 1_760_000_000_000,
        "masterData": {"actors": [{"id": 1, "name": "Vagxsu", "subType": "Warrior"}]},
        "fights": [{"id": i, "name": f"Boss{i}", "encounterID": 3000 + i, "difficulty": 5, "kill": True,
                    "friendlyPlayers": [1], "startTime": 0} for i in range(1, fights + 1)],
    }}}}


class CountingEmbedder:
    """Counts each text it embedded successfully; ``fail_after`` calls raise (an interruption)."""

    model = "fake-embed"

    def __init__(self, fail_after: int | None = None):
        self.done: Counter[str] = Counter()
        self.calls = 0
        self.fail_after = fail_after

    async def embed(self, texts, *, task):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("interrupted")
        self.done.update(texts)
        return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]


@pytest.fixture
async def seeded(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    async with session_factory() as s:
        tenant = Tenant(name="w")
        s.add(tenant)
        await s.flush()
        s.add_all([
            raw("sum", "ReportSummary", [CODE], summary_payload(3)),
            # a stored DamageDone table: no query text, so its metric is unknown and it is skipped
            raw("tbl", "ReportQ", [CODE], {"data": {"reportData": {"report": {"table": {"data": {
                "entries": [{"name": "Vagxsu", "type": "Warrior", "icon": "Warrior-Arms", "total": 5}]}}}}}}),
            raw("deaths", "ReportQ", [CODE], {"data": {"reportData": {"report": {"table": {"data": {
                "entries": [{"name": "Vagxsu", "type": "Warrior", "deathTime": 1000}]}}}}}}),
            SpecGuide(class_name="Warrior", spec="Arms", content_type="raid", status="ready",
                      guide_markdown="## Rotation\nMortal Strike.\n\n## Cooldowns\nAvatar."),
            SpecGuide(class_name="Mage", spec="Fire", content_type="raid", status="pending"),  # unpublished
        ])
        conv = Conversation(tenant_id=tenant.id, model="m")
        s.add(conv)
        await s.flush()
        s.add_all([
            Message(tenant_id=tenant.id, conversation_id=conv.id, role="user", content="How did Vagxsu do?", seq=0),
            Message(tenant_id=tenant.id, conversation_id=conv.id, role="agent", content="Well.", seq=1),
            Message(tenant_id=tenant.id, conversation_id=conv.id, role="user", content="And now?", seq=2),
            Message(tenant_id=tenant.id, conversation_id=conv.id, role="agent", content="Cut o", seq=3, status="partial"),
        ])
        await s.commit()
    return session_factory


async def kb_counts(factory) -> tuple[int, int, int]:
    async with factory() as s:
        chunks = await s.scalar(select(func.count()).select_from(KbChunk))
        chats = await s.scalar(select(func.count()).select_from(KbChatChunk))
        embedded = await s.scalar(select(func.count()).select_from(KbChunk).where(KbChunk.embedding.is_not(None)))
    return chunks, chats, embedded


async def test_dry_run_prints_counts_and_cost_and_writes_nothing(seeded, capsys):
    embedder = CountingEmbedder()
    set_embedder(embedder)
    try:
        assert await kb_backfill.run(Options(("wcl", "guide", "chat"), confirm=False, limit=None)) == 0
    finally:
        set_embedder(None)
    out = capsys.readouterr().out
    assert "wcl: 2 sources, 4 new chunks" in out  # 3 fights + the Deaths table; the DamageDone table skipped
    assert "guide: 1 sources, 2 new chunks" in out
    assert "chat: 1 sources, 1 new chunks" in out  # the partial answer is not an exchange
    assert "~USD" in out and "Nothing written" in out
    assert await kb_counts(seeded) == (0, 0, 0) and embedder.calls == 0


async def test_confirmed_run_resumes_after_an_interruption_and_embeds_each_chunk_once(seeded, monkeypatch):
    monkeypatch.setattr(kb_backfill.settings, "kb_embed_batch", 2)
    first = CountingEmbedder(fail_after=1)
    set_embedder(first)
    try:
        options = Options(("wcl", "guide", "chat"), confirm=True, limit=None)
        assert await kb_backfill.run(options) == 1  # interrupted
        chunks, chats, embedded = await kb_counts(seeded)
        assert (chunks, chats, embedded) == (6, 1, 2)
        second = CountingEmbedder()
        set_embedder(second)
        assert await kb_backfill.run(options) == 0
        assert await kb_counts(seeded) == (6, 1, 6)
        stored = first.done + second.done
        assert sum(stored.values()) == 7 and set(stored.values()) == {1}  # every chunk exactly once
        third = CountingEmbedder()
        set_embedder(third)
        assert await kb_backfill.run(options) == 0 and third.calls == 0  # idempotent
    finally:
        set_embedder(None)
    async with seeded() as s:
        [chat] = list(await s.scalars(select(KbChatChunk)))
    assert chat.message_seq == 1 and chat.text == "Question: How did Vagxsu do?\n\nAnswer: Well."


async def test_limit_caps_new_sources_per_kind(seeded, capsys):
    await kb_backfill.run(Options(("wcl",), confirm=False, limit=1))
    assert "wcl: 1 sources" in capsys.readouterr().out


def test_exchanges_pair_questions_with_complete_answers():
    def m(role, seq, status="complete"):
        return Message(tenant_id=uuid.uuid4(), conversation_id=uuid.uuid4(), role=role, content=str(seq), seq=seq, status=status)

    pairs = exchanges([m("user", 0), m("agent", 1), m("user", 2), m("agent", 3, "partial"), m("user", 4), m("user", 5), m("agent", 6)])
    assert [(q.seq, a.seq) for q, a in pairs] == [(0, 1), (5, 6)]


def test_unknown_kinds_are_refused():
    with pytest.raises(SystemExit):
        kb_backfill.parse_args(["--kinds", "wcl,files"])
