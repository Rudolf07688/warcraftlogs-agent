"""Accuracy-check scorers on fixture guides (feature 015, US4) — no live calls."""

from __future__ import annotations

import pytest

from backend.evals.guides import scoring
from backend.evals.guides.coaching import build_case_preamble, summarize
from backend.evals.guides.fixtures import CoachingCase, ExpectedPoint, FactCase, load_all
from backend.evals.guides.scoring import GuideRecord


def _fact(**over) -> FactCase:
    base = {"id": "f", "statement": "s", "expected": "present", "match": [r"\bCombustion\b"]}
    base.update(over)
    return FactCase.model_validate(base)


def _guide(**over) -> GuideRecord:
    base = dict(class_name="Mage", spec="Fire", content_type="raid", status="ready",
                markdown="# Fire\nUse Combustion.", game_patch="12.1")
    base.update(over)
    return GuideRecord(**base)


# --- facts ------------------------------------------------------------------------------


def test_fact_present_correct_omitted_wrong():
    case = _fact(contradict=[r"Combustion[^.]*5 minutes?"])
    assert scoring.score_fact("Combustion every 2 minutes.", [], case)["verdict"] == "correct"
    assert scoring.score_fact("Nothing here.", [], case)["verdict"] == "omitted"
    assert scoring.score_fact("Combustion every 5 minutes.", [], case)["verdict"] == "wrong"
    assert scoring.score_fact(None, [], case)["verdict"] == "omitted"


def test_fact_absent_and_unconfirmed_listing():
    case = _fact(expected="absent", match=[r"\bIcy Veins\b"])
    assert scoring.score_fact("Fire only.", [], case)["verdict"] == "correct"
    assert scoring.score_fact("Press Icy Veins.", [], case)["verdict"] == "wrong"
    listed = scoring.score_fact("x", ["Combustion timing"], _fact())
    assert listed["verdict"] == "omitted" and listed["listed_unconfirmed"] is True


def test_fact_totals_and_abstention():
    rows = [{"verdict": "correct"}, {"verdict": "omitted"}, {"verdict": "omitted"}, {"verdict": "wrong"}]
    totals = scoring.fact_totals(rows)
    assert totals == {"correct": 1, "omitted": 2, "wrong": 1}
    assert scoring.abstention_quality(totals) == pytest.approx(2 / 3)
    assert scoring.abstention_quality({"correct": 3, "omitted": 0, "wrong": 0}) is None


# --- sources ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,leaks",
    [
        ({"uri": "https://www.wowhead.com/ptr-2/news/x", "title": "Patch notes"}, True),
        ({"uri": "https://example.test/guide", "title": "Patch 12.2 PTR changes"}, True),
        ({"uri": "https://www.wowhead.com/classic/guide/fire-mage", "title": "Fire Mage"}, True),
        ({"uri": "https://example.test/a", "title": "Wrath of the Lich King Classic guide"}, True),
        ({"uri": "https://example.test/a", "title": "x", "environment": "beta"}, True),
        ({"uri": "https://www.icy-veins.com/wow/fire-mage-pve-dps-guide", "title": "Fire Mage"}, False),
        ({"uri": "https://worldofwarcraft.blizzard.com/en-us/news/1", "title": "Hotfixes: October 15"}, False),
    ],
)
def test_source_leaks(source, leaks):
    assert scoring.source_leaks(source) is leaks


def test_leakage_and_precision():
    sources = [
        {"uri": "https://www.wowhead.com/ptr/x", "title": "x"},
        {"uri": "https://example.test/live", "title": "live", "patch": "12.1"},
        {"uri": "https://example.test/old", "title": "old", "patch": "11.2"},
        {"uri": "https://reddit.test/r", "title": "thread", "tier": 4},
    ]
    assert scoring.leakage(sources) == 0.25
    assert scoring.current_source_precision(sources, "12.1") == 0.25
    assert scoring.leakage([]) is None


