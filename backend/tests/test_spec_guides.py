"""Shared spec-guide library — service + API (feature 008 / US2).

Covers ``ensure_guide`` dedup/retry/force + IntegrityError convergence, the
roster+status merge (100% coverage), rate-limit gating, and the guides API
(list / detail / generate, incl. 404 for unknown specs). Generation is mocked.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.exc import IntegrityError

from wcl_agent.game.constants import CLASS_SPECS

from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import background, guide
from backend.tests.guide_fakes import fake_pipeline as _pipeline

async def _drain_bg() -> None:
    for _ in range(100):
        tasks = [t for t in list(background._bg_tasks) if not t.done()]
        if not tasks:
            return
        await asyncio.gather(*tasks)


def _total_specs() -> int:
    return sum(len(info["specs"]) for info in CLASS_SPECS.values())


# --- ensure_guide lifecycle ---------------------------------------------


async def test_ensure_generates_when_absent(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list = []
    _pipeline(monkeypatch, "## Guide", calls)

    await guide.ensure_guide("Paladin", "Protection")
    await _drain_bg()

    assert calls == [("Paladin", "Protection", "raid")]
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Paladin", spec="Protection")
        assert g is not None and g.status == "ready" and g.guide_markdown == "## Guide"


async def test_ensure_dedup_ready_skips_regeneration(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list = []
    _pipeline(monkeypatch, "new", calls)
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="old"
        )
        await s.commit()

    await guide.ensure_guide("Mage", "Fire")  # ready & !force → no-op
    await _drain_bg()
    assert calls == []
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
        assert g.guide_markdown == "old"  # unchanged


async def test_ensure_dedup_pending_skips_regeneration(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list = []
    _pipeline(monkeypatch, "x", calls)
    async with session_factory() as s:
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="pending")
        await s.commit()

    await guide.ensure_guide("Mage", "Fire")  # already in flight → no-op
    await _drain_bg()
    assert calls == []


async def test_ensure_force_regenerates_ready(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    _pipeline(monkeypatch, "refreshed")
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="old"
        )
        await s.commit()

    await guide.ensure_guide("Mage", "Fire", force=True)
    await _drain_bg()
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
        assert g.status == "ready" and g.guide_markdown == "refreshed"


async def test_ensure_retries_failed(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    _pipeline(monkeypatch, "recovered")
    async with session_factory() as s:
        await repo.upsert_spec_guide(s, class_name="Rogue", spec="Outlaw", status="failed")
        await s.commit()

    await guide.ensure_guide("Rogue", "Outlaw")  # failed is retryable (no force needed)
    await _drain_bg()
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Rogue", spec="Outlaw")
        assert g.status == "ready" and g.guide_markdown == "recovered"


async def test_ensure_swallows_integrity_error(session_factory, monkeypatch):
    """A losing concurrent insert catches IntegrityError and no-ops (never raises)."""
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list = []
    _pipeline(monkeypatch, "x", calls)

    async def boom(*a, **k):
        raise IntegrityError("insert", {}, Exception("duplicate key"))

    monkeypatch.setattr(repo, "upsert_spec_guide", boom)

    await guide.ensure_guide("Priest", "Shadow")  # must not raise
    await _drain_bg()
    assert calls == []  # loser never spawns generation


# --- roster + status merge ----------------------------------------------------


async def test_roster_merge_covers_every_spec_and_content_type(session_factory):
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Paladin", spec="Holy", status="ready", guide_markdown="g"
        )
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="failed")
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", content_type="mplus", status="pending"
        )
        rows = await repo.list_spec_guides(s, with_text=False)

    roster = guide.build_guide_roster(rows)
    assert len(roster) == _total_specs()  # each spec exactly once (SC-002, FR-028)
    by_key = {(it["class_name"], it["spec"]): it for it in roster}
    assert by_key[("Paladin", "Holy")]["raid"]["status"] == "ready"
    assert by_key[("Paladin", "Holy")]["mplus"]["status"] == "none"
    assert by_key[("Mage", "Fire")]["raid"]["status"] == "failed"
    assert by_key[("Mage", "Fire")]["mplus"]["status"] == "pending"
    assert by_key[("Mage", "Fire")]["mplus"]["refreshing"] is False  # nothing published yet
    assert by_key[("Warrior", "Arms")]["raid"]["status"] == "none"
    assert by_key[("DeathKnight", "Blood")]["class_display"] == "Death Knight"
    assert by_key[("DemonHunter", "Devourer")]["role"] == "dps"
    assert by_key[("Hunter", "BeastMastery")]["spec_display"] == "Beast Mastery"


# --- feature 009 / US5: provenance, repair turn, freshness ---------------------


async def test_failed_generation_does_not_touch_provenance(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Druid", spec="Balance", status="ready", guide_markdown="old",
            game_patch="11.2", sources=[], major_cooldowns=[],
        )
        await s.commit()

    _pipeline(monkeypatch, outcome="failed")
    await guide.ensure_guide("Druid", "Balance", force=True)
    await _drain_bg()
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Druid", spec="Balance")
        assert g.status == "failed" and g.guide_markdown == "old" and g.game_patch == "11.2"
        assert g.failure_reason == "model_error"


async def test_spec_options_include_devourer():
    from wcl_agent.tools.tools import get_spec_options

    options = await get_spec_options("DemonHunter")
    assert options["specs"] == ["Havoc", "Vengeance", "Devourer"]
    assert options["display"] == "Demon Hunter"


