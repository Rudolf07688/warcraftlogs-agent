"""Coaching briefs for the WCL tools: an injected loader (features 009, 015).

``wcl_agent`` never imports the backend (dependency direction is backend → wcl_agent), so
the backend registers a loader at startup (``set_brief_loader``) that reads the PUBLISHED
coaching brief of one ``(class, spec, content_type)`` from the shared guide library —
never a draft (FR-016). Tools call ``get_brief``. The CLI registers nothing, and the tools
then coach from measured log data only (data-model §5, research R7).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuideCooldown:
    name: str
    spell_id: int | None
    cooldown_s: float
    charges: int = 1
    talent_modified: bool = False


@dataclass(frozen=True)
class BriefRecord:
    """One published coaching brief, ready for the agent."""

    class_name: str  # WCL PascalCase, e.g. "Mage"
    spec: str  # e.g. "Fire"
    content_type: str  # "raid" | "mplus"
    text: str  # the rendered brief (already within its budget, never truncated)
    cooldowns: tuple[GuideCooldown, ...]
    game_patch: str | None
    season: str | None
    generated_at: datetime | None
    freshness: str  # current | possibly_stale | unknown
    data_sufficient: bool


BriefLoader = Callable[[str, str, str], Awaitable[BriefRecord | None]]
BriefUsed = Callable[[BriefRecord], None]

_loader: BriefLoader | None = None
_on_used: BriefUsed | None = None


def set_brief_loader(loader: BriefLoader, on_used: BriefUsed | None = None) -> None:
    """Register the loader, and optionally a callback told when a tool hands a brief to the
    agent (the backend stamps the guide as in use)."""
    global _loader, _on_used
    _loader, _on_used = loader, on_used


def clear_brief_loader() -> None:
    """Tests (and shutdown) only."""
    global _loader, _on_used
    _loader, _on_used = None, None


async def get_brief(
    class_name: str, spec: str, content_type: str, *, mark_used: bool = False
) -> BriefRecord | None:
    """The published brief for exactly this content type, or None (never the other type).

    ``mark_used`` = the brief goes to the agent now (reported through ``on_used``).
    """
    if _loader is None or not class_name or not spec or content_type not in ("raid", "mplus"):
        return None
    try:
        record = await _loader(class_name.strip(), spec.strip(), content_type)
    except Exception as exc:  # noqa: BLE001 - coaching degrades to measured data only
        logger.warning("brief lookup failed for %s %s %s: %s", class_name, spec, content_type, exc)
        return None
    if record is not None and mark_used and _on_used is not None:
        try:
            _on_used(record)
        except Exception as exc:  # noqa: BLE001 - bookkeeping only
            logger.warning("brief use callback failed: %s", exc)
    return record
