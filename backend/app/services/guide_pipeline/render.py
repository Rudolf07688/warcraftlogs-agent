"""Stage 8: the coaching brief, its agent-facing text, and the readable guide markdown.

Everything here is code templates over claims (never free model text), so structure, size
and "every statement maps to a claim" are guaranteed (FR-010, FR-036 ``guide_extra_claim``).
"""

from __future__ import annotations

import re

from .models import (
    SECTION_ORDER,
    BriefCooldown,
    BriefItem,
    CoachingBrief,
    DataSheet,
    GenerationBriefing,
    GuideClaim,
    LogCheck,
)
from .prompts import CONTENT_LABEL

SECTION_TITLE = {
    "overview": "Overview",
    "priority": "Priority",
    "cooldowns": "Major cooldowns",
    "uptimes": "Uptimes",
    "talents": "Talents",
    "stats": "Stats",
    "mistakes": "Common mistakes",
    "benchmarks": "Benchmarks",
    "content_notes": "Encounter notes",
}
_CONTENT_NOTES_TITLE = {"raid": "Boss notes", "mplus": "Dungeon and affix notes"}

# Every rendered claim bullet ends with this marker; the `guide_extra_claim` check reads it.
CLAIM_MARKER_RE = re.compile(r"<!-- (c\d+) -->")


def _section_title(section: str, content_type: str) -> str:
    if section == "content_notes":
        return _CONTENT_NOTES_TITLE[content_type]
    return SECTION_TITLE[section]


def _bullet(claim: GuideClaim) -> str:
    return f"- {claim.text} <!-- {claim.id} -->"


def render_guide_markdown(briefing: GenerationBriefing, claims: list[GuideClaim]) -> str:
    """The readable guide: header, one section per claim section in a fixed order, one
    bullet per claim, then what the coach looks for in a log (FR-017)."""
    label = CONTENT_LABEL[briefing.content_type]
    provenance = [f"Patch {briefing.live_patch}"]
    if briefing.content_type == "mplus" and briefing.mplus_season:
        provenance.append(briefing.mplus_season)
    elif briefing.content_type == "raid" and briefing.raid_tier:
        provenance.append(briefing.raid_tier)
    provenance.append(f"generated {briefing.now_utc:%Y-%m-%d}")
    lines = [
        f"# {briefing.spec} {briefing.class_display} — {label}",
        "",
        f"*{' · '.join(provenance)}*",
    ]
    by_section: dict[str, list[GuideClaim]] = {}
    for claim in claims:
        by_section.setdefault(claim.section, []).append(claim)
    for section in SECTION_ORDER:
        items = by_section.get(section)
        if not items:
            continue
        lines += ["", f"## {_section_title(section, briefing.content_type)}", ""]
        lines += [_bullet(c) for c in items]
    checks = [c for c in claims if c.log_check is not None]
    if checks:
        # FR-017: the human view of what the agent will look for in a log.
        lines += ["", "## What the coach looks for", ""]
        lines += [f"- {c.log_check.expectation} <!-- {c.id} -->" for c in checks]
    # "Not covered" areas and sources are stored as fields (brief.unconfirmed, sources) and
    # rendered by the viewer, so the markdown holds only claim-backed text.
    return "\n".join(lines) + "\n"


def rendered_claim_ids(markdown: str) -> list[str]:
    """The claim ids behind the rendered bullets, in order."""
    return CLAIM_MARKER_RE.findall(markdown or "")


def strip_claim_markers(markdown: str | None) -> str | None:
    """The guide as people read it: the per-bullet claim markers removed."""
    if markdown is None:
        return None
    return re.sub(r" ?<!-- c\d+ -->", "", markdown)


# --- the coaching brief (data-model §4.6, contracts/agent-context.md §1) ------------------

_EVIDENCE_TAG = {"observed": "O", "benchmarked": "B", "guidance": "G"}
_CONFIDENCE_TAG = {"high": "H", "medium": "M", "low": "L"}
_FRESHNESS_LABEL = {
    "current": "current",
    "possibly_stale": "possibly stale — may be out of date",
    "unknown": "patch unknown — may be out of date",
}


def _sheet_ability_id(ability_id: int | None, data_sheet: DataSheet | None) -> int | None:
    """Ability ids come only from the data sheet (FR-034): anything else is dropped."""
    if ability_id is None or data_sheet is None:
        return None
    return ability_id if ability_id in data_sheet.ability_ids() else None


def _checked(log_check: LogCheck | None, data_sheet: DataSheet | None) -> LogCheck | None:
    if log_check is None:
        return None
    return log_check.model_copy(update={"ability_id": _sheet_ability_id(log_check.ability_id, data_sheet)})


def data_scope_line(data_sheet: DataSheet | None) -> str | None:
    if data_sheet is None:
        return None
    scope = data_sheet.scope
    where = scope.zone_name or "unknown zone"
    if scope.key_level_floor:
        where += f", +{scope.key_level_floor} and up"
    return f"{scope.sample_size} top logs ({scope.metric}) in {where}"


