"""Chat chunks on real Postgres (feature 043, sc-305 AC2-AC4): the indexer writes them under the
workspace's scope, mentions come from that workspace only, another workspace never sees them,
and deleting the conversation deletes them. Runtime role, RLS forced.

Skipped unless ``TEST_DATABASE_URL`` points at a migrated ``pgvector/pgvector:pg17-trixie``.
Recipe: specs/043-kb-store-embed/quickstart.md §2.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.db.models import KB_DIMENSIONS, Conversation, KbChatChunk, UserCharacter
from backend.app.kb.chat_chunker import ExchangeJob
from backend.app.kb.embedder import set_embedder
from backend.app.kb.indexer import KbIndexer
from backend.app.repositories import tenants as tenants_repo
from backend.app.tenancy.context import set_scope

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

NOW = datetime.now(UTC)


class _Unit:
    model = "fake-embed"

    async def embed(self, texts, *, task):
        return [[1.0] + [0.0] * (KB_DIMENSIONS - 1) for _ in texts]


class _Down:
    model = "down"

    async def embed(self, texts, *, task):
        raise RuntimeError("vertex down")


@pytest.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    set_embedder(_Unit())
    yield maker
    set_embedder(None)
    await engine.dispose()


@pytest.fixture
async def tenants(pg) -> tuple[uuid.UUID, uuid.UUID]:
    async with pg() as db:
        a = await tenants_repo.create_tenant(db, name="kb-chat-043-a")
        b = await tenants_repo.create_tenant(db, name="kb-chat-043-b")
        await db.commit()
    return a.id, b.id


async def scoped(pg, tenant: uuid.UUID | None, stmt):
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        return (await db.execute(stmt)).all()


async def conversation_with_friend(pg, tenant: uuid.UUID, friend: str) -> uuid.UUID:
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        conv = Conversation(tenant_id=tenant, model="m")
        db.add(conv)
        db.add(UserCharacter(tenant_id=tenant, role="friend", name=friend, server="s", region="EU",
                             class_name="Mage", active_spec="Fire"))
        await db.commit()
    return conv.id


async def test_the_indexer_writes_and_embeds_under_the_workspace_scope(pg, tenants):
    a, b = tenants
    conv = await conversation_with_friend(pg, a, "Zephyra")
    await conversation_with_friend(pg, b, "Quillon")  # B's friend: never A's mention
    job = ExchangeJob(a, conv, 1, "Did Zephyra or Quillon pull the boss?", "Zephyra did.", NOW)
    await KbIndexer(max_items=5, batch=8, sweep_s=600).handle(job)

    rows = await scoped(pg, a, sa.select(KbChatChunk.characters, KbChatChunk.embedding.is_not(None))
                        .where(KbChatChunk.conversation_id == conv))
    assert rows == [([{"name": "Zephyra", "key": "zephyra", "class": "Mage", "spec": "Fire"}], True)]
    # No tenant predicate: RLS alone hides it from B and from an unscoped session.
    assert await scoped(pg, b, sa.select(KbChatChunk.id).where(KbChatChunk.conversation_id == conv)) == []
    assert await scoped(pg, None, sa.select(KbChatChunk.id).where(KbChatChunk.conversation_id == conv)) == []


async def test_a_job_naming_another_workspaces_conversation_writes_nothing(pg, tenants):
    a, b = tenants
    conv_a = await conversation_with_friend(pg, a, "Zephyra")
    job = ExchangeJob(b, conv_a, 1, "q", "a", NOW)  # tenant B, A's conversation
    await KbIndexer(max_items=5, batch=8, sweep_s=600).handle(job)  # refused by the FK, never raises
    assert await scoped(pg, a, sa.select(KbChatChunk.id).where(KbChatChunk.conversation_id == conv_a)) == []
    assert await scoped(pg, b, sa.select(KbChatChunk.id).where(KbChatChunk.conversation_id == conv_a)) == []


async def test_deleting_the_conversation_deletes_its_chunks_and_the_sweep_embeds_per_workspace(pg, tenants):
    a, _ = tenants
    conv = await conversation_with_friend(pg, a, "Zephyra")
    set_embedder(_Down())  # embeddings down: the row stays keyword-only
    indexer = KbIndexer(max_items=5, batch=8, sweep_s=600)
    await indexer.handle(ExchangeJob(a, conv, 1, "q", "a", NOW))
    assert await scoped(pg, a, sa.select(KbChatChunk.embedding.is_(None)).where(KbChatChunk.conversation_id == conv)) == [(True,)]
    set_embedder(_Unit())
    await indexer.sweep()
    assert await scoped(pg, a, sa.select(KbChatChunk.embedding.is_(None)).where(KbChatChunk.conversation_id == conv)) == [(False,)]
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        await db.execute(sa.delete(Conversation).where(Conversation.id == conv))
        await db.commit()
    assert await scoped(pg, a, sa.select(KbChatChunk.id).where(KbChatChunk.conversation_id == conv)) == []


async def test_the_backfill_indexes_chats_per_workspace_under_its_scope(pg, tenants):
    """Gate 1 note (c): the runtime role can't bypass RLS, so the backfill scopes each workspace."""
    from backend.app.db.models import Message
    from backend.cli import kb_backfill

    a, _ = tenants
    conv = await conversation_with_friend(pg, a, "Zephyra")
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        db.add_all([
            Message(tenant_id=a, conversation_id=conv, role="user", content="Zephyra's parse?", seq=0),
            Message(tenant_id=a, conversation_id=conv, role="agent", content="95th percentile.", seq=1),
        ])
        await db.commit()
    await kb_backfill.run(kb_backfill.Options(("chat",), confirm=True, limit=None))
    rows = await scoped(pg, a, sa.select(KbChatChunk.message_seq, KbChatChunk.characters, KbChatChunk.embedding.is_not(None))
                        .where(KbChatChunk.conversation_id == conv))
    assert rows == [(1, [{"name": "Zephyra", "key": "zephyra", "class": "Mage", "spec": "Fire"}], True)]
