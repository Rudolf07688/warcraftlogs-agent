"""Knowledge search on real Postgres + pgvector (feature 044, sc-114): the SQL legs, the hybrid
ranking, and the visibility rules with the P7 bypass attempts, all as the runtime role.

Skipped unless ``TEST_DATABASE_URL`` points at a migrated ``pgvector/pgvector:pg17-trixie``
(runtime role). Recipe: specs/044-kb-search/quickstart.md.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db import session as db_session
from backend.app.db.models import Conversation, KbChatChunk, KbChunk, RawFetch, SpecGuide
from backend.app.kb import search as kb
from backend.app.kb.search import SearchFilters, SearchRequest
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories.raw_fetches import (
    ReportStatus,
    delete_report,
    grant_codes,
    record_report_status,
)
from backend.app.tenancy.context import set_scope
from backend.evals.kb.standin import StandInEmbedder, embed_one

_PG_URL = os.getenv("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="Postgres tests require TEST_DATABASE_URL pointing at a migrated Postgres (runtime role).",
)

NOW = datetime.now(UTC)
EMBEDDER = StandInEmbedder()


def fresh() -> str:
    return uuid.uuid4().hex[:16]  # the database outlives one run: unique codes and words


@pytest.fixture
async def pg(monkeypatch):
    engine = create_async_engine(_PG_URL, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", maker)
    yield maker
    await engine.dispose()


@pytest.fixture
async def tenants(pg) -> tuple[uuid.UUID, uuid.UUID]:
    async with pg() as db:
        a = await tenants_repo.create_tenant(db, name="kb-044-a")
        b = await tenants_repo.create_tenant(db, name="kb-044-b")
        await db.commit()
    return a.id, b.id


async def add_fetch(pg, codes: list[str]) -> str:
    key = uuid.uuid4().hex + uuid.uuid4().hex
    async with pg() as db:
        db.add(RawFetch(query_key=key, params={}, report_code=codes[0] if len(codes) == 1 else None,
                        report_codes=codes, fetched_at=NOW, payload={"data": {}}))
        await db.commit()
    return key


async def set_status(pg, code: str, visibility: str, at: datetime = NOW) -> None:
    async with pg() as db:
        await record_report_status(db, [ReportStatus(code, visibility, None, at)])
        await db.commit()


async def grant(pg, tenant: uuid.UUID, code: str, at: datetime = NOW) -> None:
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        await grant_codes(db, tenant, [code], at)
        await db.commit()


async def add_wcl(pg, fetch_key: str, code: str, text: str, *, embed=True, **columns) -> None:
    async with pg() as db:
        db.add(KbChunk(kind="wcl", raw_fetch_id=fetch_key, chunk_key=f"k{fresh()}",
                       label=columns.pop("label", "fight 1 summary"), text=text, content_hash="h",
                       report_code=code, fight_id=columns.pop("fight_id", 1),
                       embedding=embed_one(text) if embed else None, **columns))
        await db.commit()


async def add_guide(pg, text: str, *, class_name="Warrior", spec="Arms", embed=True) -> str:
    content_type = fresh()[:8]  # (class, spec, content_type) is unique and the DB outlives runs
    async with pg() as db:
        guide = SpecGuide(class_name=class_name, spec=spec, content_type=content_type)
        db.add(guide)
        await db.flush()
        db.add(KbChunk(kind="guide", guide_id=guide.id, chunk_key="section:0", label="Rotation",
                       text=text, content_hash="h", class_name=class_name, spec=spec,
                       content_type=content_type, section="Rotation",
                       embedding=embed_one(text) if embed else None))
        await db.commit()
    return content_type


async def add_chat(pg, tenant: uuid.UUID, text: str, *, characters=(), at: datetime = NOW) -> str:
    async with pg() as db:
        await set_scope(db, tenant_id=tenant)
        conv = Conversation(tenant_id=tenant, model="m")
        db.add(conv)
        await db.flush()
        db.add(KbChatChunk(tenant_id=tenant, conversation_id=conv.id, message_seq=2, created_at=at,
                           label="q", text=text, content_hash="h", embedding=embed_one(text),
                           characters=[{"name": c, "key": c.lower()} for c in characters]))
        await db.commit()
    return str(conv.id)


async def search(tenant: uuid.UUID, *queries: str, embedder=EMBEDDER, k=8, hard=(), **filters):
    request = SearchRequest(tuple(queries), SearchFilters(**filters), frozenset(hard), k, tenant)
    return await kb.search(request, embedder=embedder)


def codes_of(result) -> set[str]:
    return {h.source.get("report_code") for h in result.hits if h.kind == "wcl"}


def convs_of(result) -> set[str]:
    return {h.source.get("conversation_id") for h in result.hits if h.kind == "chat"}


# --- guides and chats -----------------------------------------------------------------------


async def test_guide_hit_has_a_compact_source_pointer(pg, tenants):
    word = fresh()
    content_type = await add_guide(pg, f"Arms Warrior opener {word}: Charge, Avatar, Colossus Smash.")
    result = await search(tenants[0], f"arms opener {word}", kind="guide")
    hit = next(h for h in result.hits if h.source["content_type"] == content_type)
    assert hit.kind == "guide" and result.mode == "hybrid"
    assert hit.source == {"class_name": "Warrior", "spec": "Arms", "content_type": content_type, "section": "Rotation"}
    assert len(hit.text) <= kb.HIT_TEXT_CHARS


async def test_a_chunk_without_an_embedding_is_found_by_keyword(pg, tenants):
    word = fresh()
    content_type = await add_guide(pg, f"Pending chunk {word} awaiting its vector", embed=False)
    for embedder in (EMBEDDER, None):
        result = await search(tenants[0], word, embedder=embedder, kind="guide")
        assert content_type in {h.source["content_type"] for h in result.hits}
    assert result.mode == "keyword_only"


async def test_both_legs_contribute(pg, tenants):
    word = fresh()
    async with pg() as db:  # Monk guides belong to this test; the database outlives runs
        await db.execute(sa.delete(SpecGuide).where(SpecGuide.class_name == "Monk"))
        await db.commit()
    # a keyword-only match (no vector) and a vector-close chunk without the word
    kw = await add_guide(pg, f"{word} Overpower builds Martial Prowess", class_name="Monk", spec="Windwalker", embed=False)
    vec = await add_guide(pg, "Mortal Strike Execute Overpower Colossus Smash rotation priority", class_name="Monk", spec="Windwalker")
    result = await search(
        tenants[0], f"{word} Mortal Strike Execute Overpower Colossus Smash rotation", kind="guide",
        class_name="Monk", hard={"class_name"}, k=15,
    )
    found = {h.source["content_type"] for h in result.hits}
    assert {kw, vec} <= found


async def test_own_chat_is_found_and_another_workspaces_never(pg, tenants):
    a, b = tenants
    word = fresh()
    conv = await add_chat(pg, a, f"User: opener {word}? Agent: Avatar before Colossus Smash.", characters=["Vagxsu"])
    assert conv in convs_of(await search(a, f"opener {word}"))
    assert conv in convs_of(await search(a, f"opener {word}", kind="chat", character_key="vagxsu"))
    # workspace B: no filter combination reaches A's chat
    for filters in ({}, {"kind": "chat"}, {"character_key": "vagxsu"}, {"since": NOW - timedelta(days=1)}):
        assert conv not in convs_of(await search(b, f"opener {word}", **filters)), filters


async def test_rls_alone_hides_another_workspaces_chat(pg, tenants):
    """The runner adds a tenant predicate; RLS must hold without it (defence in depth)."""
    a, b = tenants
    await add_chat(pg, a, f"secret {fresh()}")
    async with pg() as db:
        await set_scope(db, tenant_id=b)
        assert await db.scalar(sa.select(sa.func.count()).select_from(KbChatChunk).where(KbChatChunk.tenant_id == a)) == 0


async def test_deleted_conversation_never_returns(pg, tenants):
    a, _ = tenants
    word = fresh()
    conv = await add_chat(pg, a, f"User: {word}? Agent: yes.")
    async with pg() as db:
        await set_scope(db, tenant_id=a)
        await db.execute(sa.delete(Conversation).where(Conversation.id == uuid.UUID(conv)))
        await db.commit()
    assert conv not in convs_of(await search(a, word))


async def test_sql_fragments_in_queries_are_plain_text(pg, tenants):
    a, _ = tenants
    for query in ("'; DROP TABLE kb_chunks; --", "% _ * \\", "a & b | !c <-> d", "') OR 1=1 --"):
        result = await search(a, query)
        assert result.mode == "hybrid"
    async with pg() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(KbChunk)) >= 0


async def test_wildcard_filter_values_match_nothing(pg, tenants):
    a, _ = tenants
    code = fresh()
    await set_status(pg, code, "public")
    await add_wcl(pg, await add_fetch(pg, [code]), code, f"Report {code} fight 1 summary",
                  players=[{"name": "Vagxsu", "key": "vagxsu", "class": "Warrior", "spec": "Arms"}])
    for filters in ({"report_code": "%"}, {"character_key": "%"}, {"report_code": f"{code}%"}):
        assert code not in codes_of(await search(a, f"Report {code}", kind="wcl", **filters)), filters


async def test_soft_filter_relaxes_on_real_sql(pg, tenants):
    a, _ = tenants
    word = fresh()
    await add_guide(pg, f"{word} Holy Priest Divine Hymn", class_name="Priest", spec="Holy")
    # No test writes an Evoker guide, so the strict pass is empty and the class relaxes.
    result = await search(a, word, kind="guide", class_name="Evoker", k=1)
    assert result.relaxed == ["class_name"] and result.hits[0].relaxed
    stated = await search(a, word, kind="guide", class_name="Evoker", k=1, hard={"class_name"})
    assert stated.hits == [] and stated.relaxed == []


async def test_spec_only_filter_matches_every_class_with_the_spec(pg, tenants):
    a, _ = tenants
    word = fresh()
    paladin = await add_guide(pg, f"{word} holy healing", class_name="Paladin", spec="Holy")
    priest = await add_guide(pg, f"{word} holy healing", class_name="Priest", spec="Holy")
    druid = await add_guide(pg, f"{word} resto healing", class_name="Druid", spec="Restoration")
    result = await search(a, word, kind="guide", spec="Holy", hard={"spec"}, k=15)
    found = {h.source["content_type"] for h in result.hits}
    assert {paladin, priest} <= found and druid not in found


# --- WCL chunks: the 039 rule through fetch_visible_clause --------------------------------


async def test_public_and_granted_fetches_are_visible(pg, tenants):
    a, b = tenants
    public, granted = fresh(), fresh()
    await set_status(pg, public, "public")
    await set_status(pg, granted, "private")
    await grant(pg, a, granted)
    for code in (public, granted):
        await add_wcl(pg, await add_fetch(pg, [code]), code, f"Report {code} Heroic Ulatek kill")
    assert {public, granted} <= codes_of(await search(a, f"Report {public} {granted}", kind="wcl", k=15))
    seen_by_b = codes_of(await search(b, f"Report {public} {granted}", kind="wcl", k=15))
    assert public in seen_by_b and granted not in seen_by_b


@pytest.mark.parametrize("case", ["grant_expired", "turned_private", "status_stale", "row_gone", "other_tenant"])
async def test_a_fetch_that_is_no_longer_visible_returns_nothing(pg, tenants, case):
    a, b = tenants
    code = fresh()
    old = NOW - timedelta(days=30)
    if case == "grant_expired":
        await set_status(pg, code, "private")
        await grant(pg, a, code, at=old)
    elif case == "turned_private":
        await set_status(pg, code, "public", at=old)
        await set_status(pg, code, "private")
    elif case == "status_stale":
        await set_status(pg, code, "public", at=old)
    elif case == "other_tenant":
        await set_status(pg, code, "private")
        await grant(pg, b, code)
    else:
        await set_status(pg, code, "public")
    await add_wcl(pg, await add_fetch(pg, [code]), code, f"Report {code} Heroic Ulatek kill",
                  players=[{"name": "Vagxsu", "key": "vagxsu", "class": "Warrior", "spec": "Arms"}],
                  encounter_id=3101, difficulty=4, class_name="Warrior", spec="Arms", start_time=NOW)
    if case == "row_gone":
        async with pg() as db:
            await delete_report(db, code)
            await db.commit()
    combos = [
        {}, {"kind": "wcl"}, {"report_code": code}, {"character_key": "vagxsu"}, {"encounter_id": 3101},
        {"difficulty": 4}, {"class_name": "Warrior", "spec": "Arms"}, {"since": old, "until": NOW + timedelta(days=1)},
    ]
    for filters in combos:
        for embedder in (EMBEDDER, None):
            result = await search(a, f"Report {code} Heroic Ulatek kill", embedder=embedder, **filters)
            assert code not in codes_of(result), (case, filters)


async def test_a_multi_report_fetch_with_one_private_code_is_invisible(pg, tenants):
    """P7 SEC-002: kb_chunks hold private-report text; every code must be visible."""
    a, _ = tenants
    public, private = fresh(), fresh()
    await set_status(pg, public, "public")
    await set_status(pg, private, "private")
    await add_wcl(pg, await add_fetch(pg, [public, private]), public, f"Batch {public} {private}")
    assert public not in codes_of(await search(a, f"Batch {public} {private}", kind="wcl"))


async def test_a_fetch_naming_no_report_is_invisible(pg, tenants):
    """P7 SEC-002: rankings/character data has no report code, so it is never served."""
    a, _ = tenants
    word = fresh()
    await add_wcl(pg, await add_fetch(pg, []), word, f"Character rankings {word}")
    assert word not in codes_of(await search(a, f"Character rankings {word}", kind="wcl"))


async def test_wcl_filters_narrow_and_hits_point_at_the_fight(pg, tenants):
    a, _ = tenants
    code = fresh()
    await set_status(pg, code, "public")
    key = await add_fetch(pg, [code])
    await add_wcl(pg, key, code, f"Report {code} fight 12 Heroic Ula'tek kill", label="fight 12 summary",
                  fight_id=12, encounter_id=3101, difficulty=4,
                  players=[{"name": "Vagxsu", "key": "vagxsu", "class": "Warrior", "spec": "Arms"}])
    await add_wcl(pg, key, code, f"Report {code} fight 3 Mythic Ula'tek wipe", label="fight 3 summary",
                  fight_id=3, encounter_id=3101, difficulty=5)
    result = await search(a, f"Report {code} Ula'tek", report_code=code, difficulty=4)
    assert [h.source for h in result.hits if h.kind == "wcl"] == [
        {"report_code": code, "fight_id": 12, "label": "fight 12 summary"}
    ]
    by_player = await search(a, f"Report {code}", report_code=code, class_name="Warrior", spec="Arms", hard={"spec", "class_name"})
    assert {h.source["fight_id"] for h in by_player.hits if h.kind == "wcl"} == {12}


async def test_stopwords_do_not_match_every_wcl_chunk(pg, tenants):
    """P7 SEC-001: the 'simple' config keeps stopwords; the query side drops them."""
    a, _ = tenants
    code = fresh()
    await set_status(pg, code, "public")
    await add_wcl(pg, await add_fetch(pg, [code]), code, f"the boss of {code} is a wall", embed=False)
    hits = await search(a, "the of a is", embedder=None, kind="wcl", report_code=code)
    assert hits.hits == []
    found = await search(a, f"the {code}", embedder=None, kind="wcl", report_code=code)
    assert code in codes_of(found)
