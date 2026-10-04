"""Background spec-guide lifecycle (feature 005 / US6; feature 008 / US2-US3).

The character flow now resolves ``(class, spec)``, persists it, and feeds the SHARED
``spec_guides`` library (no per-character guide content). Generation is spawned off-loop,
so tests drain the background tasks before asserting.
"""

from __future__ import annotations

import asyncio
import uuid

from backend.app.db import session as db_session
from backend.app.db import repository as repo
from backend.app.services import guide


async def _drain_bg() -> None:
    """Await any background generation tasks spawned by ensure_spec_guide."""
    for _ in range(100):
        tasks = [t for t in list(guide._bg_tasks) if not t.done()]
        if not tasks:
            return
        await asyncio.gather(*tasks)


async def test_character_resolves_spec_and_triggers_shared_guide(
    session_factory, tenant_id, monkeypatch
):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_resolve(name, server, region):
        return ("Shaman", "Enhancement")

    async def fake_gen(prompt):
        return "## Rotation\nStormstrike on cooldown."

    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)
    monkeypatch.setattr(guide, "_generate_text", fake_gen)

    async with session_factory() as s:
        char = await repo.upsert_self(
            s, tenant_id=tenant_id, name="Thrall", server="Stormrage", region="US"
        )
        await s.commit()
        cid = char.id

    await guide.run_character_guide(cid, tenant_id)
    await _drain_bg()

    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        # Spec persisted on the character…
        assert c.class_name == "Shaman"
        assert c.active_spec == "Enhancement"
        # …and the guide lives in the shared library, ready.
        g = await repo.get_spec_guide(s, class_name="Shaman", spec="Enhancement")
        assert g is not None
        assert g.status == "ready"
        assert g.guide_markdown


async def test_unresolvable_character_gets_no_spec_or_guide(
    session_factory, tenant_id, monkeypatch
):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_resolve(name, server, region):
        return None

    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)

    async with session_factory() as s:
        char = await repo.add_friend(
            s, tenant_id=tenant_id, name="Bogus", server="Nowhere", region="US"
        )
        await s.commit()
        cid = char.id

    await guide.run_character_guide(cid, tenant_id)
    await _drain_bg()

    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        assert c is not None  # entry still saved (FR-030)
        assert c.active_spec is None
        assert await repo.list_spec_guides(s) == []


async def test_empty_generation_marks_spec_guide_failed(
    session_factory, tenant_id, monkeypatch
):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_resolve(*a):
        return ("Mage", "Frost")

    async def empty_gen(prompt):
        return ""

    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)
    monkeypatch.setattr(guide, "_generate_text", empty_gen)

    async with session_factory() as s:
        char = await repo.upsert_self(
            s, tenant_id=tenant_id, name="Jaina", server="Proudmoore", region="US"
        )
        await s.commit()
        cid = char.id

    await guide.run_character_guide(cid, tenant_id)
    await _drain_bg()

    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        assert c.active_spec == "Frost"  # spec still persisted
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Frost")
        assert g is not None and g.status == "failed"  # retryable, never stuck


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
