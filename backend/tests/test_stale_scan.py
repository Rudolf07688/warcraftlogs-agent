"""Guides stay current: staleness, the in-use rule, regenerate on open (feature 015, US10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import guide
from backend.app.services.guide_pipeline import briefing as briefing_mod
from wcl_agent.cache.cache_models import HotfixEntry, HotfixFeed

NOW = datetime.now(UTC)


def reason(**over):
    base = dict(content_type="raid", class_name="Mage", spec="Fire", game_patch="12.1.5", season=None,
                generated_at=NOW - timedelta(days=3), current_reason=None, live_patch="12.1.5",
                live_season="Mythic+ Season 2", hotfix_at=None, hotfix_touches=False)
    base.update(over)
    return guide.compute_stale_reason(**base)


def test_compute_stale_reason():
    assert reason() is None
    assert reason(live_patch="12.1.7") == "patch_changed"  # patch-level change, exact compare
    assert reason(game_patch="12.1", live_patch="12.1.7") is None  # major.minor only: same
    assert reason(game_patch="12.0", live_patch="12.1") == "patch_changed"
    assert reason(content_type="mplus", season="Mythic+ Season 1") == "season_changed"
    assert reason(season="Mythic+ Season 1") is None  # season only matters for Mythic+
    assert reason(hotfix_at=NOW - timedelta(days=1), hotfix_touches=True) == "hotfix"
    assert reason(hotfix_at=NOW - timedelta(days=9), hotfix_touches=True) is None  # older than the guide
    assert reason(hotfix_at=NOW, hotfix_touches=False) is None
    assert reason(current_reason="legacy", live_patch="12.2.0") == "legacy"


@pytest.fixture
def live(monkeypatch, session_factory):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def version():
        return None

    async def feed():
        return HotfixFeed(latest_at=NOW - timedelta(hours=1), entries=[
            HotfixEntry(date=None, class_name="Priest", specs=[]),  # the whole class
            HotfixEntry(date=None, class_name="Druid", specs=["Guardian"]),
        ])

    async def patch():
        return "12.1"

    async def season():
        return "Mythic+ Season 2"

    monkeypatch.setattr(briefing_mod, "fetch_live_version", version)
    monkeypatch.setattr(briefing_mod, "fetch_hotfix_feed", feed)
    monkeypatch.setattr(guide, "current_patch", patch)
    monkeypatch.setattr(guide, "current_mplus_season", season)
    regenerated = []

    async def ensure(class_name, spec, content_type="raid", *, force=False):
        regenerated.append((class_name, spec, content_type, force))

    monkeypatch.setattr(guide, "ensure_guide", ensure)
    return regenerated


async def _row(s, cls, spec, ct="raid", **over):
    fields = dict(status="ready", guide_markdown="# g", game_patch="12.1",
                  generated_at=NOW - timedelta(days=2), last_wanted_at=None)
    fields.update(over)
    await repo.upsert_spec_guide(s, class_name=cls, spec=spec, content_type=ct, **fields)


async def test_scan_marks_and_regenerates_only_guides_in_use(live, session_factory):
    async with session_factory() as s:
        await _row(s, "Mage", "Fire", game_patch="12.0", last_wanted_at=NOW - timedelta(days=1))
        await _row(s, "Mage", "Frost", game_patch="12.0")  # stale, but nobody uses it
        await _row(s, "Mage", "Fire", "mplus", season="Mythic+ Season 1", last_wanted_at=NOW)
        await _row(s, "Priest", "Holy")  # class-wide hotfix after generation
        await _row(s, "Druid", "Guardian")  # spec-specific hotfix
        await _row(s, "Druid", "Balance")  # same class, untouched spec
        await _row(s, "Rogue", "Outlaw", stale_reason="legacy")
        await _row(s, "Shaman", "Elemental", status="pending", game_patch="12.0", last_wanted_at=NOW)
        await _row(s, "Warrior", "Arms", status="failed", guide_markdown=None, game_patch=None)
        await s.commit()
    assert await guide.scan_stale_guides() == 6
    async with session_factory() as s:
        rows = {(g.class_name, g.spec, g.content_type): g.stale_reason for g in await repo.list_spec_guides(s)}
    assert rows[("Mage", "Fire", "raid")] == "patch_changed"
    assert rows[("Mage", "Frost", "raid")] == "patch_changed"
    assert rows[("Mage", "Fire", "mplus")] == "season_changed"
    assert rows[("Priest", "Holy", "raid")] == "hotfix"
    assert rows[("Druid", "Guardian", "raid")] == "hotfix"
    assert rows[("Druid", "Balance", "raid")] is None
    assert rows[("Rogue", "Outlaw", "raid")] == "legacy"
    assert rows[("Shaman", "Elemental", "raid")] == "patch_changed"
    assert rows[("Warrior", "Arms", "raid")] is None  # nothing published to go stale
    # Only stale guides in use (wanted within 14 days) and not already running regenerate.
    assert sorted(live) == [("Mage", "Fire", "mplus", True), ("Mage", "Fire", "raid", True)]


def test_scan_is_throttled(monkeypatch):
    started = []
    monkeypatch.setattr(guide, "spawn", lambda coro, key: (started.append(key), coro.close()))
    monkeypatch.setattr(guide, "_last_scan", None)
    guide.maybe_scan_stale_guides()
    guide.maybe_scan_stale_guides()  # within 10 minutes: no-op
    assert started == ["stale-scan"]


def test_wanted_stamp_is_throttled_per_guide(monkeypatch):
    started = []
    monkeypatch.setattr(guide, "spawn", lambda coro, key: (started.append(key), coro.close()))
    guide.touch_guide_wanted([("Mage", "Fire", "raid")])
    guide.touch_guide_wanted([("Mage", "Fire", "raid")])  # within the hour: no-op
    guide.touch_guide_wanted([("Mage", "Fire", "raid"), ("Mage", "Fire", "mplus")])
    assert len(started) == 2


async def test_wanted_stamp_writes_last_wanted_at(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    async with session_factory() as s:
        await _row(s, "Mage", "Fire")
        await s.commit()
    guide.touch_guide_wanted([("Mage", "Fire", "raid")])
    from backend.app.services import background
    import asyncio

    await asyncio.gather(*[t for t in background._bg_tasks if not t.done()])
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.last_wanted_at is not None


async def test_opening_a_stale_guide_queues_regeneration(as_user, session_factory, monkeypatch):
    from backend.app.api import guides as guides_api

    queued = []

    async def ensure(class_name, spec, content_type="raid", *, force=False):
        queued.append((class_name, spec, content_type))

    monkeypatch.setattr(guides_api, "ensure_guide", ensure)
    async with session_factory() as s:
        await _row(s, "Mage", "Fire", stale_reason="hotfix")
        await _row(s, "Mage", "Frost")
        await _row(s, "Mage", "Arcane", status="pending", stale_reason="hotfix")
        await s.commit()
    for spec in ("Fire", "Frost", "Arcane"):
        assert (await as_user.client.get(f"/api/guides/Mage/{spec}/raid")).status_code == 200
    assert queued == [("Mage", "Fire", "raid")]


# --- QA fixes: backoff, wave cap, abandoned runs (SPEC-002, BUG-002, BUG-003, PERF-001/002) ---


async def _age(s, cls, spec, ct="raid", *, hours):
    from sqlalchemy import update

    from backend.app.db.models import SpecGuide

    await s.execute(
        update(SpecGuide)
        .where(SpecGuide.class_name == cls, SpecGuide.spec == spec, SpecGuide.content_type == ct)
        .values(updated_at=NOW - timedelta(hours=hours))
    )


async def test_held_or_failed_runs_back_off(live, session_factory):
    async with session_factory() as s:
        await _row(s, "Mage", "Fire", status="needs_review", game_patch="12.0", last_wanted_at=NOW)
        await _row(s, "Mage", "Frost", status="failed", game_patch="12.0", last_wanted_at=NOW,
                   failure_reason="no_supported_claims")
        await _row(s, "Mage", "Arcane", status="failed", game_patch="12.0", last_wanted_at=NOW)
        await _row(s, "Priest", "Shadow", status="failed", game_patch="12.0", last_wanted_at=NOW,
                   failure_reason="wcl_budget")
        await _age(s, "Mage", "Fire", hours=2)
        await _age(s, "Mage", "Frost", hours=2)
        await _age(s, "Mage", "Arcane", hours=30)  # the backoff has passed
        await s.commit()
    await guide.scan_stale_guides()
    assert sorted(k[:2] for k in live) == [("Mage", "Arcane"), ("Priest", "Shadow")]


async def test_a_scan_starts_at_most_three_regenerations(live, session_factory):
    async with session_factory() as s:
        for n, spec in enumerate(["Arcane", "Fire", "Frost"]):
            await _row(s, "Mage", spec, game_patch="12.0", last_wanted_at=NOW - timedelta(hours=n))
        for n, spec in enumerate(["Holy", "Shadow"]):
            await _row(s, "Priest", spec, game_patch="12.0", last_wanted_at=NOW - timedelta(days=2 + n))
        await s.commit()
    await guide.scan_stale_guides()
    assert [k[1] for k in live] == ["Arcane", "Fire", "Frost"]  # the most recently wanted


async def test_abandoned_pending_is_recovered(live, session_factory):
    async with session_factory() as s:
        await _row(s, "Mage", "Fire", status="pending", game_patch="12.0", last_wanted_at=NOW)
        await _row(s, "Mage", "Frost", status="pending", game_patch="12.0", last_wanted_at=NOW)
        await _age(s, "Mage", "Fire", hours=2)  # interrupted long ago
        await s.commit()
    await guide.scan_stale_guides()
    assert [k[:2] for k in live] == [("Mage", "Fire")]  # Frost is genuinely running


async def test_ensure_guide_restarts_an_abandoned_run(session_factory, monkeypatch):
    from backend.tests.guide_fakes import fake_pipeline

    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls = []
    fake_pipeline(monkeypatch, "# recovered", calls)
    async with session_factory() as s:
        await _row(s, "Mage", "Fire", status="pending", guide_markdown=None)
        await _row(s, "Mage", "Frost", status="pending", guide_markdown=None)
        await _age(s, "Mage", "Fire", hours=2)
        await s.commit()
    await guide.ensure_guide("Mage", "Fire")
    await guide.ensure_guide("Mage", "Frost")  # in flight: still deduplicated
    from backend.app.services import background
    import asyncio

    await asyncio.gather(*[t for t in background._bg_tasks if not t.done()])
    assert calls == [("Mage", "Fire", "raid")]


def test_open_regeneration_respects_the_backoff():
    class Row:
        def __init__(self, status, hours, reason=None):
            self.status, self.failure_reason, self.stale_reason = status, reason, "hotfix"
            self.updated_at, self.brief, self.guide_markdown = NOW - timedelta(hours=hours), {"x": 1}, "# g"

    assert guide.stale_and_idle(Row("ready", 1)) is True
    assert guide.stale_and_idle(Row("needs_review", 1)) is False
    assert guide.stale_and_idle(Row("failed", 48)) is True
    assert guide.stale_and_idle(Row("pending", 0.25)) is False  # still running
    assert guide.stale_and_idle(Row("pending", 3)) is True


async def test_a_crashing_run_is_recorded_as_failed(session_factory, monkeypatch):
    from backend.app.services import guide_pipeline as pipeline

    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def boom(*a):
        raise RuntimeError("database hiccup during publish")

    monkeypatch.setattr(pipeline, "_run", boom)
    outcome = await pipeline.run_guide_generation("Mage", "Fire", "raid")
    assert outcome.outcome == "failed" and outcome.reason == "internal_error"
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.status == "failed" and g.failure_reason == "internal_error"
