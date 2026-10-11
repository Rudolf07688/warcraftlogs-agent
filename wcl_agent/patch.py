"""Current game patch and guide freshness (feature 009, US5 — research R8).

``current_patch()`` reads the default partition name of the newest non-frozen raid
zone that offers Heroic difficulty (e.g. ``"12.1"``) through the cached WCL client.
Mythic+ zones have no Heroic difficulty and season-named partitions, so they are
excluded naturally. ``guide_freshness`` compares a guide's stated patch with it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from . import wcl_client
from .menu import _default_partition
from .queries import MENU_DISCOVERY

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


def current_patch() -> str | None:
    """Name of the current raid partition (the live patch), or None when unknown."""
    try:
        data = wcl_client.get_client().query(MENU_DISCOVERY)
        zones = ((data.get("data") or {}).get("worldData") or {}).get("zones") or []
        return current_patch_from_zones(zones)
    except Exception as exc:  # noqa: BLE001 - freshness degrades to "unknown"
        logger.warning("current_patch lookup failed: %s", exc)
        return None


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
