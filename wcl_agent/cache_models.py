"""Typed values stored in the shared WCL cache, one model per key family (feature 014).

Values are the app's own normalised data, never raw GraphQL responses. A shape change
here means bumping the ``v1`` in the key builders (``cache.keys``) so old entries are
ignored rather than misread.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class CharacterRef(BaseModel):
    """``char_id``: a character's WCL identity, resolved from name/realm/region."""

    id: int
    name: str
    realm: str
    region: str
    class_id: int | None = None


class CharacterRankings(BaseModel):
    """``char_overview``: one zone- or encounter-rankings JSON scalar, unchanged."""

    name: str
    scope: Literal["zone", "encounter"]
    rankings: Any = None


class RecentReport(BaseModel):
    code: str
    title: str
    start_time_ms: int
    end_time_ms: int
    zone_id: int | None = None
    zone_name: str | None = None
    guild_name: str | None = None


class CharacterReports(BaseModel):
    """``char_reports``: a character's most recent reports."""

    reports: list[RecentReport]


class PlayerRef(BaseModel):
    name: str
    class_name: str | None = None


class FightSummary(BaseModel):
    id: int
    name: str
    encounter_id: int | None = None
    difficulty: int | None = None
    kill: bool | None = None
    average_item_level: float | None = None
    size: int | None = None
    player_ids: list[int] = []


class ReportSummary(BaseModel):
    """``report_summary``: fights, bosses, kills/wipes and roster of one report."""

    code: str
    title: str | None = None
    start_time_ms: int
    end_time_ms: int
    zone_id: int | None = None
    zone_name: str | None = None
    guild_name: str | None = None
    players: dict[int, PlayerRef] = {}
    fights: list[FightSummary] = []


class PlayerTable(BaseModel):
    """``report_player``: one source's ``table`` JSON scalar from a report."""

    data: Any = None


class OAuthToken(BaseModel):
    """``oauth_token``: the WCL client-credentials bearer token."""

    access_token: str
    expires_at: float  # epoch seconds


class WorldZones(BaseModel):
    """``world_zones``: ``worldData.zones`` as the existing pure helpers consume it."""

    zones: list[dict[str, Any]]
