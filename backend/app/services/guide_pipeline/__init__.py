"""Grounded guide generation pipeline (feature 015, contracts/guide-pipeline.md).

One guide = one ``(class, spec, content_type)``. Stages, each a plain async function with
typed input and output (no ADK agent, no coaching tools — research R3):

1. briefing   — live date, patch/build, hotfix time, tier/season, roster
2. data sheet — measured Warcraft Logs evidence from logs-only top rankings
3. research   — version-filtered fact sheet from grounded search
4. author     — tool-less structured claims citing evidence ids
5. checks     — deterministic consistency checks
6. review     — a stronger, different model verifies each claim
7. revise     — fix or remove what failed (5–7 repeat, at most N rounds)
8. render     — code-built coaching brief + readable guide
9. persist    — publish / hold for review / fail
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ...config import settings
from ...db import repository as repo
from ...db import session as db_session
from .authoring import SECTION_LABEL, author_claims, revise_claims
from .briefing import PatchUnknown, SeasonUnknown, build_briefing
from .checks import run_checks
from .datasheet import WclBudgetLow, build_data_sheet
from .llm import GuideModelError
from .models import (
    AuthorResult,
    CheckFailure,
    CoachingBrief,
    ContentType,
    DataSheet,
    EvidenceSnapshot,
    FactSheet,
    GenerationBriefing,
    GuideClaim,
    ReviewIssue,
    RunOutcome,
)
from .render import build_brief, render_brief_text, render_guide_markdown
from .research import build_fact_sheet
from .review import OpenReport, review_claims

logger = logging.getLogger(__name__)


def cited_sources(claims: list[GuideClaim], fact_sheet: FactSheet) -> list[dict]:
    """The published sources: each research item a claim cites, once, in citation order."""
    by_id = fact_sheet.by_id()
    seen: set[str] = set()
    sources: list[dict] = []
    for claim in claims:
        for ref in claim.evidence_refs:
            item = by_id.get(ref)
            if item is None or item.source_url in seen:
                continue
            seen.add(item.source_url)
            sources.append(
                {
                    "title": item.source_title,
                    "uri": item.source_url,
                    "tier": item.tier,
                    "date": item.source_date.isoformat() if item.source_date else None,
                }
            )
    return sources


def brief_cooldowns(brief: CoachingBrief) -> list[dict]:
    """The brief's cooldowns that state a duration, as the stored ``major_cooldowns``."""
    return [
        {
            "name": c.name,
            "spell_id": c.ability_id,
            "cooldown_s": c.cooldown_s,
            "charges": c.charges,
            "talent_modified": False,
        }
        for c in brief.cooldowns
        if c.cooldown_s
    ]


async def _fail(
    class_name: str, spec: str, content_type: str, reason: str, *, review_issues: list | None = None
) -> RunOutcome:
    async with db_session.SessionLocal() as session:
        await repo.fail_spec_guide(
            session,
            class_name=class_name,
            spec=spec,
            content_type=content_type,
            reason=reason,
            review_issues=review_issues,
        )
        await session.commit()
    return RunOutcome(outcome="failed", reason=reason)


@dataclass(frozen=True)
class Rendered:
    brief: CoachingBrief
    brief_text: str
    markdown: str


def render_all(briefing: GenerationBriefing, authored: AuthorResult, data_sheet: DataSheet | None) -> Rendered:
    """Stage 8 for the current claims: the brief, its agent text and the readable guide."""
    brief = build_brief(briefing, authored.claims, authored.unconfirmed, data_sheet)
    return Rendered(brief, render_brief_text(brief, "current"), render_guide_markdown(briefing, authored.claims))


@dataclass
class LoopResult:
    outcome: str  # "publish" | "hold" | "empty" (the review left no claim standing)
    authored: AuthorResult
    rendered: Rendered
    rounds: int
    failures: list[CheckFailure]
    issues: list[ReviewIssue]
    report_verdicts: list = field(default_factory=list)


def _without(authored: AuthorResult, drop: set[str]) -> AuthorResult:
    """Remove claims (their areas become "not covered") and renumber the rest."""
    kept = [c for c in authored.claims if c.id not in drop]
    gone = [SECTION_LABEL.get(c.section, c.section) for c in authored.claims if c.id in drop]
    return AuthorResult(claims=kept, unconfirmed=list(dict.fromkeys([*authored.unconfirmed, *gone])))


def _checks(briefing, authored, rendered, data_sheet, fact_sheet) -> list[CheckFailure]:
    return run_checks(
        briefing, authored.claims, rendered.brief, rendered.brief_text, rendered.markdown, data_sheet, fact_sheet
    )


