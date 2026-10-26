"""Slim participant list for a report or fight (feature 030, sc-206).

``get_report_participants`` answers "who was in this run" with one compact row per real
player (name, realm, region, class, spec, role), so the agent can resolve "the dungeon" to
people and filter them ("except the shaman") before a profile action. It reuses the
``playerDetails`` field through ``report_tools._report_fields``, so the single WCL client,
its cache and raw-fetch persistence all apply; no new query and no new cache family.
"""

from __future__ import annotations

from typing import Any

from ..game.constants import normalize_class_name, role_for_spec
from ..game.roster import roster_snapshot
from .provenance import Provenance, with_envelope
from .report_tools import _fight_ids, _report_fields

_GROUPS = (("tanks", "tank"), ("healers", "healer"), ("dps", "dps"))
_ROLE_ORDER = {"tank": 0, "healer": 1, "dps": 2}
_FIELDS = "region { slug } playerDetails(fightIDs: $fightIDs)"


def participants_from_player_details(details: Any, region: str | None) -> list[dict[str, Any]]:
    """Rows from a ``playerDetails`` payload; pets and NPCs (no playable class) are dropped.

    A player seen in several entries (raid swaps) becomes one row, with the most-played
    spec; the role is that spec's role, else the group they were first seen in.
    """
    groups = ((details or {}).get("data") or {}).get("playerDetails") or {}
    players: dict[tuple[str, str | None], dict[str, Any]] = {}
    for group, group_role in _GROUPS:
        for entry in groups.get(group) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            class_name = normalize_class_name(str(entry.get("type") or ""))
            if class_name is None:
                continue
            realm = entry.get("server") or None
            player = players.setdefault(
                (entry["name"], realm),
                {"name": entry["name"], "realm": realm, "class": class_name,
                 "role": group_role, "specs": {}},
            )
            for spec in entry.get("specs") or []:
                if isinstance(spec, dict) and spec.get("spec"):
                    counts = player["specs"]
                    counts[spec["spec"]] = counts.get(spec["spec"], 0) + int(spec.get("count") or 1)
    roster = roster_snapshot()
    rows = []
    for player in players.values():
        specs = player.pop("specs")
        spec = max(specs, key=specs.get) if specs else None
        entry = roster.get(player["class"], spec) if spec else None
        rows.append({
            "name": player["name"],
            "realm": player["realm"],
            "region": region,
            "class": roster.class_display(player["class"]),
            "spec": entry.spec_display if entry else spec,
            "role": role_for_spec(spec) or player["role"],
        })
    rows.sort(key=lambda r: (_ROLE_ORDER[r["role"]], r["name"]))
    return rows


async def get_report_participants(report_code: str, fight_id: int = 0) -> dict[str, Any]:
    """List the players in a report or one fight: name, realm, region, class, spec, role.

    Use this to learn who took part in a run (e.g. before adding them to a profile). It
    is much smaller than get_report_player_details and has no pets or NPCs. For a
    Mythic+ run pass the keystone fight id, which gives exactly that key's players; with
    fight_id 0 you get everyone who appeared in any fight of the report. Apply filters
    such as "only the healers" or "except the shaman" to the returned rows yourself.

    Args:
        report_code (str): The report code.
        fight_id (int): Single fight id (0 = all fights).

    Returns:
        dict: {"status": "success", "participants": [...]} or an error.
    """
    try:
        report = await _report_fields(
            report_code, _FIELDS, ", $fightIDs: [Int]", {"fightIDs": _fight_ids(fight_id)}
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if report is None:
        return {"status": "error", "error_message": f"No data for report '{report_code}'."}
    region = ((report.get("region") or {}).get("slug") or None)
    rows = participants_from_player_details(report.get("playerDetails"), region)
    if not rows:
        return {"status": "error", "error_message": f"No players found in report '{report_code}'."}
    return with_envelope(
        {"status": "success", "report_code": report_code, "fight_id": fight_id or None,
         "region": region, "participants": rows},
        Provenance(report_code=report_code, fight_id=fight_id or None),
    )
