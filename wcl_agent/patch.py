"""Current game patch and guide freshness (feature 009, US5 — research R8).

``current_patch()`` reads the default partition name of the newest non-frozen raid
zone that offers Heroic difficulty (e.g. ``"12.1"``) from the shared zone list.
Mythic+ zones have no Heroic difficulty and season-named partitions, so they are
excluded naturally. ``guide_freshness`` compares a guide's stated patch with it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from .menu import _default_partition, load_world_zones

logger = logging.getLogger(__name__)

HEROIC_DIFFICULTY_ID = 4
_PATCH_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")

Freshness = Literal["current", "possibly_stale", "unknown"]


def _offers_heroic(zone: dict[str, Any]) -> bool:
    return any(
        isinstance(d, dict) and d.get("id") == HEROIC_DIFFICULTY_ID
        for d in (zone.get("difficulties") or [])
    )


def current_patch_from_zones(zones: list[dict[str, Any]]) -> str | None:
    """Pure helper: default partition name of the newest non-frozen Heroic zone."""
    raids = [z for z in zones if isinstance(z, dict) and not z.get("frozen") and _offers_heroic(z)]
    if not raids:
        return None
    zone = max(raids, key=lambda z: int(z.get("id") or 0))
    pid = _default_partition(zone)
    for part in zone.get("partitions") or []:
        if part.get("id") == pid:
            name = str(part.get("name") or "").strip()
            return name or None
    return None


async def current_patch() -> str | None:
    """Name of the current raid partition (the live patch), or None when unknown."""
    try:
        return current_patch_from_zones(await load_world_zones())
    except Exception as exc:  # noqa: BLE001 - freshness degrades to "unknown"
        logger.warning("current_patch lookup failed: %s", exc)
        return None


def raid_zone_ids_from(zones: list[dict[str, Any]]) -> set[int]:
    """Pure helper: ids of zones that offer raid difficulties (Heroic), frozen ones included.

    Mythic+ and other non-raid zones have no Heroic difficulty, so they are left out.
    """
    return {int(z["id"]) for z in zones if isinstance(z, dict) and z.get("id") and _offers_heroic(z)}


async def raid_zone_ids() -> set[int]:
    """Ids of every raid zone, from the cached zone list (feature 013)."""
    return raid_zone_ids_from(await load_world_zones())


def parse_patch(value: str | None) -> tuple[int, int] | None:
    """``"12.1"`` / ``"12.1.5"`` → ``(12, 1)``; anything else → None."""
    if not value:
        return None
    match = _PATCH_RE.match(value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def guide_freshness(guide_patch: str | None, current: str | None) -> Freshness:
    """``current`` when the guide's major.minor is not older than the live patch."""
    guide, live = parse_patch(guide_patch), parse_patch(current)
    if guide is None or live is None:
        return "unknown"
    return "possibly_stale" if guide < live else "current"
