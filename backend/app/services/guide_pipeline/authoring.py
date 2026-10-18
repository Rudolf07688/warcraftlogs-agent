"""Stages 4 and 7: write claims from evidence, and revise them after checks/review.

The author is a tool-less structured call (FR-004): it sees only the briefing and the
evidence sheets. Code then keeps only claims that validate and cite evidence that exists;
everything else becomes an "unconfirmed" area (FR-005).
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError

from ...config import settings
from . import llm
from .models import (
    SECTION_ORDER,
    AuthorResult,
    CheckFailure,
    DataSheet,
    FactSheet,
    GenerationBriefing,
    GuideClaim,
    ReviewIssue,
)
from .prompts import author_prompt, format_evidence, revise_prompt

logger = logging.getLogger(__name__)

SECTION_LABEL = {
    "overview": "overview",
    "priority": "rotation / priority",
    "cooldowns": "cooldown usage",
    "uptimes": "buff and debuff uptimes",
    "talents": "talent build",
    "stats": "secondary stat priority",
    "mistakes": "common mistakes",
    "benchmarks": "benchmarks",
    "content_notes": "encounter notes",
}


class _LogCheckDraft(BaseModel):
    signal: str
    ability_id: int | None = None
    expectation: str


class _ClaimDraft(BaseModel):
    """A claim as the model returns it; validated into ``GuideClaim`` by code."""

    section: str
    text: str
    evidence_type: str = "guidance"
    evidence_refs: list[str] = []
    log_check: _LogCheckDraft | None = None
    confidence: str = "medium"
    ability_name: str | None = None
    ability_id: int | None = None
    cooldown_s: float | None = None
    charges: int | None = None


class _AuthorDraft(BaseModel):
    claims: list[_ClaimDraft] = []
    unconfirmed: list[str] = []


def known_evidence_ids(fact_sheet: FactSheet, data_sheet: DataSheet | None) -> set[str]:
    """Every id a claim may cite: citable research items, plus data-sheet facts when the
    sample is large enough to count as guidance."""
    ids = set(fact_sheet.citable_ids())
    if data_sheet is not None and data_sheet.sufficient:
        ids |= data_sheet.fact_ids()
    return ids


def accept_claims(
    drafts: list, unconfirmed: list[str], known_ids: set[str]
) -> AuthorResult:
    """Validate drafted claims; drop unsupported ones into ``unconfirmed`` by section.

    A claim survives only when it validates (section, length, log check) and keeps at
    least one evidence reference that resolves. Ids are reassigned ``c1..cN``.
    """
    claims: list[GuideClaim] = []
    missing = list(dict.fromkeys(u.strip() for u in unconfirmed if u and u.strip()))
    for draft in drafts:
        data = draft.model_dump() if isinstance(draft, BaseModel) else dict(draft)
        data["evidence_refs"] = [r for r in data.get("evidence_refs") or [] if r in known_ids]
        try:
            claim = GuideClaim.model_validate({**data, "id": "", "verdict": None})
        except ValidationError:
            label = SECTION_LABEL.get(str(data.get("section")), str(data.get("section") or "other"))
            if label not in missing:
                missing.append(label)
            continue
        claims.append(claim)
    claims.sort(key=lambda c: SECTION_ORDER.index(c.section))
    for n, claim in enumerate(claims, start=1):
        claim.id = f"c{n}"
    return AuthorResult(claims=claims, unconfirmed=missing)


async def author_claims(
    briefing: GenerationBriefing, fact_sheet: FactSheet, data_sheet: DataSheet | None = None
) -> AuthorResult:
    """Stage 4: claims from the briefing and evidence only (no tools, no web)."""
    prompt = author_prompt(briefing, format_evidence(fact_sheet, data_sheet))
    draft = await llm.generate_structured(settings.wcl_guide_model, prompt, _AuthorDraft)
    result = accept_claims(draft.claims, draft.unconfirmed, known_evidence_ids(fact_sheet, data_sheet))
    logger.info(
        "guide author %s %s %s: %d drafted, %d kept, %d unconfirmed",
        briefing.class_name, briefing.spec, briefing.content_type,
        len(draft.claims), len(result.claims), len(result.unconfirmed),
    )
    return result


def format_problems(failures: list[CheckFailure], issues: list[ReviewIssue] = ()) -> str:
    lines = [f"- [{f.check}] {f.item}: {f.detail}" for f in failures]
    lines += [f"- [review: {i.kind}] {i.claim_id or 'guide'}: {i.detail}" for i in issues]
    return "\n".join(lines) or "(none)"


async def revise_claims(
    briefing: GenerationBriefing,
    fact_sheet: FactSheet,
    data_sheet: DataSheet | None,
    current: AuthorResult,
    failures: list[CheckFailure],
    issues: list[ReviewIssue] = (),
) -> AuthorResult:
    """Stage 7: one tool-less structured call that fixes or removes what failed."""
    claims_json = json.dumps(
        [c.model_dump(mode="json", exclude={"verdict"}) for c in current.claims], ensure_ascii=False
    )
    prompt = revise_prompt(
        briefing, claims_json, format_problems(failures, issues), format_evidence(fact_sheet, data_sheet)
    )
    draft = await llm.generate_structured(settings.wcl_guide_model, prompt, _AuthorDraft)
    unconfirmed = list(dict.fromkeys([*current.unconfirmed, *draft.unconfirmed]))
    return accept_claims(draft.claims, unconfirmed, known_evidence_ids(fact_sheet, data_sheet))
