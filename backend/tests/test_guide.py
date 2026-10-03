"""Background spec-guide lifecycle (feature 005 / US6, tenant-scoped feature 006)."""

from __future__ import annotations

import asyncio
import uuid

from backend.app.db import session as db_session
from backend.app.db import repository as repo
from backend.app.services import guide


async def test_guide_lifecycle_pending_to_ready(session_factory, tenant_id, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_resolve(name, server, region):
        return ("Shaman", "Enhancement")

    async def fake_gen(prompt):
        return "## Rotation\nStormstrike on cooldown."

    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)
    monkeypatch.setattr(guide, "_generate_text", fake_gen)

    async with session_factory() as s:
        char = await repo.upsert_self(s, tenant_id=tenant_id, name="Thrall", server="Stormrage", region="US")
        await s.commit()
        cid = char.id
        assert char.guide_status == "pending"

    await guide.run_character_guide(cid, tenant_id)

    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        assert c.guide_status == "ready"
        assert c.class_name == "Shaman"
        assert c.active_spec == "Enhancement"
        assert c.guide_markdown
        assert c.guide_updated_at is not None


async def test_guide_failed_but_entry_saved_on_unresolvable(session_factory, tenant_id, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_resolve(name, server, region):
        return None

    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)

    async with session_factory() as s:
        char = await repo.add_friend(s, tenant_id=tenant_id, name="Bogus", server="Nowhere", region="US")
        await s.commit()
        cid = char.id

    await guide.run_character_guide(cid, tenant_id)

    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        assert c is not None  # entry still saved (FR-030)
        assert c.guide_status == "failed"
        assert c.guide_markdown is None


async def test_guide_failed_when_generation_returns_empty(session_factory, tenant_id, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_resolve(*a):
        return ("Mage", "Frost")

    async def empty_gen(prompt):
        return ""

    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)
    monkeypatch.setattr(guide, "_generate_text", empty_gen)

    async with session_factory() as s:
        char = await repo.upsert_self(s, tenant_id=tenant_id, name="Jaina", server="Proudmoore", region="US")
        await s.commit()
        cid = char.id

    await guide.run_character_guide(cid, tenant_id)

    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        assert c.guide_status == "failed"
        assert c.active_spec == "Frost"


async def test_schedule_is_idempotent_while_in_flight(monkeypatch, tenant_id):
    calls = {"n": 0}
    release = asyncio.Event()

    async def counted(char_id, tid):
        calls["n"] += 1
        await release.wait()

    monkeypatch.setattr(guide, "run_character_guide", counted)
    cid = uuid.uuid4()
    guide.schedule_character_guide(cid, tenant_id)
    guide.schedule_character_guide(cid, tenant_id)  # deduped while the first is in flight
    await asyncio.sleep(0.01)
    try:
        assert calls["n"] == 1
        assert cid in guide._inflight
    finally:
        release.set()
        await asyncio.sleep(0.01)
    assert cid not in guide._inflight
