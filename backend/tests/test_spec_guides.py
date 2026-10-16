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
from backend.app.services import background, guide
from wcl_agent.guide_meta import clear_guide_meta, get_guide_meta

# Feature 009: generation returns GeneratedText; a valid trailing guide-meta block is
# appended so the stored markdown equals the given text (block stripped, no repair turn).
_META = (
    '\n\n```guide-meta\n{"patch": "12.1", "major_cooldowns": '
    '[{"name": "Combustion", "spell_id": 190319, "cooldown_s": 120}]}\n```'
)


def _gen(text: str) -> guide.GeneratedText:
    return guide.GeneratedText(text + _META if text else "", [], "sess")



async def _drain_bg() -> None:
    for _ in range(100):
        tasks = [t for t in list(background._bg_tasks) if not t.done()]
        if not tasks:
            return
        await asyncio.gather(*tasks)


def _total_specs() -> int:
    return sum(len(info["specs"]) for info in CLASS_SPECS.values())


# --- ensure_spec_guide lifecycle ---------------------------------------------


async def test_ensure_generates_when_absent(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list[str] = []

    async def fake_gen(prompt, session_id=None):
        calls.append(prompt)
        return _gen("## Guide")

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

    async def fake_gen(prompt, session_id=None):
        calls.append(prompt)
        return _gen("new")

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

    async def fake_gen(prompt, session_id=None):
        calls.append(prompt)
        return _gen("x")

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    async with session_factory() as s:
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="pending")
        await s.commit()

    await guide.ensure_spec_guide("Mage", "Fire")  # already in flight → no-op
    await _drain_bg()
    assert calls == []


async def test_ensure_force_regenerates_ready(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)

    async def fake_gen(prompt, session_id=None):
        return _gen("refreshed")

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

    async def fake_gen(prompt, session_id=None):
        return _gen("recovered")

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

    async def fake_gen(prompt, session_id=None):
        calls.append(prompt)
        return _gen("x")

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


# --- feature 009 / US5: provenance, repair turn, freshness ---------------------


