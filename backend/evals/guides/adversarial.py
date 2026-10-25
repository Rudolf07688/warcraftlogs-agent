"""Evaluators for the six adversarial cases (FR-021).

Each case names an evaluator (``check``) that feeds the fixture's inputs to the pipeline
component responsible for that defence and compares the outcome with ``expected``. A
component that does not exist yet fails its case with "not implemented" — that is the
baseline's honest answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from .fixtures import AdversarialCase

Evaluator = Callable[[AdversarialCase], Awaitable[tuple[bool, str]]]


def _briefing(case: AdversarialCase, **over: Any):
    from backend.app.services.guide_pipeline.models import GenerationBriefing

    fields = {
        "now_utc": datetime(2026, 10, 18, tzinfo=UTC),
        "content_type": case.content_type,
        "class_name": "Mage",
        "class_display": "Mage",
        "spec": "Fire",
        "role": "dps",
        "class_specs": ["Arcane", "Fire", "Frost"],
        "live_patch": "12.1.5",
        "mplus_season": "Mythic+ Season 2" if case.content_type == "mplus" else None,
    }
    fields.update(case.inputs.get("briefing") or {})
    fields.update(over)
    return GenerationBriefing.model_validate(fields)


async def _old_similar_guide(case: AdversarialCase) -> tuple[bool, str]:
    """An older guide must be labelled possibly stale wherever the agent sees it."""
    from backend.app.services.guide_pipeline.models import CoachingBrief
    from backend.app.services.guide_pipeline.render import render_brief_text
    from wcl_agent.game.patch import guide_freshness

    stored = case.inputs["stored_guide"]
    freshness = guide_freshness(stored["patch"], case.inputs["live_patch"])
    brief = CoachingBrief.model_validate(stored["brief"])
    text = render_brief_text(brief, freshness)
    want = case.expected["freshness"]
    label_ok = case.expected["brief_label"].casefold() in text.casefold()
    return freshness == want and label_ok, f"freshness={freshness}, label_in_brief={label_ok}"


async def _filter(case: AdversarialCase):
    from backend.app.services.guide_pipeline.models import EvidenceItem
    from backend.app.services.guide_pipeline.research import filter_evidence

    items = [EvidenceItem.model_validate(i) for i in case.inputs["evidence"]]
    return filter_evidence(items, _briefing(case))


async def _ptr_newer_than_live(case: AdversarialCase) -> tuple[bool, str]:
    """A PTR page newer than live must be dropped, never citable."""
    sheet = await _filter(case)
    dropped = {d.url for d in sheet.dropped}
    citable = {i.source_url for i in sheet.items if i.id in sheet.citable_ids()}
    want_dropped = set(case.expected["dropped_urls"])
    want_citable = set(case.expected["citable_urls"])
    ok = want_dropped <= dropped and not (want_dropped & citable) and want_citable <= citable
    return ok, f"dropped={sorted(dropped)}, citable={sorted(citable)}"


async def _conflicting_guides(case: AdversarialCase) -> tuple[bool, str]:
    """Two equal-tier sources disagreeing: record the conflict, cite neither."""
    sheet = await _filter(case)
    conflicted = {i for c in sheet.conflicts for i in c.item_ids}
    want = set(case.expected["conflicted_ids"])
    ok = want <= conflicted and not (want & sheet.citable_ids())
    return ok, f"conflicts={sorted(conflicted)}, citable={sorted(sheet.citable_ids())}"


async def _hotfix_after_publish(case: AdversarialCase) -> tuple[bool, str]:
    """A hotfix touching the spec after publication marks the guide stale."""
    from backend.app.services.guide import compute_stale_reason

    args = dict(case.inputs["stale_scan"])
    for key in ("generated_at", "hotfix_at"):
        if args.get(key):
            args[key] = datetime.fromisoformat(args[key])
    reason = compute_stale_reason(**args)
    return reason == case.expected["stale_reason"], f"stale_reason={reason}"


async def _new_spec_thin_data(case: AdversarialCase) -> tuple[bool, str]:
    """A thin data sample is shown to the author as not citable guidance."""
    from backend.app.services.guide_pipeline.models import DataSheet
    from backend.app.services.guide_pipeline.prompts import format_data_sheet

    sheet = DataSheet.model_validate(case.inputs["data_sheet"])
    text = format_data_sheet(sheet)
    marker = case.expected["marker"]
    ok = (not sheet.sufficient) and marker.casefold() in text.casefold()
    return ok, f"sufficient={sheet.sufficient}, marker_present={marker.casefold() in text.casefold()}"


async def _raid_question_only_mplus_brief(case: AdversarialCase) -> tuple[bool, str]:
    """A raid question with only a Mythic+ brief stored gets no brief, not the M+ one."""
    from backend.app.services.content_type import classify_content_type
    from wcl_agent.guides import guide_meta

    routed = classify_content_type(case.inputs["question"], None, "Mythic+ Season 2", [], [])
    content_type = "raid" if routed == "unknown" else routed
    stored = case.inputs["stored_content_type"]

    async def loader(class_name: str, spec: str, ct: str):
        if ct != stored:
            return None
        return guide_meta.BriefRecord(
            class_name=class_name, spec=spec, content_type=ct, text="brief", cooldowns=(),
            game_patch="12.1", season=None, generated_at=None, freshness="current",
            data_sufficient=True,
        )

    guide_meta.set_brief_loader(loader)
    try:
        brief = await guide_meta.get_brief("Mage", "Fire", content_type)
    finally:
        guide_meta.clear_brief_loader()
    ok = content_type == case.expected["content_type"] and (brief is not None) == case.expected["brief_given"]
    return ok, f"content_type={content_type}, brief_given={brief is not None}"


EVALUATORS: dict[str, Evaluator] = {
    "old_similar_guide": _old_similar_guide,
    "ptr_newer_than_live": _ptr_newer_than_live,
    "conflicting_guides": _conflicting_guides,
    "hotfix_after_publish": _hotfix_after_publish,
    "new_spec_thin_data": _new_spec_thin_data,
    "raid_question_only_mplus_brief": _raid_question_only_mplus_brief,
}


async def evaluate(case: AdversarialCase) -> dict[str, Any]:
    evaluator = EVALUATORS.get(case.check)
    if evaluator is None:
        return {"case": case.case, "passed": False, "detail": f"unknown check {case.check!r}"}
    try:
        passed, detail = await evaluator(case)
    except (ImportError, AttributeError, NotImplementedError) as exc:
        return {"case": case.case, "passed": False, "detail": f"not implemented: {exc}"}
    except Exception as exc:  # noqa: BLE001 - a crashing defence is a failing defence
        return {"case": case.case, "passed": False, "detail": f"error: {type(exc).__name__}: {exc}"}
    return {"case": case.case, "passed": passed, "detail": detail}
