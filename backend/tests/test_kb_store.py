"""Knowledge base chunk tables on SQLite (feature 043, sc-111): the models build, rows round-trip
and the source constraints hold. Postgres specifics (RLS, cascades, pgvector, tsvector) are in
test_kb_store_pg.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.db.models import KB_DIMENSIONS, Conversation, KbChatChunk, KbChunk, RawFetch, SpecGuide

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def unit(i: int) -> list[float]:
    vector = [0.0] * KB_DIMENSIONS
    vector[i] = 1.0
    return vector


async def seed_sources(session) -> tuple[str, uuid.UUID]:
    session.add(RawFetch(query_key="k" * 64, params={}, report_codes=["ABC"], fetched_at=NOW, payload={}))
    guide = SpecGuide(class_name="Warrior", spec="Arms", content_type="raid")
    session.add(guide)
    await session.flush()
    return "k" * 64, guide.id


def chunk(**kw) -> KbChunk:
    base = dict(chunk_key="fight:1", label="fight 1 summary", text="Report ABC, fight 1", content_hash="h")
    return KbChunk(**{**base, **kw})


async def test_chunks_round_trip_with_vector_and_filters(session):
    fetch_key, guide_id = await seed_sources(session)
    session.add(
        chunk(
            kind="wcl", raw_fetch_id=fetch_key, embedding=unit(3), embed_model="m", embedded_at=NOW,
            report_code="ABC", fight_id=1, encounter_id=3012, difficulty=4, kill=True,
            players=[{"name": "Vagxsu", "key": "vagxsu", "class": "Warrior", "spec": "Arms"}],
            extra={"metric": "DamageDone"},
        )
    )
    session.add(chunk(kind="guide", guide_id=guide_id, chunk_key="section:0", class_name="Warrior", spec="Arms"))
    await session.commit()

    wcl = await session.scalar(select(KbChunk).where(KbChunk.kind == "wcl"))
    assert wcl.embedding == unit(3)
    assert wcl.players[0]["key"] == "vagxsu" and wcl.extra == {"metric": "DamageDone"}
    guide = await session.scalar(select(KbChunk).where(KbChunk.kind == "guide"))
    assert guide.embedding is None and guide.class_name == "Warrior"


@pytest.mark.parametrize(
    "kw",
    [
        {"kind": "wcl"},  # no source
        {"kind": "guide", "raw_fetch_id": "k" * 64},  # guide pointing at a fetch
        {"kind": "chat", "raw_fetch_id": "k" * 64},  # not a kind of this table
    ],
)
async def test_a_chunk_must_name_exactly_its_own_kind_of_source(session, kw):
    await seed_sources(session)
    session.add(chunk(**kw))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_chunk_keys_are_unique_per_source(session):
    fetch_key, _ = await seed_sources(session)
    session.add_all([chunk(kind="wcl", raw_fetch_id=fetch_key), chunk(kind="wcl", raw_fetch_id=fetch_key)])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_chat_chunk_round_trips_and_is_unique_per_message(session, tenant_id):
    conv = Conversation(tenant_id=tenant_id, model="m")
    session.add(conv)
    await session.flush()
    session.add(
        KbChatChunk(
            tenant_id=tenant_id, conversation_id=conv.id, message_seq=2, created_at=NOW,
            characters=[{"name": "Vagxsu", "key": "vagxsu"}], label="my arms build",
            text="Question: my arms build?\n\nAnswer: …", content_hash="h",
        )
    )
    await session.commit()
    row = await session.scalar(select(KbChatChunk))
    assert (row.conversation_id, row.message_seq, row.embedding) == (conv.id, 2, None)

    session.add(
        KbChatChunk(
            tenant_id=tenant_id, conversation_id=conv.id, message_seq=2, created_at=NOW,
            label="again", text="t", content_hash="h2",
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
