"""Stage 5: deterministic checks that gate publication (FR-036).

Code, not a model, decides whether a guide is structurally consistent: abilities exist in
the measured data, stated cooldowns agree with how fast top players actually cast them,
patch and season match the briefing, every cited source is live retail for this content
type and not older than a hotfix that touched the spec, every claim cites evidence, coach
checks are present, the brief fits its budget and the readable guide holds only claims.
"""

from __future__ import annotations

import re

from wcl_agent.patch import parse_patch

from ...config import settings
from .authoring import known_evidence_ids
from .models import (
    LOG_CHECK_SECTIONS,
    CheckFailure,
    CoachingBrief,
    DataSheet,
    FactSheet,
    GenerationBriefing,
    GuideClaim,
)
from .render import rendered_claim_ids
from .research import environment_marker

COOLDOWN_TOO_FAST = 0.8  # cast faster than 0.8 × the stated cooldown ⇒ the number is wrong
COOLDOWN_TOO_SLOW = 2.5  # never cast within 2.5 × the stated cooldown ⇒ the number is wrong
FREQUENT_USES_PER_FIGHT = 3  # the slow rule only applies to abilities used this often
TYPICAL_FIGHT_MIN = 5.0  # casts/min → uses per fight for the frequency rule

_BULLET_RE = re.compile(r"^- ")


def _fail(check: str, item: str, detail: str) -> CheckFailure:
    return CheckFailure(check=check, item=item, detail=detail[:300])


def _sheet_names(data_sheet: DataSheet) -> dict[str, int]:
    names = {a.name.casefold(): a.ability_id for a in data_sheet.abilities}
    names.update({u.name.casefold(): u.ability_id for u in data_sheet.uptimes})
    return names


def check_abilities(brief: CoachingBrief, data_sheet: DataSheet | None) -> list[CheckFailure]:
    """``ability_unknown`` + ``cooldown_mismatch`` — only against a sufficient data sheet."""
    if data_sheet is None or not data_sheet.sufficient:
        return []  # nothing measured to check against (the brief says so)
    failures: list[CheckFailure] = []
    names = _sheet_names(data_sheet)
    by_id = {a.ability_id: a for a in data_sheet.abilities}
    for cd in brief.cooldowns:
        ability_id = cd.ability_id or names.get(cd.name.casefold())
        if ability_id is None:
            failures.append(_fail(
                "ability_unknown", cd.claim_id,
                f"'{cd.name}' is not cast by any of the {data_sheet.scope.sample_size} top logs measured",
            ))
            continue
        observed = by_id.get(ability_id)
        if not (observed and observed.min_gap_s and cd.cooldown_s):
            continue
        lower = COOLDOWN_TOO_FAST * cd.cooldown_s
        if cd.charges <= 1 and observed.min_gap_s < lower:
            failures.append(_fail(
                "cooldown_mismatch", cd.claim_id,
                f"'{cd.name}' stated {cd.cooldown_s:g} s, but top players recast it after {observed.min_gap_s:g} s",
            ))
        uses = (observed.casts_per_min_median or 0) * TYPICAL_FIGHT_MIN
        if uses >= FREQUENT_USES_PER_FIGHT and observed.min_gap_s > COOLDOWN_TOO_SLOW * cd.cooldown_s:
            failures.append(_fail(
                "cooldown_mismatch", cd.claim_id,
                f"'{cd.name}' stated {cd.cooldown_s:g} s, but no top player recast it within {observed.min_gap_s:g} s",
            ))
    for section in ("uptimes", "benchmarks", "mistakes"):
        for item in getattr(brief, section):
            check = item.log_check
            if check and check.ability_id and check.ability_id not in data_sheet.ability_ids():
                failures.append(_fail("ability_unknown", item.claim_id, f"ability id {check.ability_id} not in the data sheet"))
    return failures