async def review_loop(
    briefing: GenerationBriefing,
    authored: AuthorResult,
    fact_sheet: FactSheet,
    data_sheet: DataSheet | None,
    reports: list[OpenReport] = (),
) -> LoopResult:
    """Checks + independent review, at most ``wcl_guide_max_review_rounds`` rounds (FR-047).

    Each round: render, run the checks, review every claim against its cited evidence.
    Unconfirmed claims are removed (their areas listed as not covered); contradicted claims
    and check failures go to one revision, and the next round starts over. The guide is
    published only when no check fails and every remaining claim is confirmed; otherwise,
    after the last round, it is held for review.
    """
    max_rounds = max(1, settings.wcl_guide_max_review_rounds)
    report_verdicts: list = []
    for round_no in range(1, max_rounds + 1):
        rendered = render_all(briefing, authored, data_sheet)
        failures = _checks(briefing, authored, rendered, data_sheet, fact_sheet)
        review = await review_claims(briefing, authored.claims, data_sheet, fact_sheet, list(reports))
        report_verdicts = review.report_verdicts or report_verdicts
        for claim in authored.claims:
            claim.verdict = review.verdicts.get(claim.id)
        unconfirmed = {cid for cid, v in review.verdicts.items() if v == "unconfirmed"}
        contradicted = [i for i in review.issues if i.kind == "contradicted"]
        authored = _without(authored, unconfirmed)
        if not authored.claims:
            return LoopResult("empty", authored, rendered, round_no, failures, review.issues, report_verdicts)
        if not contradicted:
            rendered = render_all(briefing, authored, data_sheet)
            failures = _checks(briefing, authored, rendered, data_sheet, fact_sheet)
            if not failures:
                return LoopResult("publish", authored, rendered, round_no, [], [], report_verdicts)
        if round_no == max_rounds:
            return LoopResult("hold", authored, rendered, round_no, failures, review.issues, report_verdicts)
        authored = await revise_claims(briefing, fact_sheet, data_sheet, authored, failures, contradicted)
    raise AssertionError("unreachable")  # the last round always returns


async def _open_reports(class_name: str, spec: str, content_type: str) -> list[OpenReport]:
    """Open "report an inaccuracy" notes for this guide: claims for research and review to
    verify (FR-052). Best-effort."""
    try:
        async with db_session.SessionLocal() as session:
            rows = await repo.list_open_guide_reports(
                session, class_name=class_name, spec=spec, content_type=content_type
            )
    except Exception:  # noqa: BLE001
        logger.exception("could not read open guide reports")
        return []
    return [OpenReport(id=str(r.id), note=r.note) for r in rows]


async def _resolve_reports(verdicts: list) -> None:
    """Record the reviewer's fixed/rejected verdict on each judged report."""
    if not verdicts:
        return
    now = datetime.now(UTC)
    async with db_session.SessionLocal() as session:
        for v in verdicts:
            await repo.resolve_guide_report(
                session, uuid.UUID(v.report_id), status=v.status, outcome_note=v.reason, when=now
            )
        await session.commit()


async def _data_sheet(briefing: GenerationBriefing) -> DataSheet | None:
    """Stage 2, best-effort: without a sheet the run continues on research evidence only
    (the brief then says no measured sample backs it). A low WCL budget is not "no sheet":
    it postpones the whole run (``WclBudgetLow`` propagates)."""
    try:
        return await build_data_sheet(briefing)
    except WclBudgetLow:
        raise
    except Exception:  # noqa: BLE001
        logger.exception(
            "data sheet failed for %s %s %s", briefing.class_name, briefing.spec, briefing.content_type
        )
        return None


@dataclass
class RunStats:
    """What one run did, for its single log line (T108; SC-013 timing input)."""

    rounds: int = 0
    claims_drafted: int = 0
    claims_published: int = 0
    unconfirmed: int = 0
    check_failures: list[str] = field(default_factory=list)
    sample_size: int | None = None
    evidence_kept: int = 0
    evidence_dropped: int = 0


async def run_guide_generation(class_name: str, spec: str, content_type: ContentType) -> RunOutcome:
    """Generate one guide end to end and persist the outcome (never raises).

    A failed run leaves the published version untouched (FR-037). Logs one structured line.
    """
    started = time.monotonic()
    stats = RunStats()
    try:
        outcome = await _run(class_name, spec, content_type, stats)
    except Exception:  # noqa: BLE001 - never leave the row "pending" (QA BUG-002)
        logger.exception("guide run crashed for %s %s %s", class_name, spec, content_type)
        try:
            outcome = await _fail(class_name, spec, content_type, "internal_error")
        except Exception:  # noqa: BLE001 - the DB itself is down; age-based recovery applies
            outcome = RunOutcome(outcome="failed", reason="internal_error")
    logger.info(
        "guide run class=%s spec=%s content_type=%s outcome=%s reason=%s rounds=%d "
        "claims_drafted=%d claims_published=%d unconfirmed=%d check_failures=%s "
        "sample_size=%s evidence_kept=%d evidence_dropped=%d duration_s=%.1f "
        "author_model=%s review_model=%s",
        class_name, spec, content_type, outcome.outcome, outcome.reason, stats.rounds,
        stats.claims_drafted, stats.claims_published, stats.unconfirmed,
        ",".join(stats.check_failures) or "-", stats.sample_size, stats.evidence_kept,
        stats.evidence_dropped, time.monotonic() - started,
        settings.wcl_guide_model, settings.wcl_guide_review_model,
    )
    return outcome


