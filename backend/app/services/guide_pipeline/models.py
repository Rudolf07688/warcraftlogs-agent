"""Pydantic models exchanged by the pipeline stages (data-model §4).

Pydantic (not dataclasses) because they cross the model boundary — structured LLM output
is externally-sourced data that must be validated (Constitution IV) — and are persisted as
JSON on the guide row.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ContentType = Literal["raid", "mplus"]
Confidence = Literal["high", "medium", "low"]
EvidenceType = Literal["observed", "benchmarked", "guidance"]

ClaimSection = Literal[
    "overview",
    "priority",
    "cooldowns",
    "uptimes",
    "talents",
    "stats",
    "mistakes",
    "benchmarks",
    "content_notes",
]

# Sections whose claims are coaching checks and so must say what to look for in a log (FR-009).
LOG_CHECK_SECTIONS: frozenset[str] = frozenset({"mistakes", "uptimes", "cooldowns", "benchmarks"})

# The fixed order sections are rendered in (brief and readable guide alike).
SECTION_ORDER: tuple[str, ...] = (
    "overview",
    "priority",
    "cooldowns",
    "uptimes",
    "talents",
    "stats",
    "mistakes",
    "benchmarks",
    "content_notes",
)


# --- 4.1 Briefing --------------------------------------------------------------


class GenerationBriefing(BaseModel):
    """Everything a run must know about "now" before writing anything (FR-002)."""

    now_utc: datetime
    content_type: ContentType
    class_name: str
    class_display: str
    spec: str
    role: str
    class_specs: list[str]
    live_patch: str
    live_build: str | None = None
    latest_hotfix_at: datetime | None = None
    hotfix_touches_spec: bool = False
    raid_tier: str | None = None
    mplus_season: str | None = None
    product: Literal["retail"] = "retail"
    environment: Literal["live"] = "live"
    region: str = "US"


# --- 4.2 Data sheet ------------------------------------------------------------


class SampleScope(BaseModel):
    zone_id: int | None = None
    zone_name: str | None = None
    partition: int | None = None
    difficulty: int | None = None  # raid difficulty id; 10 for Mythic+
    key_level_floor: int | None = None  # mplus: lowest key level in the cohort
    encounters: list[str] = []
    metric: str = "dps"
    sample_size: int = 0
    collected_at: datetime | None = None


class ObservedAbility(BaseModel):
    ability_id: int
    name: str
    casts_per_min_median: float | None = None
    casts_per_min_p25: float | None = None
    casts_per_min_p75: float | None = None
    min_gap_s: float | None = None
    players_using: int = 0


class ObservedUptime(BaseModel):
    ability_id: int
    name: str
    kind: Literal["buff", "debuff"]
    uptime_pct_median: float
    players: int = 0


class TalentRef(BaseModel):
    talent_id: int
    name: str | None = None


class ObservedBuild(BaseModel):
    talent_ids_hash: str
    share_pct: float
    players: int
    notable_talents: list[TalentRef] = []


class TalentPick(BaseModel):
    talent_id: int
    name: str | None = None
    pick_pct: float


class ObservedStat(BaseModel):
    stat: str
    median_rating: float
    p25: float | None = None
    p75: float | None = None


class DataSheet(BaseModel):
    """Measured Warcraft Logs evidence for one spec and content type (FR-032..FR-035).

    Fact ids are ``ds:<kind>:<key>`` (see ``fact_ids``)."""

    class_name: str
    spec: str
    content_type: ContentType
    scope: SampleScope
    sufficient: bool = False
    abilities: list[ObservedAbility] = []
    uptimes: list[ObservedUptime] = []
    talent_builds: list[ObservedBuild] = []
    talent_pick_rates: list[TalentPick] = []
    stat_spread: list[ObservedStat] = []
    item_level_median: float | None = None

    def fact_ids(self) -> set[str]:
        """Every ``ds:*`` id a claim may cite."""
        ids = {"ds:scope"}
        ids |= {f"ds:ability:{a.ability_id}" for a in self.abilities}
        ids |= {f"ds:uptime:{u.ability_id}" for u in self.uptimes}
        ids |= {f"ds:build:{b.talent_ids_hash}" for b in self.talent_builds}
        ids |= {f"ds:talent:{t.talent_id}" for t in self.talent_pick_rates}
        ids |= {f"ds:stat:{s.stat}" for s in self.stat_spread}
        if self.item_level_median is not None:
            ids.add("ds:ilvl")
        return ids

    def ability_ids(self) -> set[int]:
        return {a.ability_id for a in self.abilities} | {u.ability_id for u in self.uptimes}


# --- 4.3 Research evidence -----------------------------------------------------


EvidenceTopic = Literal["rotation", "cooldowns", "talents", "stats", "mechanics", "affixes", "other"]


class EvidenceItem(BaseModel):
    """One paraphrased fact from a source, tagged with what it applies to (FR-039..FR-044)."""

    id: str = ""  # "src:<n>", assigned by code
    statement: str = Field(max_length=300)
    topic: EvidenceTopic = "other"
    source_url: str
    source_title: str | None = None
    source_date: date | None = None
    tier: int = Field(default=3, ge=1, le=4)
    product: str = "retail"  # retail | classic | unknown
    environment: str = "live"  # live | ptr | beta | unknown
    patch: str | None = None
    content_type: Literal["raid", "mplus", "both"] = "both"
    superseded: bool = False
    # What the statement is about and the value it gives (e.g. "Combustion cooldown" /
    # "120 s"), so code can spot equal-tier sources that disagree (FR-042).
    subject: str | None = Field(default=None, max_length=80)
    value: str | None = Field(default=None, max_length=80)
    possibly_stale: bool = False  # dated before the latest hotfix that did not touch this spec
    snippet_only: bool = False  # known only from a search snippet (page not fetchable): low confidence
    flagged_instruction: bool = False  # the source text tried to instruct the model

    @field_validator("statement", mode="before")
    @classmethod
    def _trim_statement(cls, v):
        return str(v or "").strip()[:300]


class DroppedEvidence(BaseModel):
    url: str
    reason: str
    title: str | None = None


class EvidenceConflict(BaseModel):
    topic: str
    item_ids: list[str]


class FactSheet(BaseModel):
    """Citable research evidence after the hard filters, plus what was dropped and why."""

    items: list[EvidenceItem] = []
    dropped: list[DroppedEvidence] = []
    conflicts: list[EvidenceConflict] = []
    discovery: list[EvidenceItem] = []  # tier-4 items: never citable

    def citable_ids(self) -> set[str]:
        conflicted = {i for c in self.conflicts for i in c.item_ids}
        return {i.id for i in self.items if i.id and i.id not in conflicted and not i.superseded}

    def by_id(self) -> dict[str, EvidenceItem]:
        return {i.id: i for i in self.items}


class EvidenceSnapshot(BaseModel):
    """The evidence a published version was written from (audit + accuracy check)."""

    data_sheet: DataSheet | None = None
    fact_sheet: FactSheet = FactSheet()


# --- 4.5 Claims ----------------------------------------------------------------


class LogCheck(BaseModel):
    """What the coach looks for in a log to judge this claim (FR-009)."""

    signal: Literal["casts", "uptime", "cooldown_usage", "deaths", "damage_taken", "other"]
    ability_id: int | None = None
    expectation: str = Field(max_length=160)

    @field_validator("expectation", mode="before")
    @classmethod
    def _trim(cls, v):
        return str(v or "").strip()[:160]


class GuideClaim(BaseModel):
    """One statement of the guide, citing the evidence it rests on (FR-036, FR-045..FR-047)."""

    id: str = ""  # "c<n>", assigned by code
    section: ClaimSection
    text: str = Field(min_length=1, max_length=300)
    evidence_type: EvidenceType = "guidance"
    evidence_refs: list[str] = Field(min_length=1)
    log_check: LogCheck | None = None
    confidence: Confidence = "medium"
    verdict: Literal["confirmed", "contradicted", "unconfirmed"] | None = None
    # Cooldown claims only: the structured numbers the brief and checks use.
    ability_name: str | None = Field(default=None, max_length=80)
    ability_id: int | None = None
    cooldown_s: float | None = Field(default=None, ge=1, le=900)
    charges: int | None = Field(default=None, ge=1, le=5)

    @field_validator("text", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return str(v or "").strip()[:300]

    @model_validator(mode="after")
    def _log_check_required(self) -> "GuideClaim":
        if self.section in LOG_CHECK_SECTIONS and self.log_check is None:
            raise ValueError(f"a {self.section} claim needs a log_check")
        return self


class AuthorResult(BaseModel):
    claims: list[GuideClaim] = []
    unconfirmed: list[str] = []  # areas left out because nothing supported them (FR-005)


# --- 4.6 Coaching brief --------------------------------------------------------


class BriefItem(BaseModel):
    text: str
    evidence_type: EvidenceType
    confidence: Confidence
    log_check: LogCheck | None = None
    claim_id: str


class BriefCooldown(BaseModel):
    name: str
    ability_id: int | None = None  # only from the data sheet (FR-034)
    cooldown_s: float | None = None
    charges: int = 1
    usage: str
    log_check: LogCheck | None = None
    evidence_type: EvidenceType
    confidence: Confidence
    claim_id: str


class CoachingBrief(BaseModel):
    """The agent-facing guide, built by code from confirmed claims (FR-008..FR-017)."""

    class_name: str
    spec: str
    content_type: ContentType
    role: str
    patch: str
    season: str | None = None
    generated_at: datetime
    priority: list[BriefItem] = []
    cooldowns: list[BriefCooldown] = []
    uptimes: list[BriefItem] = []
    talents: list[BriefItem] = []
    stats: list[BriefItem] = []
    mistakes: list[BriefItem] = []
    benchmarks: list[BriefItem] = []
    content_notes: list[BriefItem] = []
    unconfirmed: list[str] = []
    data_sufficient: bool = False
    data_scope: str | None = None  # one line naming the measured sample


# --- 4.7 Review and checks -----------------------------------------------------


class ReviewIssue(BaseModel):
    claim_id: str | None = None
    kind: Literal["contradicted", "unconfirmed", "missing_log_check", "other"]
    detail: str = Field(max_length=200)
    evidence_refs: list[str] = []

    @field_validator("detail", mode="before")
    @classmethod
    def _trim(cls, v):
        return str(v or "").strip()[:200]


class CheckFailure(BaseModel):
    check: str
    item: str = ""
    detail: str = ""


class RunOutcome(BaseModel):
    outcome: Literal["published", "held", "failed"]
    reason: str | None = None
    rounds: int = 0
