"""Current game patch and guide freshness (feature 009, US5 — research R8).

``current_patch()`` reads the default partition name of the newest non-frozen raid
zone that offers Heroic difficulty (e.g. ``"12.1"``) from the shared zone list.
Mythic+ zones have no Heroic difficulty and season-named partitions, so they are
excluded naturally. ``guide_freshness`` compares a guide's stated patch with it.

Feature 015 adds the Mythic+ zone (research R9): the newest non-frozen zone offering the
Mythic+ difficulty (id 10), whose name is the season ("Mythic+ Season 2").
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from .menu import _default_partition, load_world_zones

logger = logging.getLogger(__name__)

HEROIC_DIFFICULTY_ID = 4
MYTHIC_PLUS_DIFFICULTY_ID = 10
_PATCH_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")

Freshness = Literal["current", "possibly_stale", "unknown"]


def _offers(zone: dict[str, Any], difficulty_id: int) -> bool:
    return any(
        isinstance(d, dict) and d.get("id") == difficulty_id
        for d in (zone.get("difficulties") or [])
    )


def _offers_heroic(zone: dict[str, Any]) -> bool:
    return _offers(zone, HEROIC_DIFFICULTY_ID)


def _newest_live_zone(zones: list[dict[str, Any]], difficulty_id: int) -> dict[str, Any] | None:
    live = [
        z for z in zones if isinstance(z, dict) and not z.get("frozen") and _offers(z, difficulty_id)
    ]
    return max(live, key=lambda z: int(z.get("id") or 0)) if live else None


def raid_zone_from(zones: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pure helper: the newest non-frozen zone offering Heroic (the current raid tier)."""
    return _newest_live_zone(zones, HEROIC_DIFFICULTY_ID)


def mplus_zone_from(zones: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pure helper: the newest non-frozen zone offering Mythic+ (difficulty 10)."""
    return _newest_live_zone(zones, MYTHIC_PLUS_DIFFICULTY_ID)


def current_patch_from_zones(zones: list[dict[str, Any]]) -> str | None:
    """Pure helper: default partition name of the newest non-frozen Heroic zone."""
    zone = raid_zone_from(zones)
    if zone is None:
        return None
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


async def current_raid_tier() -> str | None:
    """Name of the current raid zone (e.g. "The Venomous Abyss"), or None when unknown."""
    try:
        zone = raid_zone_from(await load_world_zones())
    except Exception as exc:  # noqa: BLE001 - the tier is optional context
        logger.warning("current_raid_tier lookup failed: %s", exc)
        return None
    return str(zone.get("name") or "").strip() or None if zone else None


async def mplus_zone() -> dict[str, Any] | None:
    """The current Mythic+ zone (id, name, encounters = dungeons), or None when unknown."""
    try:
        return mplus_zone_from(await load_world_zones())
    except Exception as exc:  # noqa: BLE001 - callers treat None as "no Mythic+ season"
        logger.warning("mplus_zone lookup failed: %s", exc)
        return None


async def current_mplus_season() -> str | None:
    """Name of the current Mythic+ zone (e.g. "Mythic+ Season 2"), or None when unknown."""
    zone = await mplus_zone()
    return str(zone.get("name") or "").strip() or None if zone else None


async def is_mplus_zone_id(zone_id: int | None) -> bool:
    """Whether ``zone_id`` is a Mythic+ zone (any season, frozen ones included)."""
    if not zone_id:
        return False
    try:
        zones = await load_world_zones()
    except Exception as exc:  # noqa: BLE001 - unknown ⇒ not Mythic+
        logger.warning("is_mplus_zone_id lookup failed: %s", exc)
        return False
    return any(
        isinstance(z, dict) and z.get("id") == zone_id and _offers(z, MYTHIC_PLUS_DIFFICULTY_ID)
        for z in zones
    )


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
