"""Typed values stored in the shared WCL cache, one model per key family (feature 014).

Values are the app's own normalised data, never raw GraphQL responses. A shape change
here means bumping the ``v1`` in the key builders (``cache.keys``) so old entries are
ignored rather than misread.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, model_validator


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


class GameSpec(BaseModel):
    id: int | None = None
    name: str  # display name, e.g. "Beast Mastery"
    slug: str  # filter value, e.g. "BeastMastery"


class GameClass(BaseModel):
    id: int | None = None
    name: str  # display name, e.g. "Demon Hunter"
    slug: str  # filter value, e.g. "DemonHunter"
    specs: list[GameSpec] = []


class GameClasses(BaseModel):
    """Warcraft Logs ``gameData.classes`` — the live class/spec roster (feature 015)."""

    classes: list[GameClass]


class DataSheetCache(BaseModel):
    """A guide data sheet, stored as JSON so ``wcl_agent`` needs no backend model (feature 015)."""

    data: dict[str, Any]


class ResearchCache(BaseModel):
    """A filtered guide fact sheet, stored as JSON (feature 015)."""

    data: dict[str, Any]


class TalentNames(BaseModel):
    """Optional talent-entry id → name map (feature 015, research R5 §6)."""

    names: dict[int, str]


class LiveVersion(BaseModel):
    """The live retail build from Blizzard's version endpoint (feature 015, research R1)."""

    region: str
    version: str  # VersionsName, e.g. "12.1.5.70448"
    build_id: int | None = None
    seqn: int | None = None
    fetched_at: datetime

    @property
    def patch(self) -> str:
        """``major.minor.patch`` — the part of the version guides target."""
        return ".".join(self.version.split(".")[:3])


class HotfixEntry(BaseModel):
    date: str | None = None  # the article's date heading, as written
    class_name: str  # WCL class filter value, e.g. "DemonHunter"
    specs: list[str] = []  # WCL spec values; empty = the whole class


class HotfixFeed(BaseModel):
    """The newest Blizzard "Hotfixes:" article, reduced to which classes/specs it touches (R2)."""

    article_url: str | None = None
    latest_at: datetime | None = None
    entries: list[HotfixEntry] = []
    touches_all_classes: bool = False  # a change listed for every class at once



class ClassResult(BaseModel):
    """One model class's discovery outcome (feature 016), replayed in the boot log on a hit."""

    publisher: str
    cls: str
    models: list[str] = []  # kept ids, newest first
    reason: str | None = None  # no_quota | not_enabled | failed | no_candidates
    failed: list[str] = []  # ids skipped for an error that may not last (timeout, 5xx)


class ModelCatalog(BaseModel):
    """``model_catalog``: the startup model discovery result (feature 016, data-model.md)."""

    models: list[str]  # served order; never empty
    default: str
    degraded: bool
    source: Literal["catalog", "static", "fallback", "degraded"]
    classes: list[ClassResult] = []  # empty unless source == "catalog"
    listed: list[str] = []  # every callable id the catalog listed (fixed-model warning)
    fetched_at: datetime

    @model_validator(mode="after")
    def _check(self) -> ModelCatalog:
        if not self.models:
            raise ValueError("models must not be empty")
        if self.default not in self.models:
            raise ValueError(f"default {self.default!r} is not among the models")
        if self.degraded != (self.source == "degraded"):
            raise ValueError("degraded must be true exactly when source is 'degraded'")
        return self
