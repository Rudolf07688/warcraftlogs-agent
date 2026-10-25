"""Deterministic scorers for the accuracy check (contracts/accuracy-check.md §Scoring).

Pure functions over stored guides and fixture cases, so the scoring itself is unit-tested
without live calls. Regex matching on purpose: an LLM judge would share the blind spots
being measured (research R15).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from wcl_agent.game.patch import parse_patch

try:
    from backend.app.services.guide_pipeline.research import environment_marker
except ImportError:  # a pre-feature checkout (baseline run, FR-024): same rule, inline
    _PRE_FEATURE_MARKERS = re.compile(
        r"(?:\bptr\b|/ptr[/-]|ptr-\d|\bbeta\b|/beta[/-]|\bclassic\b|/classic[/-]|\bwotlk\b|"
        r"\bcata(?:clysm)?\b|mop-classic|\bsod\b|season of discovery|\bvanilla\b)",
        re.I,
    )

    def environment_marker(url: str | None, title: str | None = None) -> str | None:
        return "non-live" if _PRE_FEATURE_MARKERS.search(f"{url or ''} {title or ''}") else None

from .fixtures import CoachingCase, FactCase

# Release-gate thresholds (FR-025).
MIN_CLAIM_SUPPORT = 0.95
MIN_PATCH_ACCURACY = 1.0

EXIT_PASSED, EXIT_FAILED, EXIT_ERROR = 0, 1, 2


@dataclass
class GuideRecord:
    """The published version of one guide, as scored."""

    class_name: str
    spec: str
    content_type: str
    status: str
    markdown: str | None = None
    game_patch: str | None = None
    season: str | None = None
    sources: list[dict] = field(default_factory=list)
    claims: list[dict] | None = None
    brief: dict | None = None
    evidence: dict | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return self.class_name, self.spec, self.content_type

    @property
    def published(self) -> bool:
        return bool(self.markdown or self.brief)

    @property
    def unconfirmed(self) -> list[str]:
        return list((self.brief or {}).get("unconfirmed") or [])


def _hits(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(p, text, re.I | re.M) for p in patterns)


# --- facts -----------------------------------------------------------------------------


def score_fact(text: str | None, unconfirmed: list[str], case: FactCase) -> dict[str, Any]:
    """``correct`` | ``omitted`` | ``wrong`` for one fact against one guide text."""
    text = text or ""
    if case.expected == "present":
        if _hits(case.contradict, text):
            verdict = "wrong"
        elif _hits(case.match, text):
            verdict = "correct"
        else:
            verdict = "omitted"
    else:
        verdict = "wrong" if _hits(case.match, text) else "correct"
    listed = _hits(case.match, "\n".join(unconfirmed)) if unconfirmed else False
    return {"id": case.id, "verdict": verdict, "listed_unconfirmed": listed}


def score_facts(text: str | None, unconfirmed: list[str], cases: list[FactCase]) -> list[dict]:
    return [score_fact(text, unconfirmed, c) for c in cases]


def fact_totals(results: Iterable[dict]) -> dict[str, int]:
    totals = {"correct": 0, "omitted": 0, "wrong": 0}
    for r in results:
        totals[r["verdict"]] += 1
    return totals


def abstention_quality(totals: dict[str, int]) -> float | None:
    """omitted ÷ (omitted + wrong): how often an unsure guide leaves a fact out rather
    than getting it wrong. ``None`` when there was nothing to abstain on."""
    denom = totals["omitted"] + totals["wrong"]
    return totals["omitted"] / denom if denom else None


# --- sources ---------------------------------------------------------------------------


def cited_sources(guide: GuideRecord) -> list[dict]:
    """The published sources plus every fact-sheet item a claim cites."""
    sources = [s for s in guide.sources if isinstance(s, dict) and s.get("uri")]
    items = ((guide.evidence or {}).get("fact_sheet") or {}).get("items") or []
    cited_ids = {r for c in guide.claims or [] for r in (c.get("evidence_refs") or [])}
    seen = {s["uri"] for s in sources}
    for item in items:
        if item.get("id") in cited_ids and item.get("source_url") not in seen:
            seen.add(item["source_url"])
            sources.append(
                {
                    "uri": item["source_url"],
                    "title": item.get("source_title"),
                    "environment": item.get("environment"),
                    "product": item.get("product"),
                    "patch": item.get("patch"),
                    "tier": item.get("tier"),
                }
            )
    return sources


def source_leaks(source: dict) -> bool:
    """A cited source is PTR / beta / Classic by its URL, title or stored tags."""
    if environment_marker(source.get("uri"), source.get("title")):
        return True
    env, product = source.get("environment"), source.get("product")
    return (env not in (None, "live")) or (product not in (None, "retail"))


def leakage(sources: list[dict]) -> float | None:
    if not sources:
        return None
    return sum(source_leaks(s) for s in sources) / len(sources)


def current_source_precision(sources: list[dict], live_patch: str | None) -> float | None:
    """Share of cited sources valid for the live patch: not leaking, not tier 4, and not
    tagged with an older patch."""
    if not sources:
        return None
    live = parse_patch(live_patch)

    def valid(s: dict) -> bool:
        if source_leaks(s) or s.get("tier") == 4:
            return False
        tagged = parse_patch(s.get("patch"))
        return not (tagged and live and tagged < live)

    return sum(valid(s) for s in sources) / len(sources)


# --- guides ----------------------------------------------------------------------------


def patch_correct(guide: GuideRecord, live_patch: str | None, live_season: str | None) -> bool:
    """The published patch (major.minor) — and, for Mythic+, the season — equal live."""
    stated, live = parse_patch(guide.game_patch), parse_patch(live_patch)
    if stated is None or live is None or stated != live:
        return False
    if guide.content_type == "mplus":
        return bool(guide.season) and guide.season == live_season
    return True


def patch_accuracy(
    guides: list[GuideRecord], live_patch: str | None, live_season: str | None
) -> float | None:
    published = [g for g in guides if g.published]
    if not published:
        return None
    return sum(patch_correct(g, live_patch, live_season) for g in published) / len(published)


def claim_support(guides: list[GuideRecord]) -> dict[str, Any]:
    """Confirmed ÷ all published claims, from the stored review verdicts. A claim with no
    verdict counts as unknown (not confirmed); a guide without claims adds ``unscored``."""
    confirmed = total = unknown = unscored = 0
    for g in guides:
        if not g.published:
            continue
        if not g.claims:
            unscored += 1
            continue
        for c in g.claims:
            total += 1
            verdict = c.get("verdict")
            if verdict == "confirmed":
                confirmed += 1
            elif verdict is None:
                unknown += 1
    rate = confirmed / total if total else None
    return {"rate": rate, "confirmed": confirmed, "claims": total, "unknown": unknown, "unscored_guides": unscored}


def spec_coverage(roster: Iterable[tuple[str, str]], listed: Iterable[tuple[str, str]]) -> float | None:
    roster = set(roster)
    if not roster:
        return None
    return len(roster & set(listed)) / len(roster)


# --- coaching --------------------------------------------------------------------------


def coaching_points(case: CoachingCase, answer: str) -> list[dict]:
    """Per expected point: ``raised`` | ``missed`` | ``contradicted``."""
    results = []
    for point in case.expected_points:
        if _hits(point.contradict, answer):
            verdict = "contradicted"
        elif point.kind == "not_contradict" or _hits(point.match, answer):
            verdict = "raised"
        else:
            verdict = "missed"
        results.append({"id": point.id, "kind": point.kind, "verdict": verdict})
    return results


def wrong_content_brief_use(case: CoachingCase, briefs_used: list[str]) -> bool:
    """The run was given or fetched a brief of the other content type."""
    return any(ct != case.content_type for ct in briefs_used)


# --- gate ------------------------------------------------------------------------------


def gate(report: dict[str, Any]) -> tuple[bool, list[str]]:
    """The release gate (FR-025, SC-002/003/008/009) → ``(passed, reasons it failed)``."""
    m = report.get("metrics") or {}
    reasons: list[str] = []
    if (m.get("leakage_rate") or 0) > 0:
        reasons.append(f"leakage_rate {m['leakage_rate']:.2f} > 0")
    if (m.get("wrong_content_brief_use") or 0) > 0:
        reasons.append(f"wrong_content_brief_use {m['wrong_content_brief_use']:.2f} > 0")
    pa = m.get("patch_accuracy")
    if pa is None or pa < MIN_PATCH_ACCURACY:
        reasons.append(f"patch_accuracy {pa} < {MIN_PATCH_ACCURACY}")
    cs = m.get("claim_support_rate")
    if cs is None or cs < MIN_CLAIM_SUPPORT:
        reasons.append(f"claim_support_rate {cs} < {MIN_CLAIM_SUPPORT}")
    wrong_facts = (m.get("facts") or {}).get("wrong", 0)
    if wrong_facts:
        reasons.append(f"{wrong_facts} wrong fact(s)")
    failed_cases = [c["case"] for c in report.get("adversarial") or [] if not c.get("passed")]
    if failed_cases:
        reasons.append(f"adversarial failed: {', '.join(failed_cases)}")
    contradicted = (m.get("coaching") or {}).get("contradicted", 0)
    if contradicted:
        reasons.append(f"{contradicted} contradicted coaching point(s)")
    return not reasons, reasons


def exit_code(report: dict[str, Any] | None) -> int:
    if report is None or report.get("error"):
        return EXIT_ERROR
    return EXIT_PASSED if report.get("gate", {}).get("passed") else EXIT_FAILED


def deltas(report: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Numeric metric changes against the baseline, plus the SC-010/SC-011 targets."""
    if not baseline:
        return {}
    now, base = report.get("metrics") or {}, baseline.get("metrics") or {}
    out: dict[str, Any] = {}
    for key, value in now.items():
        prev = base.get(key)
        if isinstance(value, (int, float)) and isinstance(prev, (int, float)):
            out[key] = round(value - prev, 4)
    wrong_now = _wrong_share(now.get("facts"))
    wrong_base = _wrong_share(base.get("facts"))
    if wrong_now is not None and wrong_base:
        out["wrong_fact_share_reduction"] = round(1 - wrong_now / wrong_base, 4)  # SC-010 ≥ 0.8
    raised_now = (now.get("coaching") or {}).get("raised_rate")
    raised_base = (base.get("coaching") or {}).get("raised_rate")
    if raised_now is not None and raised_base is not None:
        out["coaching_raised_rate"] = round(raised_now - raised_base, 4)  # SC-011
    return out


def _wrong_share(facts: dict | None) -> float | None:
    if not facts:
        return None
    total = sum(facts.get(k, 0) for k in ("correct", "omitted", "wrong"))
    return facts.get("wrong", 0) / total if total else None
