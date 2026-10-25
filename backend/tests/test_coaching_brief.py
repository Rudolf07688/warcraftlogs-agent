"""Coaching briefs: built by code from claims, rendered for the agent, loaded published-only
(feature 015, US2 — contracts/agent-context.md §1, data-model §4.6/§5)."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.config import settings
from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import guide
from backend.app.services.guide_pipeline.models import (
    DataSheet,
    GenerationBriefing,
    GuideClaim,
    ObservedAbility,
    SampleScope,
)
from backend.app.services.guide_pipeline.render import (
    build_brief,
    render_brief_text,
    render_guide_markdown,
)
from backend.tests.test_guide_meta import MENU_PAYLOAD
from backend.tests.wcl_fakes import install

BRIEFING = GenerationBriefing(
    now_utc=datetime(2026, 10, 18, tzinfo=UTC), content_type="raid", class_name="Mage",
    class_display="Mage", spec="Fire", role="dps", class_specs=["Arcane", "Fire", "Frost"],
    live_patch="12.1.5", raid_tier="The Venomous Abyss", mplus_season="Mythic+ Season 2",
)
SHEET = DataSheet(
    class_name="Mage", spec="Fire", content_type="raid",
    scope=SampleScope(zone_name="The Venomous Abyss", sample_size=24, metric="dps"),
    sufficient=True,
    abilities=[ObservedAbility(ability_id=190319, name="Combustion", casts_per_min_median=0.5)],
)


def _claim(n, section, text, **kw):
    base = {"id": f"c{n}", "section": section, "text": text, "evidence_refs": ["src:1"],
            "confidence": "high", "evidence_type": "guidance"}
    if section in {"mistakes", "uptimes", "cooldowns", "benchmarks"}:
        base["log_check"] = kw.pop("log_check", {"signal": "casts", "expectation": f"check {n}"})
    base.update(kw)
    return GuideClaim.model_validate(base)


CLAIMS = [
    _claim(1, "overview", "Fire builds Hot Streak from crits."),
    _claim(2, "priority", "Spend Hot Streak on Pyroblast at once."),
    _claim(3, "cooldowns", "Use Combustion on cooldown.", ability_name="Combustion", ability_id=190319,
           cooldown_s=120, charges=1,
           log_check={"signal": "cooldown_usage", "ability_id": 190319, "expectation": "about every 120 s"}),
    _claim(4, "cooldowns", "Use Shifting Power after Combustion.", ability_name="Shifting Power",
           ability_id=999999, cooldown_s=60),  # id not in the data sheet → dropped
    _claim(5, "mistakes", "Capping Fire Blast charges {wasted}.", evidence_type="observed",
           confidence="medium", log_check={"signal": "casts", "expectation": "Fire Blast never sits at 3 charges"}),
    _claim(6, "content_notes", "Save Combustion for the add phase."),
]


def test_build_brief_maps_sections_and_only_trusts_sheet_ability_ids():
    brief = build_brief(BRIEFING, CLAIMS, ["AoE priority"], SHEET)
    assert [i.claim_id for i in brief.priority] == ["c2"]
    assert [c.name for c in brief.cooldowns] == ["Combustion", "Shifting Power"]
    assert brief.cooldowns[0].ability_id == 190319 and brief.cooldowns[0].log_check.ability_id == 190319
    assert brief.cooldowns[1].ability_id is None  # FR-034: not in the data sheet
    assert [i.claim_id for i in brief.mistakes] == ["c5"] and brief.content_notes[0].claim_id == "c6"
    assert brief.unconfirmed == ["AoE priority"] and brief.data_sufficient is True
    assert brief.patch == "12.1.5" and brief.season is None
    assert build_brief(BRIEFING, CLAIMS, [], None).cooldowns[0].ability_id is None  # no sheet, no ids


def test_render_brief_text_golden():
    brief = build_brief(BRIEFING, CLAIMS, ["AoE priority"], SHEET)
    text = render_brief_text(brief, "current")
    assert text == "\n".join([
        "COACHING BRIEF — Fire Mage · Raid · patch 12.1.5 · generated 2026-10-18 · current",
        "Data: observed from 24 top logs (dps) in The Venomous Abyss, sufficient.",
        "Tags: [O]=observed in top logs [B]=benchmark [G]=guidance from current sources; conf H/M/L.",
        "",
        "PRIORITY (in order)",
        "1. [G,H] Spend Hot Streak on Pyroblast at once.",
        "",
        "MAJOR COOLDOWNS",
        "- Combustion (id 190319) 120 s ×1 — Use Combustion on cooldown. [G,H] LOG: cooldown_usage (id 190319): about every 120 s",
        "- Shifting Power 60 s ×1 — Use Shifting Power after Combustion. [G,H] LOG: casts: check 4",
        "",
        "COMMON MISTAKES (check in the log)",
        "- [O,M] Capping Fire Blast charges (wasted). LOG: casts: Fire Blast never sits at 3 charges",
        "",
        "BOSS NOTES",
        "- [G,H] Save Combustion for the add phase.",
        "",
        "NOT COVERED / UNCONFIRMED (no current source confirmed these; do not coach on them)",
        "- AoE priority",
    ])
    assert "{" not in text and "}" not in text
    assert len(text) <= settings.wcl_guide_brief_max_chars


def test_render_brief_header_freshness_season_and_thin_data():
    mplus = BRIEFING.model_copy(update={"content_type": "mplus"})
    thin = SHEET.model_copy(update={"sufficient": False})
    text = render_brief_text(build_brief(mplus, CLAIMS[:2], [], thin), "possibly_stale")
    first, data = text.splitlines()[:2]
    assert first == ("COACHING BRIEF — Fire Mage · Mythic+ · patch 12.1.5 · Mythic+ Season 2 · "
                     "generated 2026-10-18 · possibly stale — may be out of date")
    assert data.endswith("too small — numbers are context only.")
    assert "Data: no measured Warcraft Logs sample" in render_brief_text(build_brief(BRIEFING, CLAIMS[:2], []), "unknown")


def test_markdown_lists_what_the_coach_looks_for():
    md = render_guide_markdown(BRIEFING, CLAIMS)
    section = md.split("## What the coach looks for", 1)[1].split("##", 1)[0]
    for expectation in ("about every 120 s", "check 4", "Fire Blast never sits at 3 charges"):
        assert expectation in section


# --- the backend loader: published briefs only, cached, freshness-labelled ----------------


async def _store(session_factory, **over):
    brief = build_brief(BRIEFING, CLAIMS, [], SHEET).model_dump(mode="json")
    async with session_factory() as s:
        await repo.publish_spec_guide(
            s, class_name="Mage", spec="Fire", content_type="raid", markdown="# Fire", brief=brief,
            claims=[], game_patch=over.get("game_patch", "12.1"), season=None,
            generated_at=datetime(2026, 10, 18, tzinfo=UTC), sources=[], major_cooldowns=[],
            briefing=None, evidence=None,
        )
        await s.commit()


async def test_loader_returns_the_published_brief(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    install(monkeypatch, lambda q, v: MENU_PAYLOAD)
    guide.invalidate_brief_cache()
    await _store(session_factory)
    record = await guide.load_brief_record("mage", "fire", "raid")  # loose names resolve
    assert record.class_name == "Mage" and record.freshness == "current"
    assert record.text.startswith("COACHING BRIEF — Fire Mage · Raid")
    assert [c.name for c in record.cooldowns] == ["Combustion", "Shifting Power"]
    assert record.cooldowns[0].spell_id == 190319
    assert await guide.load_brief_record("Mage", "Fire", "mplus") is None  # never the other type


async def test_loader_never_returns_a_draft(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    install(monkeypatch, lambda q, v: MENU_PAYLOAD)
    guide.invalidate_brief_cache()
    async with session_factory() as s:
        await repo.hold_spec_guide(
            s, class_name="Mage", spec="Fire", content_type="raid",
            draft={"brief": build_brief(BRIEFING, CLAIMS, [], SHEET).model_dump(mode="json")},
            review_issues=[{"kind": "unconfirmed", "detail": "x"}],
        )
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Frost", status="ready", guide_markdown="# legacy, no brief"
        )
        await s.commit()
    assert await guide.load_brief_record("Mage", "Fire", "raid") is None
    assert await guide.load_brief_record("Mage", "Frost", "raid") is None  # legacy markdown only


async def test_loader_labels_stale_briefs_and_caches(session_factory, monkeypatch):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    install(monkeypatch, lambda q, v: MENU_PAYLOAD)  # live patch 12.1
    guide.invalidate_brief_cache()
    await _store(session_factory, game_patch="12.0")
    record = await guide.load_brief_record("Mage", "Fire", "raid")
    assert record.freshness == "possibly_stale" and "may be out of date" in record.text.splitlines()[0]
    await _store(session_factory, game_patch="12.1")
    assert (await guide.load_brief_record("Mage", "Fire", "raid")).freshness == "possibly_stale"  # cached
    guide.invalidate_brief_cache(("Mage", "Fire", "raid"))
    assert (await guide.load_brief_record("Mage", "Fire", "raid")).freshness == "current"


def test_freshness_rules():
    f = guide.guide_freshness_of
    assert f("raid", "12.1", None, None, "12.1", None) == "current"
    assert f("raid", "12.0", None, None, "12.1", None) == "possibly_stale"
    assert f("raid", None, None, None, "12.1", None) == "unknown"
    assert f("raid", "12.1", None, "hotfix", "12.1", None) == "possibly_stale"
    assert f("mplus", "12.1", "Mythic+ Season 1", None, "12.1", "Mythic+ Season 2") == "possibly_stale"
    assert f("mplus", "12.1", "Mythic+ Season 2", None, "12.1", "Mythic+ Season 2") == "current"


async def test_turn_briefs_survive_a_wcl_outage(monkeypatch):
    # QA BUG-001: no zone list ⇒ classify from the message, never fail the chat turn.
    from wcl_agent.guides.guide_meta import BriefRecord, clear_brief_loader, set_brief_loader

    def boom(q, v):
        raise RuntimeError("WCL down")

    install(monkeypatch, boom)

    async def loader(class_name, spec, ct):
        return BriefRecord(class_name, spec, ct, f"{ct} brief", (), "12.1", None, None, "current", True)

    set_brief_loader(loader)
    try:
        turn = await guide.briefs_for_turn([("Mage", "Fire")], "how was my +12 key?", None)
    finally:
        clear_brief_loader()
    assert turn.content_type == "mplus" and turn.briefs[("Mage", "Fire")].text == "mplus brief"


async def test_turn_preamble_survives_a_brief_failure(session, tenant_id, monkeypatch):
    from backend.app.api import ws

    char = await repo.add_character(session, tenant_id=tenant_id, role="self", name="Ana", server="S", region="EU")
    await repo.set_character_spec(session, char.id, tenant_id=tenant_id, class_name="Mage", active_spec="Fire")
    await session.commit()

    async def broken(*a):
        raise RuntimeError("anything at all")

    monkeypatch.setattr(ws, "briefs_for_turn", broken)
    preamble = await ws._build_turn_preamble(session, tenant_id, "how did I do?")
    assert "Ana-S (EU)" in preamble  # the profile still reaches the agent
