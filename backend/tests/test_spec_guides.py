"""Shared spec-guide library — service + API (feature 008 / US2).

Covers ``ensure_spec_guide`` dedup/retry/force + IntegrityError convergence, the
roster+status merge (100% coverage), rate-limit gating, and the guides API
(list / detail / generate, incl. 404 for unknown specs). Generation is mocked.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from wcl_agent.constants import CLASS_SPECS

from backend.app.api import guides as guides_api
from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import guide


async def _drain_bg() -> None:
    for _ in range(100):
        tasks = [t for t in list(guide._bg_tasks) if not t.done()]
        if not tasks:
            return
        await asyncio.gather(*tasks)


def _total_specs() -> int:
    return sum(len(info["specs"]) for info in CLASS_SPECS.values())


# --- ensure_spec_guide lifecycle ---------------------------------------------


async def test_ensure_generates_when_absent(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list[str] = []

    async def fake_gen(prompt):
        calls.append(prompt)
        return "## Guide"

    monkeypatch.setattr(guide, "_generate_text", fake_gen)

    await guide.ensure_spec_guide("Paladin", "Protection")
    await _drain_bg()

    assert len(calls) == 1
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Paladin", spec="Protection")
        assert g is not None and g.status == "ready" and g.guide_markdown == "## Guide"


async def test_ensure_dedup_ready_skips_regeneration(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list[str] = []

    async def fake_gen(prompt):
        calls.append(prompt)
        return "new"

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="old"
        )
        await s.commit()

    await guide.ensure_spec_guide("Mage", "Fire")  # ready & !force → no-op
    await _drain_bg()
    assert calls == []
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
        assert g.guide_markdown == "old"  # unchanged


async def test_ensure_dedup_pending_skips_regeneration(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list[str] = []

    async def fake_gen(prompt):
        calls.append(prompt)
        return "x"

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    async with session_factory() as s:
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="pending")
        await s.commit()

    await guide.ensure_spec_guide("Mage", "Fire")  # already in flight → no-op
    await _drain_bg()
    assert calls == []


async def test_ensure_force_regenerates_ready(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_gen(prompt):
        return "refreshed"

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="old"
        )
        await s.commit()

    await guide.ensure_spec_guide("Mage", "Fire", force=True)
    await _drain_bg()
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
        assert g.status == "ready" and g.guide_markdown == "refreshed"


async def test_ensure_retries_failed(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_gen(prompt):
        return "recovered"

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    async with session_factory() as s:
        await repo.upsert_spec_guide(s, class_name="Rogue", spec="Outlaw", status="failed")
        await s.commit()

    await guide.ensure_spec_guide("Rogue", "Outlaw")  # failed is retryable (no force needed)
    await _drain_bg()
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Rogue", spec="Outlaw")
        assert g.status == "ready" and g.guide_markdown == "recovered"


async def test_ensure_swallows_integrity_error(session_factory, monkeypatch):
    """A losing concurrent insert catches IntegrityError and no-ops (never raises)."""
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list[str] = []

    async def fake_gen(prompt):
        calls.append(prompt)
        return "x"

    async def boom(*a, **k):
        raise IntegrityError("insert", {}, Exception("duplicate key"))

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    monkeypatch.setattr(repo, "upsert_spec_guide", boom)

    await guide.ensure_spec_guide("Priest", "Shadow")  # must not raise
    await _drain_bg()
    assert calls == []  # loser never spawns generation


# --- roster + status merge ----------------------------------------------------


async def test_roster_merge_covers_every_spec(session_factory):
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Paladin", spec="Holy", status="ready", guide_markdown="g"
        )
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="failed")
        rows = await repo.list_spec_guides(s)

    roster = guide.build_guide_roster(rows)
    assert len(roster) == _total_specs()  # 100% coverage (SC-002)
    by_key = {(it["class_name"], it["spec"]): it for it in roster}
    assert by_key[("Paladin", "Holy")]["status"] == "ready"
    assert by_key[("Mage", "Fire")]["status"] == "failed"
    assert by_key[("Warrior", "Arms")]["status"] == "none"  # no row ⇒ none
    # Every roster entry carries a human display name.
    assert by_key[("DeathKnight", "Blood")]["class_display"] == "Death Knight"


# --- guides API ---------------------------------------------------------------


async def test_list_guides_returns_full_roster(as_user):
    r = await as_user.client.get("/api/guides")
    assert r.status_code == 200, r.text
    guides = r.json()["guides"]
    assert len(guides) == _total_specs()
    assert all(g["status"] == "none" for g in guides)  # empty library


async def test_get_guide_detail_none_and_404(as_user):
    ok = await as_user.client.get("/api/guides/Paladin/Protection")
    assert ok.status_code == 200
    assert ok.json()["status"] == "none" and ok.json()["guide_markdown"] is None

    missing = await as_user.client.get("/api/guides/Bogus/Spec")
    assert missing.status_code == 404


async def test_generate_404_for_unknown_spec(as_user):
    r = await as_user.client.post("/api/guides/Bogus/Spec/generate", json={})
    assert r.status_code == 404


async def test_generate_rate_limited_returns_429(as_user, monkeypatch):
    monkeypatch.setattr(guides_api.guide_limiter, "allow_request", lambda key: False)
    r = await as_user.client.post("/api/guides/Paladin/Protection/generate", json={})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"  # reshaped by the error envelope
    assert r.headers.get("Retry-After")


async def test_generate_happy_path_returns_state(as_user, monkeypatch):
    seen = {}

    async def fake_ensure(class_name, spec, *, force=False):
        seen["args"] = (class_name, spec, force)

    monkeypatch.setattr(guides_api, "ensure_spec_guide", fake_ensure)
    r = await as_user.client.post(
        "/api/guides/Paladin/Protection/generate", json={"force": True}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_name"] == "Paladin" and body["spec"] == "Protection"
    assert body["status"] == "pending"  # no row yet → pending (generation in flight)
    assert seen["args"] == ("Paladin", "Protection", True)
