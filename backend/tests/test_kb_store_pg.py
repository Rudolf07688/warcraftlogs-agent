"""The knowledge base tables on real Postgres + pgvector (feature 043, sc-111, migration 0019):
extension version, keyword config per kind, a vector query, delete cascades, and the chat
chunks' RLS and composite conversation key, all as the runtime role.

Skipped unless ``TEST_DATABASE_URL`` points at a migrated ``pgvector/pgvector:pg17`` (runtime
role). Recipe: specs/043-kb-store-embed/quickstart.md §2.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db.models import KB_DIMENSIONS, Conversation, KbChatChunk, KbChunk, RawFetch, SpecGuide
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories.raw_fetches import delete_report
from backend.app.tenancy.context import set_scope

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

NOW = datetime.now(UTC)


def unit(i: int) -> list[float]:
    vector = [0.0] * KB_DIMENSIONS
    vector[i] = 1.0
    return vector


def fresh() -> str:
    return uuid.uuid4().hex[:16]  # the database outlives one run


@pytest.fixture
async def pg():
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def tenants(pg) -> tuple[uuid.UUID, uuid.UUID]:
    async with pg() as db:
        a = await tenants_repo.create_tenant(db, name="kb-043-a")
        b = await tenants_repo.create_tenant(db, name="kb-043-b")
        await db.commit()
    return a.id, b.id


async def add_fetch(pg, code: str) -> str:
    key = uuid.uuid4().hex + uuid.uuid4().hex
    async with pg() as db:
        db.add(RawFetch(query_key=key, params={"code": code}, report_code=code, report_codes=[code],
                        fetched_at=NOW, payload={"data": {}}))
        await db.commit()
    return key


async def add_guide(pg) -> uuid.UUID:
    async with pg() as db:
        guide = SpecGuide(class_name=f"C{fresh()}", spec="Arms", content_type="raid")
        db.add(guide)
        await db.commit()
    return guide.id


async def add_conversation(pg, tenant: uuid.UUID) -> uuid.UUID:
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        conv = Conversation(tenant_id=tenant, model="m")
        db.add(conv)
        await db.commit()
    return conv.id


def chat_chunk(tenant: uuid.UUID, conv: uuid.UUID, seq: int = 2) -> KbChatChunk:
    return KbChatChunk(tenant_id=tenant, conversation_id=conv, message_seq=seq, created_at=NOW,
                       label="q", text="Question: running build?\n\nAnswer: …", content_hash="h")


async def count(pg, model, *where, tenant: uuid.UUID | None = None) -> int:
    async with pg() as db:
        if tenant is not None:
            await set_scope(db, tenant_id=tenant)
        return await db.scalar(sa.select(sa.func.count()).select_from(model).where(*where))


async def test_extension_is_at_least_0_8(pg):
    async with pg() as db:
        version = await db.scalar(sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    assert tuple(int(p) for p in version.split(".")[:2]) >= (0, 8)


async def test_keyword_config_is_simple_for_wcl_and_english_for_guides(pg):
    code, guide_id = fresh(), await add_guide(pg)
    fetch_key = await add_fetch(pg, code)
    async with pg() as db:
        db.add(KbChunk(kind="wcl", raw_fetch_id=fetch_key, chunk_key="fight:1", label="l",
                       text="Running fights", content_hash="h", report_code=code))
        db.add(KbChunk(kind="guide", guide_id=guide_id, chunk_key="section:0", label="l",
                       text="Running fights", content_hash="h"))
        await db.commit()
        rows = dict((await db.execute(
            sa.select(KbChunk.kind, sa.cast(KbChunk.tsv, sa.Text)).where(
                sa.or_(KbChunk.raw_fetch_id == fetch_key, KbChunk.guide_id == guide_id)
            )
        )).all())
    assert "'running'" in rows["wcl"] and "'fights'" in rows["wcl"]  # no stemming
    assert "'run'" in rows["guide"] and "'fight'" in rows["guide"]  # English stems


async def test_cosine_query_orders_by_vector(pg):
    code = fresh()
    fetch_key = await add_fetch(pg, code)
    async with pg() as db:
        for i in range(3):
            db.add(KbChunk(kind="wcl", raw_fetch_id=fetch_key, chunk_key=f"fight:{i}", label="l",
                           text=f"t{i}", content_hash="h", report_code=code, embedding=unit(i)))
        await db.commit()
        await db.execute(sa.text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        keys = (await db.scalars(
            sa.select(KbChunk.chunk_key).where(KbChunk.report_code == code)
            .order_by(KbChunk.embedding.cosine_distance(unit(2))).limit(2)
        )).all()
    assert keys[0] == "fight:2"


async def test_deleting_a_fetch_or_a_report_or_a_guide_deletes_its_chunks(pg):
    code, gone_code = fresh(), fresh()
    fetch_key, gone_key, guide_id = await add_fetch(pg, code), await add_fetch(pg, gone_code), await add_guide(pg)
    async with pg() as db:
        for key, c in ((fetch_key, code), (gone_key, gone_code)):
            db.add(KbChunk(kind="wcl", raw_fetch_id=key, chunk_key="fight:1", label="l", text="t",
                           content_hash="h", report_code=c))
        db.add(KbChunk(kind="guide", guide_id=guide_id, chunk_key="section:0", label="l", text="t",
                       content_hash="h"))
        await db.commit()
    async with pg() as db:
        await db.execute(sa.delete(RawFetch).where(RawFetch.query_key == fetch_key))
        await delete_report(db, gone_code)  # the 039 "report gone / private" path
        await db.execute(sa.delete(SpecGuide).where(SpecGuide.id == guide_id))
        await db.commit()
    assert await count(pg, KbChunk, KbChunk.raw_fetch_id.in_([fetch_key, gone_key])) == 0
    assert await count(pg, KbChunk, KbChunk.guide_id == guide_id) == 0


async def test_deleting_a_conversation_deletes_its_chat_chunks(pg, tenants):
    a, _ = tenants
    conv = await add_conversation(pg, a)
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        db.add(chat_chunk(a, conv))
        await db.commit()
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        await db.execute(sa.delete(Conversation).where(Conversation.id == conv))
        await db.commit()
    assert await count(pg, KbChatChunk, KbChatChunk.conversation_id == conv, tenant=a) == 0


async def test_another_workspace_sees_none_of_the_chat_chunks(pg, tenants):
    a, b = tenants
    conv = await add_conversation(pg, a)
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        db.add(chat_chunk(a, conv))
        await db.commit()
    assert await count(pg, KbChatChunk, KbChatChunk.conversation_id == conv, tenant=a) == 1
    # No tenant predicate on purpose: RLS alone must hide A's chunk from B and from no scope.
    assert await count(pg, KbChatChunk, KbChatChunk.conversation_id == conv, tenant=b) == 0
    assert await count(pg, KbChatChunk, KbChatChunk.conversation_id == conv) == 0


async def test_a_workspace_cannot_insert_a_chunk_with_another_workspaces_tenant_id(pg, tenants):
    a, b = tenants
    conv = await add_conversation(pg, a)
    async with pg() as db:
        await set_scope(db, tenant_id=b)
        db.add(chat_chunk(a, conv))
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.commit()


async def test_a_workspace_cannot_attach_its_chunk_to_another_workspaces_conversation(pg, tenants):
    a, b = tenants
    conv = await add_conversation(pg, a)
    async with pg() as db:
        await set_scope(db, tenant_id=b)
        db.add(chat_chunk(b, conv))  # its own tenant id, A's conversation: FK checks skip RLS
        with pytest.raises(IntegrityError, match="fk_kb_chat_chunks_conversation"):
            await db.commit()


async def test_an_unscoped_chat_chunk_insert_is_refused(pg, tenants):
    a, _ = tenants
    conv = await add_conversation(pg, a)
    async with pg() as db:
        db.add(chat_chunk(a, conv))
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.commit()


async def test_backfill_iterator_reads_keys_and_bodies_on_postgres(pg):
    from backend.app.repositories.raw_fetches import list_fetch_keys, load_fetch_for_index

    code = fresh()
    key = await add_fetch(pg, code)
    async with pg() as db:
        keys = await list_fetch_keys(db, after=key[:-1], limit=5, summaries=False)
        row = await load_fetch_for_index(db, key)
    assert key in keys
    assert row.report_codes == [code] and row.body.startswith(b"{")


async def test_a_foreign_conversation_fails_on_the_fk_even_when_its_seq_is_taken(pg, tenants):
    """P7 SEC-001: the unique key leads with the tenant, so B learns nothing about A's chat."""
    a, b = tenants
    conv = await add_conversation(pg, a)
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        db.add(chat_chunk(a, conv, seq=2))
        await db.commit()
    async with pg() as db:
        await set_scope(db, tenant_id=b)
        db.add(chat_chunk(b, conv, seq=2))
        with pytest.raises(IntegrityError, match="fk_kb_chat_chunks_conversation"):
            await db.commit()