async def _run(class_name: str, spec: str, content_type: str, stats: RunStats) -> RunOutcome:
    try:
        briefing = await build_briefing(class_name, spec, content_type)
    except PatchUnknown:
        return await _fail(class_name, spec, content_type, "patch_unknown")
    except SeasonUnknown:
        return await _fail(class_name, spec, content_type, "season_unknown")
    except Exception:  # noqa: BLE001 - a broken briefing is a failed run, not a crash
        logger.exception("guide briefing failed for %s %s %s", class_name, spec, content_type)
        return await _fail(class_name, spec, content_type, "briefing_error")

    try:
        data_sheet = await _data_sheet(briefing)
    except WclBudgetLow as exc:
        logger.info("guide run %s %s %s postponed: %s", class_name, spec, content_type, exc)
        return await _fail(class_name, spec, content_type, "wcl_budget")
    reports = await _open_reports(class_name, spec, content_type)
    try:
        fact_sheet = await build_fact_sheet(
            briefing,
            ability_names=[a.name for a in (data_sheet.abilities if data_sheet else [])],
            reports=[r.note for r in reports],
        )
        stats.sample_size = data_sheet.scope.sample_size if data_sheet else None
        stats.evidence_kept, stats.evidence_dropped = len(fact_sheet.items), len(fact_sheet.dropped)
        authored = await author_claims(briefing, fact_sheet, data_sheet)
        stats.claims_drafted = len(authored.claims)
    except GuideModelError as exc:
        logger.warning("guide model error for %s %s %s: %s", class_name, spec, content_type, exc)
        return await _fail(class_name, spec, content_type, "model_error")
    except Exception:  # noqa: BLE001
        logger.exception("guide generation failed for %s %s %s", class_name, spec, content_type)
        return await _fail(class_name, spec, content_type, "generation_error")

    if not authored.claims:
        return await _fail(class_name, spec, content_type, "no_supported_claims")
    try:
        loop = await review_loop(briefing, authored, fact_sheet, data_sheet, reports)
    except GuideModelError as exc:
        logger.warning("guide review failed for %s %s %s: %s", class_name, spec, content_type, exc)
        return await _fail(class_name, spec, content_type, "model_error")
    authored, rendered = loop.authored, loop.rendered
    stats.rounds = loop.rounds
    stats.unconfirmed = len(authored.unconfirmed)
    stats.check_failures = sorted({f.check for f in loop.failures})
    if loop.outcome == "empty":
        return await _fail(class_name, spec, content_type, "no_supported_claims")
    if loop.outcome == "hold":
        issues = [i.model_dump() for i in loop.issues] + [f.model_dump() for f in loop.failures]
        async with db_session.SessionLocal() as session:
            await repo.hold_spec_guide(
                session,
                class_name=class_name,
                spec=spec,
                content_type=content_type,
                draft={
                    "brief": rendered.brief.model_dump(mode="json"),
                    "claims": [c.model_dump(mode="json") for c in authored.claims],
                    "markdown": rendered.markdown,
                    "briefing": briefing.model_dump(mode="json"),
                    "generated_at": briefing.now_utc.isoformat(),
                },
                review_issues=issues,
            )
            await session.commit()
        await _resolve_reports(loop.report_verdicts)
        return RunOutcome(outcome="held", reason="review", rounds=loop.rounds)

    sources = cited_sources(authored.claims, fact_sheet)
    snapshot = EvidenceSnapshot(data_sheet=data_sheet, fact_sheet=fact_sheet)
    async with db_session.SessionLocal() as session:
        await repo.publish_spec_guide(
            session,
            class_name=class_name,
            spec=spec,
            content_type=content_type,
            markdown=rendered.markdown,
            brief=rendered.brief.model_dump(mode="json"),
            claims=[c.model_dump(mode="json") for c in authored.claims],
            game_patch=briefing.live_patch,
            season=briefing.mplus_season if content_type == "mplus" else None,
            generated_at=briefing.now_utc,
            sources=sources,
            major_cooldowns=brief_cooldowns(rendered.brief),
            briefing=briefing.model_dump(mode="json"),
            evidence=snapshot.model_dump(mode="json"),
        )
        await session.commit()
    await _resolve_reports(loop.report_verdicts)
    stats.claims_published = len(authored.claims)
    return RunOutcome(outcome="published", rounds=loop.rounds)
