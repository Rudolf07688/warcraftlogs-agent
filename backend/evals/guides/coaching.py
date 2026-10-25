"""Coaching runner for the accuracy check (FR-022, contracts/accuracy-check.md).

Each ``CoachingCase`` is one chat turn on a real log, run through the production agent
(``agent_runner.stream_response``) in a fresh session, with the profile context a player
of that spec would get. Scored by regex on the final answer, plus which content type of
guidance the agent was given or fetched.
"""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace
from typing import Any

from .fixtures import CoachingCase
from .scoring import GuideRecord, coaching_points, wrong_content_brief_use

logger = logging.getLogger(__name__)


def _character(case: CoachingCase) -> SimpleNamespace:
    """The case's player as a stand-in profile character (only the read attributes)."""
    return SimpleNamespace(
        name=case.player,
        server="",
        region="",
        class_name=case.class_name,
        active_spec=case.spec,
        raid_role=None,
    )


def install_brief_loader() -> None:
    """Register the backend's brief loader, as startup does (no-op before feature 015)."""
    try:
        from backend.app.services.guide import load_brief_record
        from wcl_agent.guides.guide_meta import set_brief_loader
    except ImportError:
        return
    set_brief_loader(load_brief_record)


async def build_case_preamble(
    case: CoachingCase, guides: dict[tuple[str, str, str], GuideRecord] | None = None
) -> tuple[str, list[str]]:
    """The preamble the player would get — through the production brief selection — and
    the content types of the guidance it carries.

    On a pre-feature checkout (the FR-024 baseline run) the old path is used: the spec's
    stored guide (a raid guide) is injected whatever the question was about.
    """
    from backend.app.services.profile_context import build_preamble

    try:
        from backend.app.services.guide import briefs_for_turn
    except ImportError:
        raid = (guides or {}).get((case.class_name, case.spec, "raid"))
        spec_guides = {(case.class_name, case.spec): raid.markdown} if raid and raid.markdown else {}
        preamble = build_preamble([_character(case)], [], None, spec_guides=spec_guides)
        return preamble, (["raid"] if spec_guides else [])

    turn = await briefs_for_turn([(case.class_name, case.spec)], case.question, None)
    preamble = build_preamble(
        [_character(case)],
        [],
        None,
        briefs=turn.briefs,
        available=turn.available,
        content_type=turn.content_type,
        content_type_note=turn.note,
    )
    return preamble, [record.content_type for record in turn.briefs.values()]


async def run_case(
    case: CoachingCase, *, model: str, guides: dict[tuple[str, str, str], GuideRecord] | None = None
) -> dict[str, Any]:
    """One turn → final text, tool calls, guidance content types, and the point verdicts."""
    from backend.app.agent_runner import stream_response

    preamble, briefs_used = await build_case_preamble(case, guides)
    tokens: list[str] = []
    tools: list[dict] = []
    error: str | None = None
    try:
        async for record in stream_response(
            model, f"eval-{uuid.uuid4().hex}", case.question, context_preamble=preamble or None
        ):
            kind = record.get("type")
            if kind == "token":
                tokens.append(record["text"])
            elif kind == "tool_start":
                tools.append({"name": record.get("name"), "args": record.get("args") or {}})
                if record.get("name") == "get_coaching_brief":
                    briefs_used.append(str((record.get("args") or {}).get("content_type") or "raid"))
    except Exception as exc:  # noqa: BLE001 - a failed run is reported, not fatal
        logger.exception("coaching case %s failed", case.id)
        error = f"{type(exc).__name__}: {exc}"
    answer = "".join(tokens)
    return {
        "id": case.id,
        "content_type": case.content_type,
        "error": error,
        "points": coaching_points(case, answer) if error is None else [],
        "briefs_used": briefs_used,
        "wrong_content_brief_use": wrong_content_brief_use(case, briefs_used),
        "tools": [t["name"] for t in tools],
        "answer": answer,
    }


def summarize(runs: list[dict]) -> dict[str, Any]:
    totals = {"raised": 0, "missed": 0, "contradicted": 0}
    for run in runs:
        for point in run["points"]:
            totals[point["verdict"]] += 1
    scored = sum(totals.values())
    return {
        **totals,
        "raised_rate": totals["raised"] / scored if scored else None,
        "runs": len(runs),
        "errors": sum(1 for r in runs if r["error"]),
        "wrong_content_brief_use": (
            sum(r["wrong_content_brief_use"] for r in runs) / len(runs) if runs else None
        ),
    }