@pytest.mark.parametrize("move", ["tenant", "conversation"])
async def test_an_update_cannot_move_a_chat_chunk_to_another_workspace(pg, tenants, move):
    """P7 (f): neither the tenant id nor the conversation can be rewritten across workspaces."""
    a, b = tenants
    conv_a, conv_b = await add_conversation(pg, a), await add_conversation(pg, b)
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        db.add(chat_chunk(a, conv_a))
        await db.commit()
    values = {"tenant_id": b} if move == "tenant" else {"conversation_id": conv_b}
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        with pytest.raises((DBAPIError, IntegrityError)):
            await db.execute(sa.update(KbChatChunk).where(KbChatChunk.conversation_id == conv_a).values(**values))
            await db.commit()
    assert await count(pg, KbChatChunk, KbChatChunk.conversation_id == conv_a, tenant=a) == 1


async def test_deleting_a_workspace_deletes_its_chat_chunks(pg):
    async with pg() as db:
        tenant = (await tenants_repo.create_tenant(db, name="kb-043-gone")).id
        await db.commit()
    conv = await add_conversation(pg, tenant)
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        db.add(chat_chunk(tenant, conv))
        await db.commit()
    async with pg() as db:
        await db.execute(sa.text("DELETE FROM tenants WHERE id = :t"), {"t": tenant})
        await db.commit()
    assert await count(pg, KbChatChunk, KbChatChunk.tenant_id == tenant, tenant=tenant) == 0


