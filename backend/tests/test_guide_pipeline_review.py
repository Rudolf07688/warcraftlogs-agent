"""Independent review and correction before publishing (feature 015, US9, FR-045..FR-049)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from backend.app.config import settings
from backend.app.db import repository as repo
from backend.app.db import session as db_session
from backend.app.services import guide_pipeline as pipeline
from backend.app.services.guide_pipeline import llm
from backend.app.services.guide_pipeline.models import (
    AuthorResult,
    EvidenceItem,
    FactSheet,
    GenerationBriefing,
    GuideClaim,
)

BRIEFING = GenerationBriefing(
    now_utc=datetime(2026, 10, 18, tzinfo=UTC), content_type="raid", class_name="Mage",
    class_display="Mage", spec="Fire", role="dps", class_specs=["Arcane", "Fire", "Frost"],
    live_patch="12.1.5",
)
FACTS = FactSheet(items=[
    EvidenceItem(id=f"src:{n}", statement=text, source_url=f"https://www.icy-veins.com/wow/fire-{n}",
                 source_title="Fire Mage guide", patch="12.1")
    for n, text in [(1, "Combustion has a 120 second cooldown."), (2, "Pyroblast consumes Hot Streak."),
                    (3, "Sunfury is the common hero talent tree."), (4, "UNCITED SECRET EVIDENCE")]
])


def claim(n, section, text, refs, **kw):
    base = {"id": f"c{n}", "section": section, "text": text, "evidence_refs": refs}
    if section in {"cooldowns", "mistakes", "uptimes", "benchmarks"}:
        base["log_check"] = {"signal": "cooldown_usage", "expectation": "on cooldown"}
    base.update(kw)
    return GuideClaim.model_validate(base)


AUTHORED = AuthorResult(claims=[
    claim(1, "priority", "Spend Hot Streak on Pyroblast.", ["src:2"]),
    claim(2, "cooldowns", "Combustion every 90 s.", ["src:1"], ability_name="Combustion", cooldown_s=90),
    claim(3, "talents", "Play Spellslinger.", ["src:3"]),
])


class Reviewer:
    """Scripted reviewer: ``rounds`` is a list of {claim_id: verdict} per call (default confirmed)."""

    def __init__(self, rounds, revised=None):
        self.rounds = list(rounds)
        self.revised = revised
        self.review_prompts: list[str] = []
        self.revise_prompts: list[str] = []
        self.models: list[str] = []

    async def __call__(self, model, prompt, schema, *, temperature=0.2):
        if schema.__name__ == "_ReviewDraft":
            self.models.append(model)
            self.review_prompts.append(prompt)
            script = self.rounds.pop(0) if self.rounds else {}
            ids = re.findall(r"^(c\d+) \(", prompt, re.M)
            return schema.model_validate({"verdicts": [
                {"claim_id": i, "verdict": script.get(i, "confirmed"), "detail": f"{i} {script.get(i, 'ok')}",
                 "evidence_ids": ["src:1"]} for i in ids
            ]})
        self.revise_prompts.append(prompt)
        return schema.model_validate(self.revised)


def fresh():
    return AUTHORED.model_copy(deep=True)


async def test_passes_in_one_round_when_everything_is_confirmed(monkeypatch):
    reviewer = Reviewer([{}])
    monkeypatch.setattr(llm, "generate_structured", reviewer)
    loop = await pipeline.review_loop(BRIEFING, fresh(), FACTS, None)
    assert loop.outcome == "publish" and loop.rounds == 1 and reviewer.revise_prompts == []
    assert {c.verdict for c in loop.authored.claims} == {"confirmed"}
    assert reviewer.models == [settings.wcl_guide_review_model] != [settings.wcl_guide_model]


async def test_contradicted_is_revised_and_unconfirmed_removed(monkeypatch):
    fixed = {"claims": [
        {"section": "priority", "text": "Spend Hot Streak on Pyroblast.", "evidence_refs": ["src:2"]},
        {"section": "cooldowns", "text": "Combustion every 120 s.", "evidence_refs": ["src:1"],
         "ability_name": "Combustion", "cooldown_s": 120,
         "log_check": {"signal": "cooldown_usage", "expectation": "about every 120 s"}},
    ], "unconfirmed": []}
    reviewer = Reviewer([{"c2": "contradicted", "c3": "unconfirmed"}, {}], revised=fixed)
    monkeypatch.setattr(llm, "generate_structured", reviewer)
    loop = await pipeline.review_loop(BRIEFING, fresh(), FACTS, None)
    assert loop.outcome == "publish" and loop.rounds == 2
    assert [c.text for c in loop.authored.claims] == ["Spend Hot Streak on Pyroblast.", "Combustion every 120 s."]
    assert "talent build" in loop.authored.unconfirmed  # the removed claim's area
    assert "c2 contradicted" in reviewer.revise_prompts[0] and "Play Spellslinger" not in reviewer.revise_prompts[0]
    assert "talent build" in loop.rendered.brief.unconfirmed


async def test_only_unconfirmed_needs_no_revision(monkeypatch):
    reviewer = Reviewer([{"c3": "unconfirmed"}])
    monkeypatch.setattr(llm, "generate_structured", reviewer)
    loop = await pipeline.review_loop(BRIEFING, fresh(), FACTS, None)
    assert loop.outcome == "publish" and loop.rounds == 1 and reviewer.revise_prompts == []
    assert [c.id for c in loop.authored.claims] == ["c1", "c2"]


async def test_stops_at_the_round_limit_and_holds(monkeypatch):
    monkeypatch.setattr(settings, "wcl_guide_max_review_rounds", 2)
    stubborn = {"claims": [c.model_dump() for c in AUTHORED.claims[:2]], "unconfirmed": []}
    reviewer = Reviewer([{"c2": "contradicted"}] * 5, revised=stubborn)
    monkeypatch.setattr(llm, "generate_structured", reviewer)
    loop = await pipeline.review_loop(BRIEFING, fresh(), FACTS, None)
    assert loop.outcome == "hold" and loop.rounds == 2 and len(reviewer.review_prompts) == 2
    assert [i.kind for i in loop.issues] == ["contradicted"]


async def test_everything_unconfirmed_leaves_nothing(monkeypatch):
    reviewer = Reviewer([{"c1": "unconfirmed", "c2": "unconfirmed", "c3": "unconfirmed"}])
    monkeypatch.setattr(llm, "generate_structured", reviewer)
    assert (await pipeline.review_loop(BRIEFING, fresh(), FACTS, None)).outcome == "empty"


async def test_reviewer_sees_only_cited_evidence_and_the_knowledge_rule(monkeypatch):
    reviewer = Reviewer([{}])
    monkeypatch.setattr(llm, "generate_structured", reviewer)
    await pipeline.review_loop(BRIEFING, fresh(), FACTS, None)
    prompt = reviewer.review_prompts[0]
    assert "Your own game knowledge is not evidence" in prompt and "verifying, not writing" in prompt
    assert "Combustion has a 120 second cooldown." in prompt
    assert "UNCITED SECRET EVIDENCE" not in prompt
    assert "c2 (cooldowns, cites src:1): Combustion every 90 s. [stated cooldown 90 s, charges 1]" in prompt


async def test_check_failures_block_publication(monkeypatch):
    monkeypatch.setattr(settings, "wcl_guide_max_review_rounds", 1)
    bad = fresh()
    bad.claims[0] = bad.claims[0].model_copy(update={"evidence_refs": ["src:99"]})
    monkeypatch.setattr(llm, "generate_structured", Reviewer([{}]))
    loop = await pipeline.review_loop(BRIEFING, bad, FACTS, None)
    assert loop.outcome == "hold" and loop.failures[0].check == "claim_unreferenced"


async def test_held_run_keeps_the_published_guide(monkeypatch, session_factory):
    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "wcl_guide_max_review_rounds", 1)
    async with session_factory() as s:
        await repo.upsert_spec_guide(s, class_name="Mage", spec="Fire", status="ready", guide_markdown="# verified")
        await s.commit()

    async def briefing(*a):
        return BRIEFING

    async def no_sheet(b):
        return None

    async def facts(b, **kw):
        return FACTS

    async def authored(*a):
        return fresh()

    monkeypatch.setattr(pipeline, "build_briefing", briefing)
    monkeypatch.setattr(pipeline, "build_data_sheet", no_sheet)
    monkeypatch.setattr(pipeline, "build_fact_sheet", facts)
    monkeypatch.setattr(pipeline, "author_claims", authored)
    monkeypatch.setattr(llm, "generate_structured", Reviewer([{"c2": "contradicted"}]))
    outcome = await pipeline.run_guide_generation("Mage", "Fire", "raid")
    assert outcome.outcome == "held" and outcome.rounds == 1
    async with session_factory() as s:
        g = await repo.get_spec_guide(s, class_name="Mage", spec="Fire")
    assert g.status == "needs_review" and g.guide_markdown == "# verified"  # published untouched
    assert g.draft["markdown"].startswith("# Fire Mage — Raid") and g.draft["claims"]
    assert g.review_issues[0]["kind"] == "contradicted" and g.brief is None