def test_cited_sources_adds_fact_sheet_items_claims_cite():
    g = _guide(
        sources=[{"title": "Blizzard", "uri": "https://worldofwarcraft.blizzard.com/x"}],
        claims=[{"id": "c1", "evidence_refs": ["src:2", "ds:ability:1"]}],
        evidence={"fact_sheet": {"items": [
            {"id": "src:1", "source_url": "https://uncited.test"},
            {"id": "src:2", "source_url": "https://www.wowhead.com/ptr/x", "environment": "ptr"},
        ]}},
    )
    uris = [s["uri"] for s in scoring.cited_sources(g)]
    assert uris == ["https://worldofwarcraft.blizzard.com/x", "https://www.wowhead.com/ptr/x"]


# --- guides -----------------------------------------------------------------------------


def test_patch_accuracy_major_minor_and_season():
    raid_ok = _guide(game_patch="12.1.5")
    raid_old = _guide(spec="Frost", game_patch="12.0")
    mplus_ok = _guide(content_type="mplus", season="Mythic+ Season 2")
    mplus_bad = _guide(spec="Arcane", content_type="mplus", season="Mythic+ Season 1")
    unpublished = _guide(spec="X", markdown=None)
    guides = [raid_ok, raid_old, mplus_ok, mplus_bad, unpublished]
    assert scoring.patch_accuracy(guides, "12.1", "Mythic+ Season 2") == 0.5
    assert scoring.patch_accuracy([unpublished], "12.1", None) is None
    assert scoring.patch_correct(raid_ok, None, None) is False


def test_claim_support_counts_unknown_and_unscored():
    guides = [
        _guide(claims=[{"verdict": "confirmed"}, {"verdict": "confirmed"}, {"verdict": None}]),
        _guide(spec="Frost", claims=[{"verdict": "contradicted"}]),
        _guide(spec="Arcane", claims=None),  # legacy guide: nothing to score
    ]
    support = scoring.claim_support(guides)
    assert support["rate"] == 0.5 and support["unknown"] == 1 and support["unscored_guides"] == 1
    assert scoring.claim_support([_guide()])["rate"] is None


def test_spec_coverage():
    roster = [("DemonHunter", "Havoc"), ("DemonHunter", "Vengeance"), ("DemonHunter", "Devourer")]
    assert scoring.spec_coverage(roster, roster[:2]) == pytest.approx(2 / 3)


# --- coaching ---------------------------------------------------------------------------


def _case(content_type="raid") -> CoachingCase:
    return CoachingCase(
        id="c", report_code="abc", fight_id=1, player="P", class_name="Mage", spec="Fire",
        content_type=content_type, question="q",
        expected_points=[
            ExpectedPoint(id="combust", kind="raise", match=[r"Combustion"]),
            ExpectedPoint(id="no_icy", kind="not_contradict", contradict=[r"Icy Veins"]),
            ExpectedPoint(id="cpm", kind="raise", match=[r"\d+ casts"], contradict=[r"never cast"]),
        ],
    )


def test_coaching_points_and_wrong_content():
    points = scoring.coaching_points(_case(), "Combustion was late. Use Icy Veins.")
    assert [p["verdict"] for p in points] == ["raised", "contradicted", "missed"]
    assert scoring.wrong_content_brief_use(_case("mplus"), ["raid"]) is True
    assert scoring.wrong_content_brief_use(_case("mplus"), ["mplus"]) is False
    assert scoring.wrong_content_brief_use(_case("mplus"), []) is False


def test_summarize_coaching():
    runs = [
        {"error": None, "points": [{"verdict": "raised"}, {"verdict": "missed"}], "wrong_content_brief_use": True},
        {"error": "boom", "points": [], "wrong_content_brief_use": False},
    ]
    s = summarize(runs)
    assert s["raised"] == 1 and s["raised_rate"] == 0.5 and s["errors"] == 1
    assert s["wrong_content_brief_use"] == 0.5


