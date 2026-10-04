"""Auto-fetch reconciliation with the shared library (feature 008 / US3).

Characters derive their guide from the shared ``spec_guides`` store: auto-fetch on add
reuses a ready guide (zero regeneration, SC-004), removing a character leaves the shared
guide intact (FR-017), and ``CharacterOut.guide_status`` is derived from the library (FR-016).
"""

from __future__ import annotations

import asyncio

from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import guide


async def _drain_bg() -> None:
    for _ in range(100):
        tasks = [t for t in list(guide._bg_tasks) if not t.done()]
        if not tasks:
            return
        await asyncio.gather(*tasks)


async def test_autofetch_reuses_ready_guide_with_zero_regeneration(
    session_factory, tenant_id, monkeypatch
):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    gen_calls: list[str] = []

    async def fake_gen(prompt):
        gen_calls.append(prompt)
        return "md"

    async def fake_resolve(*a):
        return ("Shaman", "Enhancement")

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    monkeypatch.setattr(guide, "resolve_active_spec", fake_resolve)

    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Shaman", spec="Enhancement", status="ready", guide_markdown="existing"
        )
        char = await repo.add_friend(
            s, tenant_id=tenant_id, name="Thrall", server="Stormrage", region="US"
        )
        await s.commit()
        cid = char.id

    await guide.run_character_guide(cid, tenant_id)
    await _drain_bg()

    assert gen_calls == []  # reused the ready shared guide — zero regeneration (SC-004)
    async with session_factory() as s:
        c = await repo.get_character(s, cid, tenant_id=tenant_id)
        assert c.class_name == "Shaman" and c.active_spec == "Enhancement"
        g = await repo.get_spec_guide(s, class_name="Shaman", spec="Enhancement")
        assert g.guide_markdown == "existing"  # untouched


async def test_removing_character_keeps_shared_guide(session_factory, tenant_id):
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="g"
        )
        f = await repo.add_friend(
            s, tenant_id=tenant_id, name="Jaina", server="Proudmoore", region="US"
        )
        await repo.set_character_spec(
            s, f.id, tenant_id=tenant_id, class_name="Mage", active_spec="Fire"
        )
        await s.commit()
        fid = f.id

    async with session_factory() as s:
        assert await repo.delete_friend(s, fid, tenant_id=tenant_id) is True
        await s.commit()

    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
        assert g is not None and g.status == "ready"  # shared guide survives (FR-017)


async def test_character_out_guide_status_is_derived(as_user, session_factory, monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    tenant = as_user.tenant_id

    async with session_factory() as s:
        f = await repo.add_friend(
            s, tenant_id=tenant, name="Khadgar", server="Dalaran", region="US"
        )
        await repo.set_character_spec(
            s, f.id, tenant_id=tenant, class_name="Mage", active_spec="Arcane"
        )
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Arcane", status="ready", guide_markdown="g"
        )
        await s.commit()

    prof = (await as_user.client.get("/api/profile")).json()
    friend = next(fr for fr in prof["friends"] if fr["name"] == "Khadgar")
    assert friend["guide_status"] == "ready"  # derived from the shared library (FR-016)
    assert friend["guide_updated_at"] is not None


async def test_unresolved_character_guide_status_none(as_user, session_factory, monkeypatch):
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)
    tenant = as_user.tenant_id

    async with session_factory() as s:
        await repo.add_friend(
            s, tenant_id=tenant, name="Mystery", server="Server", region="US"
        )
        await s.commit()

    prof = (await as_user.client.get("/api/profile")).json()
    friend = next(fr for fr in prof["friends"] if fr["name"] == "Mystery")
    assert friend["guide_status"] == "none"  # unresolved spec ⇒ no guide