def check_versions(brief: CoachingBrief, briefing: GenerationBriefing) -> list[CheckFailure]:
    """``patch_mismatch`` / ``season_mismatch``."""
    failures = []
    if brief.patch != briefing.live_patch:
        failures.append(_fail("patch_mismatch", "brief", f"brief patch {brief.patch} ≠ live {briefing.live_patch}"))
    if briefing.content_type == "mplus" and brief.season != briefing.mplus_season:
        failures.append(_fail(
            "season_mismatch", "brief", f"brief season {brief.season} ≠ live {briefing.mplus_season}",
        ))
    return failures


def check_sources(
    claims: list[GuideClaim], fact_sheet: FactSheet, briefing: GenerationBriefing
) -> list[CheckFailure]:
    """``source_env`` and ``source_prehotfix`` for every cited research item."""
    failures = []
    items = fact_sheet.by_id()
    live = parse_patch(briefing.live_patch)
    hotfix_day = briefing.latest_hotfix_at.date() if briefing.latest_hotfix_at else None
    for claim in claims:
        for ref in claim.evidence_refs:
            item = items.get(ref)
            if item is None:
                continue
            problems = []
            if item.product != "retail" or item.environment != "live":
                problems.append(f"{item.product}/{item.environment}")
            if environment_marker(item.source_url, item.source_title):
                problems.append("PTR/beta/Classic page")
            tagged = parse_patch(item.patch)
            if tagged and live and tagged < live:
                problems.append(f"patch {item.patch} < live {briefing.live_patch}")
            if item.content_type not in ("both", briefing.content_type):
                problems.append(f"{item.content_type} source for a {briefing.content_type} guide")
            if problems:
                failures.append(_fail("source_env", claim.id, f"{ref}: " + "; ".join(problems)))
            if (
                briefing.hotfix_touches_spec
                and hotfix_day
                and item.source_date
                and item.source_date < hotfix_day
                and not item.possibly_stale
            ):
                failures.append(_fail(
                    "source_prehotfix", claim.id,
                    f"{ref} dated {item.source_date} predates the {hotfix_day} hotfix to this spec",
                ))
    return failures


def check_claims(
    claims: list[GuideClaim], fact_sheet: FactSheet, data_sheet: DataSheet | None
) -> list[CheckFailure]:
    """``claim_unreferenced`` + ``log_check_missing``."""
    known = known_evidence_ids(fact_sheet, data_sheet)
    failures = []
    for claim in claims:
        if not any(ref in known for ref in claim.evidence_refs):
            failures.append(_fail("claim_unreferenced", claim.id, "no evidence reference resolves"))
        if claim.section in LOG_CHECK_SECTIONS and (claim.log_check is None or not claim.log_check.expectation):
            failures.append(_fail("log_check_missing", claim.id, f"{claim.section} claim without a log check"))
    return failures


def check_rendering(
    claims: list[GuideClaim], brief_text: str, markdown: str
) -> list[CheckFailure]:
    """``brief_too_long`` + ``guide_extra_claim``."""
    failures = []
    limit = settings.wcl_guide_brief_max_chars
    if len(brief_text) > limit:
        failures.append(_fail("brief_too_long", "brief", f"{len(brief_text)} characters > {limit}"))
    ids = {c.id for c in claims}
    for line in markdown.splitlines():
        if not _BULLET_RE.match(line):
            continue
        marked = rendered_claim_ids(line)
        if not marked or any(i not in ids for i in marked):
            failures.append(_fail("guide_extra_claim", line[:60], "a guide bullet maps to no claim"))
    return failures


def run_checks(
    briefing: GenerationBriefing,
    claims: list[GuideClaim],
    brief: CoachingBrief,
    brief_text: str,
    markdown: str,
    data_sheet: DataSheet | None,
    fact_sheet: FactSheet,
) -> list[CheckFailure]:
    """Every deterministic check (contracts/guide-pipeline.md §Deterministic checks)."""
    return [
        *check_versions(brief, briefing),
        *check_abilities(brief, data_sheet),
        *check_sources(claims, fact_sheet, briefing),
        *check_claims(claims, fact_sheet, data_sheet),
        *check_rendering(claims, brief_text, markdown),
    ]
