"""``get_coaching_brief`` — the verified coaching brief for one spec and content type.

Feature 015 (contracts/agent-context.md §2.2): the agent fetches a brief that was not
inlined in the turn context (budget, a friend's spec, or the other content type). Only
published, reviewed briefs are returned, and never the other content type's (FR-014).
"""

from __future__ import annotations

from typing import Any

from .guide_meta import get_brief
from ..tools.provenance import Provenance, with_envelope
from ..game.roster import resolve_spec, roster_snapshot

_LABEL = {"raid": "Raid", "mplus": "Mythic+"}


async def get_coaching_brief(class_name: str, spec_name: str, content_type: str = "raid") -> dict[str, Any]:
    """Get the verified coaching brief for a spec and content type (Raid or Mythic+).

    Use it before spec-specific coaching when the brief for the player's spec and the
    content type being discussed is not already in the context. Raid logs and boss
    pulls use "raid"; dungeon runs and keys use "mplus". Never apply one content type's
    brief to the other. The brief lists priorities, cooldowns, uptimes and common
    mistakes, each with a tag ([O] observed, [B] benchmark, [G] guidance, confidence
    H/M/L) and a LOG: line saying what to check in the log before calling it a mistake.

    Args:
        class_name (str): The class, any casing/spacing (e.g. "Mage", "Demon Hunter").
        spec_name (str): The spec (e.g. "Fire", "Devourer", "Beast Mastery").
        content_type (str): "raid" or "mplus".

    Returns:
        dict: {"status": "success", "brief": <text>, "content_type", "game_patch",
            "season", "freshness", "data_sufficient"} or {"status": "no_brief",
            "message"} when no verified guidance exists, or an error with the valid values.
    """
    if content_type not in _LABEL:
        return {
            "status": "error",
            "error_message": f"Unknown content_type '{content_type}'.",
            "valid_content_types": list(_LABEL),
        }
    entry = resolve_spec(class_name, spec_name)
    if entry is None:
        roster = roster_snapshot()
        cls = next(
            (c for c in roster.classes()
             if c.casefold() == (class_name or "").replace(" ", "").casefold()
             or roster.class_display(c).casefold() == (class_name or "").strip().casefold()),
            None,
        )
        return {
            "status": "error",
            "error_message": f"Unknown class/spec '{class_name} {spec_name}'.",
            "valid_specs": roster.specs_for(cls) if cls else [],
            "valid_classes": [] if cls else roster.classes(),
        }
    record = await get_brief(entry.class_name, entry.spec, content_type, mark_used=True)
    if record is None:
        return {
            "status": "no_brief",
            "content_type": content_type,
            "message": (
                f"No verified {_LABEL[content_type]} guidance for {entry.spec_display} "
                f"{entry.class_display}. Coach from measured log data only; do not apply "
                "the other content type's brief."
            ),
        }
    return with_envelope(
        {
            "status": "success",
            "brief": record.text,
            "content_type": record.content_type,
            "game_patch": record.game_patch,
            "season": record.season,
            "freshness": record.freshness,
            "data_sufficient": record.data_sufficient,
        },
        Provenance(),
    )