def build_brief(
    briefing: GenerationBriefing,
    claims: list[GuideClaim],
    unconfirmed: list[str],
    data_sheet: DataSheet | None = None,
) -> CoachingBrief:
    """The agent-facing brief, built by code from the (confirmed) claims."""
    brief = CoachingBrief(
        class_name=briefing.class_name,
        spec=briefing.spec,
        content_type=briefing.content_type,
        role=briefing.role,
        patch=briefing.live_patch,
        season=briefing.mplus_season if briefing.content_type == "mplus" else None,
        generated_at=briefing.now_utc,
        unconfirmed=list(unconfirmed),
        data_sufficient=bool(data_sheet is not None and data_sheet.sufficient),
        data_scope=data_scope_line(data_sheet),
    )
    for claim in claims:
        if claim.section == "overview":
            continue  # the readable guide's intro; the coach needs checkable items
        check = _checked(claim.log_check, data_sheet)
        if claim.section == "cooldowns":
            brief.cooldowns.append(
                BriefCooldown(
                    name=claim.ability_name or claim.text[:80],
                    ability_id=_sheet_ability_id(claim.ability_id, data_sheet),
                    cooldown_s=claim.cooldown_s,
                    charges=claim.charges or 1,
                    usage=claim.text,
                    log_check=check,
                    evidence_type=claim.evidence_type,
                    confidence=claim.confidence,
                    claim_id=claim.id,
                )
            )
            continue
        getattr(brief, claim.section).append(
            BriefItem(
                text=claim.text,
                evidence_type=claim.evidence_type,
                confidence=claim.confidence,
                log_check=check,
                claim_id=claim.id,
            )
        )
    return brief


def _clean(text: str) -> str:
    """Brief text is plain: no braces (ADK placeholders) and no line breaks inside items."""
    return " ".join(text.replace("{", "(").replace("}", ")").split())


def _tag(evidence_type: str, confidence: str) -> str:
    return f"[{_EVIDENCE_TAG[evidence_type]},{_CONFIDENCE_TAG[confidence]}]"


def _log(check: LogCheck | None) -> str:
    if check is None:
        return ""
    ability = f" (id {check.ability_id})" if check.ability_id else ""
    return f" LOG: {check.signal}{ability}: {_clean(check.expectation)}"


def _item_line(item: BriefItem, prefix: str = "-") -> str:
    return f"{prefix} {_tag(item.evidence_type, item.confidence)} {_clean(item.text)}{_log(item.log_check)}"


def render_brief_text(brief: CoachingBrief, freshness: str = "current") -> str:
    """The compact plain text the agent reads (contracts/agent-context.md §1)."""
    label = CONTENT_LABEL[brief.content_type]
    head = [f"{brief.spec} {brief.class_name}", label, f"patch {brief.patch}"]
    if brief.season:
        head.append(brief.season)
    head += [f"generated {brief.generated_at:%Y-%m-%d}", _FRESHNESS_LABEL.get(freshness, freshness)]
    if brief.data_scope:
        sufficiency = "sufficient" if brief.data_sufficient else "too small — numbers are context only"
        data = f"Data: observed from {brief.data_scope}, {sufficiency}."
    else:
        data = "Data: no measured Warcraft Logs sample; guidance from current sources only."
    lines = [
        "COACHING BRIEF — " + " · ".join(_clean(h) for h in head),
        data,
        "Tags: [O]=observed in top logs [B]=benchmark [G]=guidance from current sources; conf H/M/L.",
    ]
    if brief.priority:
        lines += ["", "PRIORITY (in order)"]
        lines += [_item_line(item, f"{n}.") for n, item in enumerate(brief.priority, start=1)]
    if brief.cooldowns:
        lines += ["", "MAJOR COOLDOWNS"]
        for cd in brief.cooldowns:
            ident = f" (id {cd.ability_id})" if cd.ability_id else ""
            timing = f" {cd.cooldown_s:g} s ×{cd.charges}" if cd.cooldown_s else ""
            lines.append(
                f"- {_clean(cd.name)}{ident}{timing} — {_clean(cd.usage)} "
                f"{_tag(cd.evidence_type, cd.confidence)}{_log(cd.log_check)}"
            )
    titled = {
        "uptimes": "UPTIMES",
        "mistakes": "COMMON MISTAKES (check in the log)",
        "benchmarks": "BENCHMARKS",
        "talents": "TALENTS (observed, not prescriptive)",
        "stats": "STATS (observed, not prescriptive)",
        "content_notes": "BOSS NOTES" if brief.content_type == "raid" else "DUNGEON AND AFFIX NOTES",
    }
    for section in ("uptimes", "mistakes", "benchmarks", "talents", "stats", "content_notes"):
        items = getattr(brief, section)
        if items:
            lines += ["", titled[section]]
            lines += [_item_line(item) for item in items]
    if brief.unconfirmed:
        lines += ["", "NOT COVERED / UNCONFIRMED (no current source confirmed these; do not coach on them)"]
        lines += [f"- {_clean(area)}" for area in brief.unconfirmed]
    return "\n".join(lines)
