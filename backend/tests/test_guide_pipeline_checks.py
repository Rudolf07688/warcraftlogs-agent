"""Deterministic guide checks — one fixture per defect (feature 015, US7, FR-036)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.app.config import settings
from backend.app.services.guide_pipeline.checks import run_checks
from backend.app.services.guide_pipeline.models import (
    DataSheet,
    EvidenceItem,
    FactSheet,
    GenerationBriefing,
    GuideClaim,
    ObservedAbility,
    SampleScope,
)
from backend.app.services.guide_pipeline.render import build_brief, render_brief_text, render_guide_markdown

BRIEFING = GenerationBriefing(
    now_utc=datetime(2026, 10, 18, tzinfo=UTC), content_type="raid", class_name="Mage",
    class_display="Mage", spec="Fire", role="dps", class_specs=["Arcane", "Fire", "Frost"],
    live_patch="12.1.5", mplus_season="Mythic+ Season 2",
    latest_hotfix_at=datetime(2026, 10, 16, tzinfo=UTC), hotfix_touches_spec=True,
)
SHEET = DataSheet(
    class_name="Mage", spec="Fire", content_type="raid",
    scope=SampleScope(zone_name="The Venomous Abyss", sample_size=24, metric="dps"), sufficient=True,
    abilities=[
        ObservedAbility(ability_id=190319, name="Combustion", casts_per_min_median=0.8, min_gap_s=118.0, players_using=24),
        ObservedAbility(ability_id=2139, name="Counterspell", casts_per_min_median=0.2, min_gap_s=24.0, players_using=20),
        ObservedAbility(ability_id=153561, name="Meteor", casts_per_min_median=1.4, min_gap_s=30.0, players_using=24),
    ],
)


def _item(n, **over):
    base = {"id": f"src:{n}", "statement": "fact", "source_url": f"https://www.icy-veins.com/wow/fire-{n}",
            "source_title": "Fire Mage guide", "source_date": "2026-10-17", "tier": 3, "patch": "12.1",
            "content_type": "both"}
    base.update(over)
    return EvidenceItem.model_validate(base)


FACTS = FactSheet(items=[_item(1), _item(2)])


def _cd(n, name, cooldown, ability_id=None, charges=1, refs=("src:1",)):
    return GuideClaim(
        id=f"c{n}", section="cooldowns", text=f"Use {name} on cooldown.", evidence_refs=list(refs),
        ability_name=name, ability_id=ability_id, cooldown_s=cooldown, charges=charges,
        log_check={"signal": "cooldown_usage", "expectation": f"{name} on cooldown"},
    )


CLEAN = [
    GuideClaim(id="c1", section="priority", text="Pyroblast on Hot Streak.", evidence_refs=["src:1"]),
    _cd(2, "Combustion", 120, 190319, refs=("src:1", "ds:ability:190319")),
]


def check(claims=CLEAN, *, briefing=BRIEFING, sheet=SHEET, facts=FACTS, brief_patch=None, markdown=None, text=None):
    brief = build_brief(briefing, claims, [], sheet)
    if brief_patch:
        brief = brief.model_copy(update=brief_patch)
    brief_text = text if text is not None else render_brief_text(brief)
    md = markdown if markdown is not None else render_guide_markdown(briefing, claims)
    return [(f.check, f.item) for f in run_checks(briefing, claims, brief, brief_text, md, sheet, facts)]


def test_clean_guide_passes():
    assert check() == []


def test_ability_unknown_and_skipped_without_a_sufficient_sheet():
    claims = [*CLEAN, _cd(3, "Arcane Power", 90)]
    assert check(claims) == [("ability_unknown", "c3")]
    assert check(claims, sheet=SHEET.model_copy(update={"sufficient": False})) == []
    assert check(claims, sheet=None) == []


def test_cooldown_cast_faster_than_stated():
    assert check([*CLEAN[:1], _cd(2, "Combustion", 180, 190319)]) == [("cooldown_mismatch", "c2")]


def test_charges_relax_the_lower_bound():
    assert check([*CLEAN[:1], _cd(2, "Combustion", 180, 190319, charges=2)]) == []


def test_frequent_ability_never_recast_that_fast():
    # Meteor: 1.4 casts/min (≈7 per fight) but never recast within 30 s; "10 s" is wrong.
    assert check([*CLEAN, _cd(3, "Meteor", 10, 153561)]) == [("cooldown_mismatch", "c3")]
    # Counterspell is rare (≈1 per fight), so its long gaps prove nothing.
    assert check([*CLEAN, _cd(3, "Counterspell", 4, 2139)]) == []


def test_patch_and_season_mismatch():
    assert check(brief_patch={"patch": "12.0"}) == [("patch_mismatch", "brief")]
    mplus = BRIEFING.model_copy(update={"content_type": "mplus"})
    assert ("season_mismatch", "brief") in check(briefing=mplus, sheet=None, brief_patch={"season": "Mythic+ Season 1"})


@pytest.mark.parametrize(
    "item",
    [
        {"environment": "ptr"},
        {"product": "classic"},
        {"source_url": "https://www.wowhead.com/ptr-2/guide/fire"},
        {"patch": "11.2"},
        {"content_type": "mplus"},
    ],
)
def test_source_env(item):
    facts = FactSheet(items=[_item(1, **item), _item(2)])
    assert ("source_env", "c1") in check(facts=facts)


def test_source_prehotfix_and_its_exceptions():
    old = FactSheet(items=[_item(1, source_date="2026-10-01"), _item(2)])
    assert ("source_prehotfix", "c1") in check(facts=old)
    flagged = FactSheet(items=[_item(1, source_date="2026-10-01", possibly_stale=True), _item(2)])
    assert check(facts=flagged) == []
    no_hotfix = BRIEFING.model_copy(update={"latest_hotfix_at": None})
    assert check(facts=old, briefing=no_hotfix) == []
    untouched = BRIEFING.model_copy(update={"hotfix_touches_spec": False})
    assert check(facts=old, briefing=untouched) == []


def test_claim_unreferenced():
    ghost = GuideClaim(id="c3", section="overview", text="Fire is fun.", evidence_refs=["src:99"])
    assert check([*CLEAN, ghost]) == [("claim_unreferenced", "c3")]


def test_log_check_missing():
    claim = CLEAN[1].model_copy(update={"log_check": None})
    assert ("log_check_missing", "c2") in check([CLEAN[0], claim])


def test_brief_too_long(monkeypatch):
    monkeypatch.setattr(settings, "wcl_guide_brief_max_chars", 50)
    assert check() == [("brief_too_long", "brief")]


def test_guide_extra_claim():
    md = render_guide_markdown(BRIEFING, CLEAN) + "\n## Extra\n\n- Always stand in fire.\n"
    assert check(markdown=md) == [("guide_extra_claim", "- Always stand in fire.")]
    forged = render_guide_markdown(BRIEFING, CLEAN).replace("<!-- c1 -->", "<!-- c9 -->")
    assert ("guide_extra_claim", "- Pyroblast on Hot Streak. <!-- c9 -->") in check(markdown=forged)


def test_dates_are_compared_as_days():
    assert date(2026, 10, 16) == BRIEFING.latest_hotfix_at.date()
    same_day = FactSheet(items=[_item(1, source_date="2026-10-16"), _item(2)])
    assert check(facts=same_day) == []
