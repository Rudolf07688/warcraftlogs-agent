"""Distinct-encounter extraction from a ``get_report_fights`` result (US2/US4).

A report's fight list contains one entry per pull, so the same boss appears many
times (and trash pulls have a null ``encounterID``). This collapses it to the
distinct bosses — the shape both the sidebar summary (US2) and the boss-focus
checkboxes (US4) consume, and what we persist on ``TrackedRaid.encounters``.
"""

from __future__ import annotations

from typing import Any


def encounters_from_tool(name: str, ok: bool, result: dict[str, Any]) -> list[dict]:
    """Return distinct bosses ``[{encounter_id, name, difficulty, kill}]`` or ``[]``.

    Only produces output for a successful ``get_report_fights`` call. Dedup is by
    ``encounter_id``; trash pulls / null ``encounterID`` are excluded; ``kill`` is
    ``True`` if *any* pull of that encounter was a kill.
    """
    if name != "get_report_fights" or not ok or not isinstance(result, dict):
        return []
    fights = result.get("fights")
    if not isinstance(fights, list):
        return []

    by_id: dict[int, dict] = {}
    for fight in fights:
        if not isinstance(fight, dict):
            continue
        enc_id = fight.get("encounterID")
        if not isinstance(enc_id, int) or enc_id == 0:
            continue  # trash pull / non-encounter
        kill = bool(fight.get("kill"))
        existing = by_id.get(enc_id)
        if existing is None:
            by_id[enc_id] = {
                "encounter_id": enc_id,
                "name": fight.get("name") or f"Encounter {enc_id}",
                "difficulty": fight.get("difficulty"),
                "kill": kill,
            }
        else:
            # Any kill across pulls counts as a kill; keep the first known name.
            existing["kill"] = existing["kill"] or kill
            if not existing.get("name") and fight.get("name"):
                existing["name"] = fight["name"]

    return list(by_id.values())


def merge_encounters(existing: list[dict] | None, incoming: list[dict] | None) -> list[dict]:
    """Merge two distinct-encounter lists by ``encounter_id`` (US2 backfill).

    Keeps every known boss; a later kill upgrades an earlier non-kill. Never
    duplicates an encounter already present.
    """
    by_id: dict[int, dict] = {}
    for item in (existing or []) + (incoming or []):
        if not isinstance(item, dict):
            continue
        enc_id = item.get("encounter_id")
        if not isinstance(enc_id, int):
            continue
        prev = by_id.get(enc_id)
        if prev is None:
            by_id[enc_id] = dict(item)
        else:
            prev["kill"] = bool(prev.get("kill")) or bool(item.get("kill"))
            if not prev.get("name") and item.get("name"):
                prev["name"] = item["name"]
            if prev.get("difficulty") is None and item.get("difficulty") is not None:
                prev["difficulty"] = item["difficulty"]
    return list(by_id.values())
