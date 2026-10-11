"""``get_cooldown_usage`` — opportunity-based cooldown coaching (feature 009, US4).

Turns "you only cast Combustion twice" into "2 of ~4 opportunities": eligible time
is the fight minus the player's dead windows and the encounter's intermissions
(research R5, shared ``fight_time`` helpers — never WCL ``activeTime``), and the
cooldown durations come from the spec guide's machine-readable metadata via the
in-process registry (research R6/R7). With no guide cooldowns the tool returns
rates only, so the model compares rates and never says "missed" (FR-025).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from . import wcl_client
from .benchmark import _casts_table, reduce_casts_entry
from .fight_time import (
    PlayerResolutionError,
    eligible_seconds,
    fetch_dead_windows,
    intermission_windows,
    resolve_player,
    windows_seconds,
)
from .guide_meta import GuideCooldown, get_guide_meta
from .patch import current_patch, guide_freshness
from .provenance import Completeness, Provenance, with_envelope

EXCLUDED_WINDOWS_UNKNOWN = ["target immunity outside intermissions"]


# --- Pure helpers (unit-tested) -----------------------------------------------------


def opportunities(eligible_s: float, cooldown_s: float, charges: int = 1) -> int:
    """``1 + floor(eligible / cooldown) + (charges − 1)`` — the use available at pull
    plus one per full cooldown of eligible time (research R6). Always approximate."""
    if cooldown_s <= 0 or eligible_s < 0:
        return 0
    return 1 + math.floor(eligible_s / cooldown_s) + max(0, int(charges) - 1)


def match_uses(cooldowns: Sequence[GuideCooldown], abilities: list[dict[str, Any]]) -> list[int]:
    """Casts per guide cooldown: ``spell_id == guid`` first, else case-insensitive name; else 0."""
    by_guid = {a.get("guid"): int(a.get("total") or 0) for a in abilities if a.get("guid") is not None}
    by_name = {str(a.get("name", "")).casefold(): int(a.get("total") or 0) for a in abilities}
    uses: list[int] = []
    for cd in cooldowns:
        if cd.spell_id is not None and cd.spell_id in by_guid:
            uses.append(by_guid[cd.spell_id])
        else:
            uses.append(by_name.get(cd.name.casefold(), 0))
    return uses


def _split_icon(icon: str | None) -> tuple[str | None, str | None]:
    """``"Mage-Fire"`` → ``("Mage", "Fire")``."""
    if not icon or "-" not in icon:
        return None, None
    cls, spec = icon.split("-", 1)
    return cls or None, spec or None


# --- The tool ---------------------------------------------------------------------


def _fetch_context(report_code: str, fight_id: int) -> dict[str, Any] | None:
    query = """
    query CooldownCtx($code: String!, $fightIDs: [Int]) {
      reportData { report(code: $code) {
        masterData { actors(type: "Player") { id name server subType } }
        phases { encounterID phases { id name isIntermission } }
        fights(fightIDs: $fightIDs) {
          id startTime endTime kill encounterID difficulty friendlyPlayers
          phaseTransitions { id startTime }
        }
      } }
    }
    """.strip()
    data = wcl_client.get_client().query(query, {"code": report_code, "fightIDs": [fight_id]})
    return ((data.get("data") or {}).get("reportData") or {}).get("report")


def _intermission_ids(phases: list[dict[str, Any]] | None, encounter_id: int | None) -> set[int]:
    for block in phases or []:
        if not isinstance(block, dict) or block.get("encounterID") != encounter_id:
            continue
        return {
            int(p["id"])
            for p in (block.get("phases") or [])
            if isinstance(p, dict) and p.get("isIntermission") and p.get("id") is not None
        }
    return set()


def get_cooldown_usage(
    report_code: str,
    fight_id: int,
    player_name: str,
    source_id: int = 0,
) -> dict[str, Any]:
    """Count a player's major-cooldown uses against approximate opportunities in one fight.

    Use this BEFORE saying a cooldown was under-used or "missed". It computes the
    player's eligible time (fight length minus time dead and intermissions — not
    WCL activeTime) and, when the spec's guide provides cooldown durations
    (`guide.available`), "uses of ~opportunities" per major cooldown. Express
    results as "N of ~M opportunities" only when `guide.available` is true; the
    counts are always approximate (`approximate: true`) and carry
    `freshness_caveat` when the guide may be out of date. Otherwise compare the
    `rates` (casts per minute of eligible time) with the cohort and never say
    "missed". `time.excluded_windows_unknown` lists what could not be excluded.

    Args:
        report_code (str): The report code.
        fight_id (int): The fight id (> 0).
        player_name (str): The player's character name as it appears in the report.
        source_id (int): The player's source id, to disambiguate duplicate names.

    Returns:
        dict: {"status": "success", player: {name, source_id, class, spec},
            time: {fight_s, dead_s, intermission_s, eligible_s, excluded_windows_unknown},
            guide: {available, game_patch, freshness, generated_at},
            cooldowns: [{name, spell_id, cooldown_s, charges, talent_modified, uses,
                         opportunities, approximate, freshness_caveat}],
            rates: [{ability: {name, guid}, casts, casts_per_min}],
            provenance, completeness} or {"status": "error", ...} (with
            "candidates" when the name is ambiguous).
    """
    if not fight_id or fight_id < 1:
        return {"status": "error", "error_message": "fight_id must be a single fight id (> 0)."}
    try:
        report = _fetch_context(report_code, fight_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    if not report or not report.get("fights"):
        return {"status": "error", "error_message": f"No fight {fight_id} in report '{report_code}'."}
    fight = report["fights"][0]
    actors = ((report.get("masterData") or {}).get("actors")) or []
    try:
        resolved = resolve_player(actors, fight.get("friendlyPlayers"), player_name, source_id)
    except PlayerResolutionError as exc:
        return exc.result

    fight_start, fight_end = float(fight.get("startTime") or 0), float(fight.get("endTime") or 0)
    fight_s = round(max(0.0, fight_end - fight_start) / 1000, 1)
    try:
        entry = reduce_casts_entry(_casts_table(report_code, fight_id), source_id=resolved.source_id)
        dead = fetch_dead_windows(report_code, fight_id, resolved.source_id, fight_end)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"WCL request failed: {exc}"}
    inter = intermission_windows(
        fight_start,
        fight_end,
        fight.get("phaseTransitions"),
        _intermission_ids(report.get("phases"), fight.get("encounterID")),
    )
    eligible_s = round(eligible_seconds(fight_start, fight_end, dead, inter), 1)
    eligible_min = (eligible_s if eligible_s > 0 else fight_s) / 60 or 1.0

    class_name, spec = _split_icon(entry.class_spec if entry else None)
    class_name = class_name or resolved.class_name
    abilities = entry.abilities if entry else []

    meta = get_guide_meta(class_name, spec) if class_name and spec else None
    freshness = guide_freshness(meta.game_patch, current_patch()) if meta is not None else None
    guide = {
        "available": bool(meta is not None and meta.cooldowns),
        "game_patch": meta.game_patch if meta is not None else None,
        "freshness": freshness,
        "generated_at": meta.generated_at.isoformat() if meta is not None and meta.generated_at else None,
    }
    cooldowns: list[dict[str, Any]] = []
    if guide["available"]:
        uses = match_uses(meta.cooldowns, abilities)
        for cd, used in zip(meta.cooldowns, uses, strict=True):
            cooldowns.append(
                {
                    "name": cd.name,
                    "spell_id": cd.spell_id,
                    "cooldown_s": cd.cooldown_s,
                    "charges": cd.charges,
                    "talent_modified": cd.talent_modified,
                    "uses": used,
                    "opportunities": opportunities(eligible_s, cd.cooldown_s, cd.charges),
                    "approximate": True,
                    "freshness_caveat": freshness != "current",
                }
            )

    result = {
        "status": "success",
        "player": {
            "name": resolved.name,
            "source_id": resolved.source_id,
            "class": class_name,
            "spec": spec,
        },
        "time": {
            "fight_s": fight_s,
            "dead_s": windows_seconds([(max(s, fight_start), min(e, fight_end)) for s, e in dead]),
            "intermission_s": windows_seconds(inter),
            "eligible_s": eligible_s,
            "excluded_windows_unknown": list(EXCLUDED_WINDOWS_UNKNOWN),
        },
        "guide": guide,
        "cooldowns": cooldowns,
        "rates": [
            {
                "ability": {"name": a["name"], "guid": a["guid"]},
                "casts": a["total"],
                "casts_per_min": round(a["total"] / eligible_min, 2),
            }
            for a in abilities
        ],
    }
    return with_envelope(
        result,
        Provenance(
            report_code=report_code,
            fight_id=fight_id,
            encounter_id=fight.get("encounterID"),
            difficulty=fight.get("difficulty"),
            source_id=resolved.source_id,
        ),
        Completeness(),
    )
