"""Guide pipeline end to end with faked model calls (feature 015, US1).

The author is a tool-less structured call that sees only the briefing and evidence; the
chat agent (``stream_response``) is never involved; unknown patch postpones the run.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from backend.app import agent_runner
from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services.guide_pipeline import (
    authoring,
    briefing as briefing_mod,
    llm,
    research,
    run_guide_generation,
)
from backend.app.services.guide_pipeline.llm import GroundedText, GuideModelError
from backend.app.services.guide_pipeline.models import (
    DataSheet,
    GenerationBriefing,
    ObservedAbility,
    SampleScope,
)
from backend.app.services.guide_pipeline.render import rendered_claim_ids, strip_claim_markers

BRIEFING = GenerationBriefing(
    now_utc=datetime(2026, 10, 18, 12, 0, tzinfo=UTC),
    content_type="raid",
    class_name="Mage",
    class_display="Mage",
    spec="Fire",
    role="dps",
    class_specs=["Arcane", "Fire", "Frost"],
    live_patch="12.1.5",
    live_build="12.1.5.70448",
    latest_hotfix_at=datetime(2026, 10, 17, tzinfo=UTC),
    hotfix_touches_spec=False,
    raid_tier="The Venomous Abyss",
    mplus_season="Mythic+ Season 2",
)

EXTRACTED = {
    "items": [
        {"statement": "Combustion has a 120 second cooldown.", "topic": "cooldowns",
         "source_url": "https://www.icy-veins.com/wow/fire-mage-pve-dps-guide",
         "source_title": "Fire Mage DPS Guide", "source_date": "2026-09-20", "product": "retail",
         "environment": "live", "patch": "12.1", "content_type": "both",
         "subject": "Combustion cooldown", "value": "120 s"},
        {"statement": "Spend Hot Streak immediately on Pyroblast.", "topic": "rotation",
         "source_url": "https://worldofwarcraft.blizzard.com/en-us/news/1",
         "source_title": "Class tuning", "source_date": "not a date", "content_type": "raid"},
    ]
}

AUTHORED = {
    "claims": [
        {"section": "priority", "text": "Spend Hot Streak on Pyroblast right away.",
         "evidence_type": "guidance", "evidence_refs": ["src:2"], "confidence": "medium"},
        {"section": "cooldowns", "text": "Use Combustion on cooldown, every 120 s.",
         "evidence_type": "guidance", "evidence_refs": ["src:1"], "confidence": "high",
         "ability_name": "Combustion", "cooldown_s": 120, "charges": 1,
         "log_check": {"signal": "cooldown_usage", "expectation": "Combustion about every 120 s"}},
        # Cites evidence that does not exist → dropped into "unconfirmed".
        {"section": "talents", "text": "Take the Sunfury build.", "evidence_refs": ["src:99"]},
        # A mistake without a log check fails validation → dropped.
        {"section": "mistakes", "text": "Do not cap Fire Blast charges.", "evidence_refs": ["src:2"]},
    ],
    "unconfirmed": ["AoE priority"],
}


SHEET = DataSheet(
    class_name="Mage", spec="Fire", content_type="raid",
    scope=SampleScope(zone_name="The Venomous Abyss", sample_size=24, metric="dps", encounters=["Sszorak"]),
    sufficient=True,
    abilities=[ObservedAbility(ability_id=190319, name="Combustion", casts_per_min_median=0.5,
                               min_gap_s=118.0, players_using=24)],
)


def confirm_all(prompt: str) -> dict:
    """A reviewer that confirms every claim it is shown."""
    ids = re.findall(r"^(c\d+) \(", prompt, re.M)
    return {"verdicts": [{"claim_id": i, "verdict": "confirmed", "evidence_ids": []} for i in ids]}


def answer(schema, prompt, extracted=None, authored=None):
    if schema.__name__ == "_Extraction":
        return schema.model_validate(extracted or EXTRACTED)
    if schema.__name__ == "_ReviewDraft":
        return schema.model_validate(confirm_all(prompt))
    return schema.model_validate(authored or AUTHORED)


@pytest.fixture
def fakes(monkeypatch, session_factory):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    calls: dict[str, list] = {"grounded": [], "structured": []}

    async def fake_briefing(class_name, spec, content_type):
        return BRIEFING.model_copy(update={"content_type": content_type})

    async def fake_grounded(model, prompt, *, url_context):
        calls["grounded"].append((model, prompt, url_context))
        return GroundedText("notes", [{"title": "icy-veins.com", "uri": "https://www.icy-veins.com/x"}])

    async def fake_structured(model, prompt, schema, *, temperature=0.2):
        calls["structured"].append((model, prompt, schema.__name__))
        return answer(schema, prompt)

    async def no_chat(*a, **k):
        raise AssertionError("the guide pipeline must not use the chat agent")
        yield  # pragma: no cover

    async def fake_sheet(briefing):
        calls["sheet"] = briefing
        return SHEET.model_copy(update={"content_type": briefing.content_type})

    monkeypatch.setattr("backend.app.services.guide_pipeline.build_briefing", fake_briefing)
    monkeypatch.setattr("backend.app.services.guide_pipeline.build_data_sheet", fake_sheet)
    monkeypatch.setattr(llm, "generate_grounded", fake_grounded)
    monkeypatch.setattr(llm, "generate_structured", fake_structured)
    monkeypatch.setattr(agent_runner, "stream_response", no_chat)
    return calls


async def test_run_publishes_claims_rendered_with_the_live_patch(fakes, session_factory):
    outcome = await run_guide_generation("Mage", "Fire", "raid")
    assert outcome.outcome == "published"

    author_prompt = next(p for _, p, name in fakes["structured"] if name == "_AuthorDraft")
    for field in ("2026-10-18 12:00 UTC", "12.1.5", "12.1.5.70448", "The Venomous Abyss",
                  "Arcane, Fire, Frost", "Raid", "leave it out"):
        assert field in author_prompt, field
    assert "src:1" in author_prompt and "src:2" in author_prompt
    collect_prompt = fakes["grounded"][0][1]
    # Third-party page fetching stays off by default: only official pages may be opened.
    assert "ONLY on these sites: worldofwarcraft.blizzard.com, news.blizzard.com." in collect_prompt

    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.status == "ready" and g.game_patch == "12.1.5" and g.season is None
    assert [c["id"] for c in g.claims] == ["c1", "c2"]
    assert g.briefing["live_build"] == "12.1.5.70448"
    assert g.evidence["fact_sheet"]["items"][1]["source_date"] is None  # bad date dropped, item kept
    assert g.major_cooldowns == [{"name": "Combustion", "spell_id": None, "cooldown_s": 120.0,
                                  "charges": 1, "talent_modified": False}]
    assert {s["uri"] for s in g.sources} == {
        "https://www.icy-veins.com/wow/fire-mage-pve-dps-guide",
        "https://worldofwarcraft.blizzard.com/en-us/news/1",
    }
    md = g.guide_markdown
    assert md.startswith("# Fire Mage — Raid") and "Patch 12.1.5 · The Venomous Abyss" in md
    assert rendered_claim_ids(md) == ["c1", "c2", "c2"]  # c2 again under "What the coach looks for"
    assert "## What the coach looks for\n\n- Combustion about every 120 s" in md
    assert g.brief["cooldowns"][0]["name"] == "Combustion" and g.brief["cooldowns"][0]["ability_id"] is None
    assert g.brief["unconfirmed"] == ["AoE priority", "talent build", "common mistakes"]
    assert "## Sources" not in md and "## Not covered" not in md  # the viewer renders those
    assert "<!--" not in strip_claim_markers(md)


async def test_mplus_run_stores_the_season(fakes, monkeypatch, session_factory):
    both = {"items": [dict(i, content_type="both") for i in EXTRACTED["items"]]}

    async def structured(model, prompt, schema, *, temperature=0.2):
        return answer(schema, prompt, extracted=both)

    monkeypatch.setattr(llm, "generate_structured", structured)
    await run_guide_generation("Mage", "Fire", "mplus")
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire", content_type="mplus")
    assert g.status == "ready" and g.season == "Mythic+ Season 2"
    assert "Mythic+ Season 2" in g.guide_markdown


@pytest.mark.parametrize(
    "error,reason",
    [(briefing_mod.PatchUnknown(), "patch_unknown"), (briefing_mod.SeasonUnknown(), "season_unknown")],
)
async def test_postponed_runs_fail_with_a_reason(fakes, monkeypatch, session_factory, error, reason):
    async def no_patch(*a):
        raise error

    monkeypatch.setattr("backend.app.services.guide_pipeline.build_briefing", no_patch)
    outcome = await run_guide_generation("Mage", "Fire", "raid")
    assert outcome.outcome == "failed" and outcome.reason == reason
    assert fakes["structured"] == []  # nothing is written without a live patch
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.status == "failed" and g.failure_reason == reason


async def test_model_error_keeps_the_published_version(fakes, monkeypatch, session_factory):
    async with session_factory() as s:
        await repo.upsert_spec_guide(
            s, class_name="Mage", spec="Fire", status="ready", guide_markdown="# old", game_patch="12.0"
        )
        await s.commit()

    async def broken(*a, **k):
        raise GuideModelError("invalid structured output")

    monkeypatch.setattr(llm, "generate_structured", broken)
    outcome = await run_guide_generation("Mage", "Fire", "raid")
    assert outcome.reason == "model_error"
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.status == "failed" and g.guide_markdown == "# old" and g.game_patch == "12.0"


async def test_no_supported_claims_is_a_failure(fakes, monkeypatch, session_factory):
    async def nothing(model, prompt, schema, *, temperature=0.2):
        return answer(schema, prompt, authored={"claims": [], "unconfirmed": ["everything"]})

    monkeypatch.setattr(llm, "generate_structured", nothing)
    outcome = await run_guide_generation("Mage", "Fire", "raid")
    assert outcome.reason == "no_supported_claims"


def test_accept_claims_drops_unsupported_and_orders_sections():
    result = authoring.accept_claims(
        [
            {"section": "stats", "text": "Haste is good.", "evidence_refs": ["src:1"]},
            {"section": "priority", "text": "Pyroblast on Hot Streak.", "evidence_refs": ["src:1", "src:9"]},
            {"section": "bogus", "text": "x", "evidence_refs": ["src:1"]},
        ],
        ["stats"],
        {"src:1"},
    )
    assert [(c.id, c.section) for c in result.claims] == [("c1", "priority"), ("c2", "stats")]
    assert result.claims[0].evidence_refs == ["src:1"]
    assert result.unconfirmed == ["stats", "bogus"]


async def test_redirect_sources_resolve_to_publisher_urls(monkeypatch):
    import httpx

    def handler(request):
        return httpx.Response(302, headers={"location": "https://www.icy-veins.com/wow/fire"})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        research.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    out = await research.resolve_source_urls(
        [{"title": "icy-veins.com", "uri": research._REDIRECT_PREFIX + "abc"},
         {"title": "x", "uri": "https://example.test/direct"}]
    )
    assert [s["uri"] for s in out] == ["https://www.icy-veins.com/wow/fire", "https://example.test/direct"]


async def test_data_sheet_feeds_research_author_and_brief(fakes, monkeypatch, session_factory):
    authored = dict(AUTHORED)
    authored["claims"] = [dict(c) for c in AUTHORED["claims"]]
    authored["claims"][1].update(ability_id=190319, evidence_refs=["src:1", "ds:ability:190319"])
    authored["claims"][0].update(
        text="Among 24 top logs, Pyroblast follows every Hot Streak.", evidence_type="observed",
        evidence_refs=["ds:scope"],
    )

    async def structured(model, prompt, schema, *, temperature=0.2):
        fakes["structured"].append((model, prompt, schema.__name__))
        return answer(schema, prompt, authored=authored)

    monkeypatch.setattr(llm, "generate_structured", structured)
    await run_guide_generation("Mage", "Fire", "raid")
    assert "Combustion" in fakes["grounded"][0][1]  # research is told what top players cast
    author_prompt = next(p for _, p, name in fakes["structured"] if name == "_AuthorDraft")
    assert "ds:ability:190319 Combustion" in author_prompt and "ds:scope 24 top logs" in author_prompt
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.brief["cooldowns"][0]["ability_id"] == 190319  # id from the data sheet
    assert g.brief["data_sufficient"] is True and g.brief["data_scope"].startswith("24 top logs")
    assert g.evidence["data_sheet"]["abilities"][0]["min_gap_s"] == 118.0
    assert g.brief["priority"][0]["evidence_type"] == "observed"


async def test_failed_data_sheet_does_not_stop_the_run(fakes, monkeypatch, session_factory):
    async def broken(briefing):
        raise RuntimeError("WCL down")

    monkeypatch.setattr("backend.app.services.guide_pipeline.build_data_sheet", broken)
    assert (await run_guide_generation("Mage", "Fire", "raid")).outcome == "published"
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.brief["data_sufficient"] is False and g.evidence["data_sheet"] is None
    assert g.brief["cooldowns"][0]["ability_id"] is None  # no sheet, no ids (FR-034)


async def test_raid_source_never_reaches_an_mplus_author(fakes, session_factory):
    # src:2 is a raid-only page: the hard filter drops it before authoring, so the claim
    # that cites it cannot survive and its area is reported as not covered.
    outcome = await run_guide_generation("Mage", "Fire", "mplus")
    assert outcome.outcome == "published"
    author_prompt = next(p for _, p, name in fakes["structured"] if name == "_AuthorDraft")
    assert "src:2" not in author_prompt
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire", content_type="mplus")
    assert g.evidence["fact_sheet"]["dropped"][0]["reason"] == "other_content_type:raid"
    assert [c["section"] for c in g.claims] == ["cooldowns"]
    assert "rotation / priority" in g.brief["unconfirmed"]


async def test_one_structured_log_line_per_run(fakes, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="backend.app.services.guide_pipeline"):
        await run_guide_generation("Mage", "Fire", "raid")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("guide run ")]
    assert len(lines) == 1
    line = lines[0]
    for part in ("class=Mage", "spec=Fire", "content_type=raid", "outcome=published", "rounds=1",
                 "claims_drafted=2", "claims_published=2", "sample_size=24", "evidence_kept=2",
                 "evidence_dropped=0", "duration_s=", "review_model="):
        assert part in line, part


async def test_low_wcl_budget_postpones_before_any_model_call(fakes, monkeypatch, session_factory):
    from backend.app.services.guide_pipeline.datasheet import WclBudgetLow

    async def low(briefing):
        raise WclBudgetLow("100 of 720 left")

    monkeypatch.setattr("backend.app.services.guide_pipeline.build_data_sheet", low)
    outcome = await run_guide_generation("Mage", "Fire", "raid")
    assert outcome.reason == "wcl_budget" and fakes["grounded"] == [] and fakes["structured"] == []