async def test_case_preamble_uses_only_the_matching_content_type(monkeypatch):
    from backend.tests.test_guide_meta import MENU_PAYLOAD
    from backend.tests.wcl_fakes import install
    from wcl_agent.guides.guide_meta import BriefRecord, clear_brief_loader, set_brief_loader

    install(monkeypatch, lambda q, v: MENU_PAYLOAD)

    async def raid_only(class_name, spec, content_type):
        if content_type != "raid":
            return None
        return BriefRecord(class_name, spec, "raid", "RAID BRIEF", (), "12.1", None, None, "current", True)

    set_brief_loader(raid_only)
    try:
        mplus_case = _case("mplus").model_copy(update={"question": "how was my +21 key?"})
        preamble, used = await build_case_preamble(mplus_case)
        assert used == [] and "RAID BRIEF" not in preamble  # never the other type
        assert "Mythic+: none (no verified guidance) · Raid: available" in preamble
        raid_case = _case("raid").model_copy(update={"question": "how was my raid boss pull?"})
        preamble, used = await build_case_preamble(raid_case)
        assert used == ["raid"] and "RAID BRIEF" in preamble
    finally:
        clear_brief_loader()


# --- gate -------------------------------------------------------------------------------


def _report(**metrics) -> dict:
    base = {
        "leakage_rate": 0.0, "wrong_content_brief_use": 0.0, "patch_accuracy": 1.0,
        "claim_support_rate": 0.97, "facts": {"correct": 5, "omitted": 1, "wrong": 0},
        "coaching": {"contradicted": 0},
    }
    base.update(metrics)
    return {"metrics": base, "adversarial": [{"case": "a", "passed": True}]}


def test_gate_passes_and_each_rule_fails():
    assert scoring.gate(_report()) == (True, [])
    for bad in (
        {"leakage_rate": 0.1},
        {"wrong_content_brief_use": 0.25},
        {"patch_accuracy": 0.9},
        {"patch_accuracy": None},
        {"claim_support_rate": 0.9},
        {"claim_support_rate": None},
        {"facts": {"correct": 5, "omitted": 0, "wrong": 1}},
        {"coaching": {"contradicted": 2}},
    ):
        passed, reasons = scoring.gate(_report(**bad))
        assert not passed and reasons, bad
    failing_case = _report()
    failing_case["adversarial"] = [{"case": "ptr_newer_than_live", "passed": False}]
    assert scoring.gate(failing_case)[0] is False


def test_exit_codes():
    passed = _report()
    passed["gate"] = {"passed": True}
    failed = _report()
    failed["gate"] = {"passed": False}
    assert scoring.exit_code(passed) == 0
    assert scoring.exit_code(failed) == 1
    assert scoring.exit_code({"error": "x"}) == 2
    assert scoring.exit_code(None) == 2


def test_deltas_against_baseline():
    now = {"metrics": {"patch_accuracy": 1.0, "facts": {"correct": 9, "omitted": 1, "wrong": 0},
                       "coaching": {"raised_rate": 0.9}}}
    base = {"metrics": {"patch_accuracy": 0.25, "facts": {"correct": 5, "omitted": 0, "wrong": 5},
                        "coaching": {"raised_rate": 0.5}}}
    d = scoring.deltas(now, base)
    assert d["patch_accuracy"] == 0.75
    assert d["wrong_fact_share_reduction"] == 1.0
    assert d["coaching_raised_rate"] == 0.4
    assert scoring.deltas(now, None) == {}


def test_committed_fixtures_validate():
    facts, adversarial, coaching = load_all()
    assert len(adversarial) == 6
    assert {f.content_type for f in facts} == {"raid", "mplus"}
    assert {(f.class_name, f.spec) for f in facts} >= {("DemonHunter", "Devourer")}
    assert all(len(f.facts) >= 5 for f in facts)
    assert {c.content_type for c in coaching} == {"raid", "mplus"}