# --- the indexer through the 039 writer (sc-112 AC7) ------------------------------------------


class _Unit:
    model = "fake-embed"

    async def embed(self, texts, *, task):
        return [unit(0) for _ in texts]


def summary_fetched(code: str):
    import json as _json

    from wcl_agent.client.queries import REPORT_SUMMARY
    from wcl_agent.client.wcl_client import FetchedResponse, _flight_key

    report = {"code": code, "visibility": "public", "title": "t", "startTime": 1_760_000_000_000,
              "masterData": {"actors": []},
              "fights": [{"id": 1, "name": "Boss", "encounterID": 3001, "difficulty": 4, "kill": True}]}
    body = _json.dumps({"data": {"reportData": {"report": report}}}).encode()
    return FetchedResponse(_flight_key(REPORT_SUMMARY, {"code": code}), REPORT_SUMMARY, {"code": code}, body, NOW)


def _job(fetched, code: str):
    from backend.app.kb.indexer import FetchJob

    return FetchJob(fetched.query_key, fetched.query, fetched.variables, (code,))


@pytest.fixture
async def app_db(pg, monkeypatch):
    from backend.app.db import session as db_session
    from backend.app.kb.embedder import set_embedder

    monkeypatch.setattr(db_session, "SessionLocal", pg)
    set_embedder(_Unit())
    yield pg
    set_embedder(None)


async def test_a_stored_fetch_is_indexed_and_a_gone_report_takes_its_chunks(app_db):
    from backend.app.kb.indexer import KbIndexer
    from backend.app.services.fetch_persistence import PendingWrite, store_batch
    from wcl_agent.client.wcl_client import ReportGone

    code = fresh()
    fetched = summary_fetched(code)
    result = await store_batch([PendingWrite(fetched, None)])
    assert result.changed == [fetched]
    await KbIndexer(max_items=5, batch=8, sweep_s=600).handle(_job(fetched, code))
    assert await count(app_db, KbChunk, KbChunk.report_code == code, KbChunk.embedding.is_not(None)) == 1
    await store_batch([PendingWrite(ReportGone((code,), NOW), None)])
    assert await count(app_db, KbChunk, KbChunk.report_code == code) == 0


async def test_an_index_job_for_a_fetch_that_is_already_gone_writes_nothing(app_db):
    from backend.app.kb.indexer import KbIndexer

    code = fresh()
    fetched = summary_fetched(code)  # never stored: nothing to read, nothing written
    await KbIndexer(max_items=5, batch=8, sweep_s=600).handle(_job(fetched, code))
    assert await count(app_db, KbChunk, KbChunk.raw_fetch_id == fetched.query_key) == 0
