"""Value objects passed between the recent-raids service and the repository (feature 013).

Plain dataclasses in their own module so both sides import them without a cycle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ListedReport:
    """One report from the ``recentReports`` list step, merged across own characters."""

    code: str
    title: str
    zone_id: int | None
    zone_name: str | None
    guild_name: str | None
    started_at: datetime
    ended_at: datetime
    character_ids: frozenset[uuid.UUID]
    # The zone offers raid difficulties, known from the zone id alone, so a raid can be
    # listed before its details arrive.
    is_raid: bool = False


@dataclass(frozen=True)
class ReportDetails:
    """What the detail step learns about one report."""

    ended_at: datetime
    difficulty: int | None
    bosses_pulled: int
    bosses_killed: int
    is_raid: bool


@dataclass(frozen=True)
class MplusRun:
    """One completed Mythic+ keystone fight inside a report (feature 022)."""

    report_code: str
    fight_id: int
    dungeon: str
    key_level: int
    started_at: datetime
    timed: bool
    character_ids: frozenset[uuid.UUID]