async def test_success_persists_provenance_and_registry(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    clear_guide_meta()

    async def fake_gen(prompt, session_id=None):
        assert "guide-meta" in prompt and "Major cooldowns" in prompt  # authoring prompt
        return guide.GeneratedText(
            "# Fire" + _META, [{"title": "Wowhead", "uri": "https://example.test/fire"}], "sess-1"
        )

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    await guide.ensure_spec_guide("Mage", "Fire")
    await _drain_bg()

    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
        assert g.status == "ready" and g.guide_markdown == "# Fire"  # block stripped
        assert g.game_patch == "12.1" and g.generated_at is not None
        assert g.sources == [{"title": "Wowhead", "uri": "https://example.test/fire"}]
        assert g.major_cooldowns == [
            {"name": "Combustion", "spell_id": 190319, "cooldown_s": 120.0, "charges": 1,
             "talent_modified": False}
        ]
    meta = get_guide_meta("Mage", "Fire")
    assert meta is not None and meta.game_patch == "12.1"
    assert meta.cooldowns[0].spell_id == 190319 and meta.cooldowns[0].cooldown_s == 120.0


async def test_missing_block_triggers_one_repair_turn_on_same_session(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: list[tuple[str, str | None]] = []

    async def fake_gen(prompt, session_id=None):
        calls.append((prompt, session_id))
        if session_id is None:
            return guide.GeneratedText("# No block here", [], "sess-7")
        return guide.GeneratedText(
            '```guide-meta\n{"patch": "12.1", "major_cooldowns": []}\n```', [], session_id
        )

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    await guide.ensure_spec_guide("Mage", "Frost")
    await _drain_bg()

    assert len(calls) == 2
    assert calls[1] == (guide._GUIDE_META_REPAIR_PROMPT, "sess-7")  # same session, block only
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Frost")
        assert g.status == "ready" and g.guide_markdown == "# No block here"
        assert g.game_patch == "12.1" and g.major_cooldowns == []


async def test_failed_repair_leaves_metadata_null_but_guide_ready(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    clear_guide_meta()
    calls: list[str | None] = []

    async def fake_gen(prompt, session_id=None):
        calls.append(session_id)
        return guide.GeneratedText("# Still no block", [], session_id or "sess-9")

    monkeypatch.setattr(guide, "_generate_text", fake_gen)
    await guide.ensure_spec_guide("Rogue", "Subtlety")
    await _drain_bg()

    assert calls == [None, "sess-9"]  # exactly one repair attempt, never a third turn
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Rogue", spec="Subtlety")
        assert g.status == "ready" and g.guide_markdown == "# Still no block"
        assert g.game_patch is None and g.major_cooldowns is None
        assert g.sources == [] and g.generated_at is not None
    meta = get_guide_meta("Rogue", "Subtlety")
    assert meta is not None and meta.game_patch is None and meta.cooldowns == ()


async def test_failed_generation_does_not_touch_provenance(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Druid", spec="Balance", status="ready", guide_markdown="old",
            game_patch="11.2", sources=[], major_cooldowns=[],
        )
        await s.commit()

    async def empty_gen(prompt, session_id=None):
        return guide.GeneratedText("", [], "s")

    monkeypatch.setattr(guide, "_generate_text", empty_gen)
    await guide.ensure_spec_guide("Druid", "Balance", force=True)
    await _drain_bg()
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Druid", spec="Balance")
        assert g.status == "failed" and g.guide_markdown == "old" and g.game_patch == "11.2"


async def test_load_guide_registry_loads_ready_rows(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    clear_guide_meta()
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="g",
            game_patch="12.1", major_cooldowns=[{"name": "Combustion", "cooldown_s": 120}],
        )
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Frost", status="failed")
        await s.commit()
    assert await guide.load_guide_registry() == 1
    assert get_guide_meta("Mage", "Fire").cooldowns[0].name == "Combustion"
    assert get_guide_meta("Mage", "Frost") is None


def test_roster_freshness_only_for_ready_rows():
    class Row:
        def __init__(self, class_name, spec, status, game_patch):
            self.class_name, self.spec, self.status = class_name, spec, status
            self.game_patch, self.generated_at, self.updated_at = game_patch, None, None

    roster = guide.build_guide_roster(
        [Row("Mage", "Fire", "ready", "12.1"), Row("Mage", "Frost", "ready", None),
         Row("Mage", "Arcane", "ready", "11.2"), Row("Rogue", "Outlaw", "failed", "12.1")],
        current_patch="12.1",
    )
    by_key = {(it["class_name"], it["spec"]): it for it in roster}
    assert by_key[("Mage", "Fire")]["freshness"] == "current"
    assert by_key[("Mage", "Frost")]["freshness"] == "unknown"
    assert by_key[("Mage", "Arcane")]["freshness"] == "possibly_stale"
    assert by_key[("Rogue", "Outlaw")]["freshness"] is None  # not ready
    assert by_key[("Warrior", "Arms")]["freshness"] is None and by_key[("Warrior", "Arms")]["game_patch"] is None


async def test_api_exposes_freshness_and_sources(as_user, session_factory, monkeypatch):
    monkeypatch.setattr(guides_api, "current_patch", lambda: "12.1")
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="# Fire",
            game_patch="11.2", sources=[{"title": "Wowhead", "uri": "https://example.test/fire"}],
            major_cooldowns=[{"name": "Combustion", "cooldown_s": 120}],
        )
        await s.commit()

    listing = await as_user.client.get("/api/guides")
    assert listing.status_code == 200, listing.text
    fire = next(g for g in listing.json()["guides"] if g["class_name"] == "Mage" and g["spec"] == "Fire")
    assert fire["game_patch"] == "11.2" and fire["freshness"] == "possibly_stale"
    arms = next(g for g in listing.json()["guides"] if g["spec"] == "Arms")
    assert arms["freshness"] is None and arms["game_patch"] is None

    detail = await as_user.client.get("/api/guides/Mage/Fire")
    body = detail.json()
    assert body["freshness"] == "possibly_stale" and body["game_patch"] == "11.2"
    assert body["sources"] == [{"title": "Wowhead", "uri": "https://example.test/fire"}]
    assert "major_cooldowns" not in body  # internal coaching input, not exposed
