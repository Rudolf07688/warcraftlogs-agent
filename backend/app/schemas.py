"""Pydantic contracts for the WebSocket frames and REST bodies."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- WebSocket: client -> server ---------------------------------------------


class ChatTurn(BaseModel):
    conversation_id: uuid.UUID | None = None
    model: str
    content: str = Field(min_length=1)


# --- WebSocket: server -> client frames --------------------------------------


class MetaFrame(BaseModel):
    type: Literal["meta"] = "meta"
    conversation_id: uuid.UUID
    seq: int


class ToolStartFrame(BaseModel):
    type: Literal["tool_start"] = "tool_start"
    name: str


class ToolEndFrame(BaseModel):
    type: Literal["tool_end"] = "tool_end"
    name: str
    ok: bool = True
    # US6: optional telemetry for resolved spell chips. Additive — older clients ignore them.
    summary: str | None = None  # short human-readable result summary (≤140 chars)
    ms: int | None = None  # elapsed duration of the tool call, in milliseconds


class ToolProgressFrame(BaseModel):
    """US6 (optional): upgrade a cast bar from indeterminate to determinate.

    Only emitted by tools that can report progress; clients that ignore it still work.
    """

    type: Literal["tool_progress"] = "tool_progress"
    id: str  # correlates to the tool call
    done: int
    total: int
    note: str | None = None


class TokenFrame(BaseModel):
    type: Literal["token"] = "token"
    text: str


class DoneFrame(BaseModel):
    type: Literal["done"] = "done"
    message_id: uuid.UUID


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class RaidTrackedFrame(BaseModel):
    """Emitted after a raid is upserted so the UI can refresh its Raids list."""

    type: Literal["raid_tracked"] = "raid_tracked"
    report_code: str
    label: str


class GroundingSource(BaseModel):
    title: str | None = None
    uri: str | None = None


class GroundingFrame(BaseModel):
    """Emitted once per turn when the model used native web grounding (US3/FR-011)."""

    type: Literal["grounding"] = "grounding"
    used: bool = True
    sources: list[GroundingSource] = []


class SuggestionsFrame(BaseModel):
    """Up to 3 predicted follow-up questions, emitted just before `done` (US1).

    Omitted entirely when there are no useful suggestions.
    """

    type: Literal["suggestions"] = "suggestions"
    suggestions: list[str] = Field(default_factory=list, max_length=3)


class EncounterOut(BaseModel):
    """A distinct boss encounter from a report's fight list (US2 display + US4 picker)."""

    encounter_id: int
    name: str
    difficulty: int | None = None
    kill: bool | None = None


class EncountersFrame(BaseModel):
    """Emitted after a successful `get_report_fights` when the report has distinct bosses (US4).

    `encounters` is deduped by `encounter_id`; omitted entirely when empty.
    """

    type: Literal["encounters"] = "encounters"
    report_code: str
    encounters: list[EncounterOut] = []


# --- REST --------------------------------------------------------------------


class ModelsResponse(BaseModel):
    models: list[str]
    default: str
    degraded: bool = False


class ConversationCreate(BaseModel):
    model: str
    title: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    seq: int
    status: str = "complete"
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    model: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []
    # US2/FR-011: persisted charts, so reopening a conversation re-renders them.
    artifacts: list["ArtifactOut"] = []


class ConversationListResponse(BaseModel):
    conversations: list[ConversationOut]


# --- Tracked raids (US1) -----------------------------------------------------


class RaidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    report_code: str
    label: str
    zone: str | None = None
    guild: str | None = None
    report_started_at: datetime | None = None
    last_asked_at: datetime
    first_seen_at: datetime
    # US2: distinct boss(es) for this report, for the sidebar summary. Defaults empty.
    encounters: list[EncounterOut] = []

    @field_validator("encounters", mode="before")
    @classmethod
    def _none_encounters_to_empty(cls, v):
        # The DB column is nullable; rows predating the migration read back as None.
        return v or []


class RaidListResponse(BaseModel):
    raids: list[RaidOut]


class InvestigateRequest(BaseModel):
    model: str | None = None


class InvestigateResponse(BaseModel):
    conversation_id: uuid.UUID
    model: str
    kickoff_prompt: str


class GreetingResponse(BaseModel):
    """Warm Barnaby greeting for a new chat (US5). Empty string on generation failure."""

    greeting: str = ""


# --- Profile (feature 005 / US1) ---------------------------------------------


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    server: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=8)


class CharacterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    name: str
    server: str
    region: str
    class_name: str | None = None
    active_spec: str | None = None
    guide_status: str = "none"
    guide_updated_at: datetime | None = None


class GuildIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    server: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=8)


class GuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    server: str
    region: str
    summary_status: str = "none"


class ProfileOut(BaseModel):
    # Field name intentionally "self" (the user's own character); not a method arg here.
    self_character: CharacterOut | None = Field(default=None, serialization_alias="self")
    friends: list[CharacterOut] = []
    guild: GuildOut | None = None

    model_config = ConfigDict(populate_by_name=True)


# --- Charts & artifacts (feature 005 / US2) ----------------------------------

CHART_KINDS = {"line", "bar", "scatter", "area"}


class ChartSeries(BaseModel):
    name: str
    y: list[float] = Field(min_length=1)
    x: list[float | int | str] | None = None

    @field_validator("x")
    @classmethod
    def _x_matches_y(cls, v, info):
        y = info.data.get("y")
        if v is not None and y is not None and len(v) != len(y):
            raise ValueError("series 'x' length must match 'y' length")
        return v


class ChartSpec(BaseModel):
    """Single source of truth for both the Plotly (UI) and matplotlib (PDF) renderers."""

    kind: str
    title: str
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(min_length=1)
    source_url: str = ""

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v):
        if v not in CHART_KINDS:
            raise ValueError(f"kind must be one of {sorted(CHART_KINDS)}")
        return v


class ArtifactOut(BaseModel):
    id: uuid.UUID
    message_seq: int | None = None
    kind: str
    title: str
    figure: dict  # {data, layout} — rebuilt from the stored ChartSpec on read


class ArtifactFrame(BaseModel):
    type: Literal["artifact"] = "artifact"
    artifact_id: uuid.UUID
    kind: str
    title: str
    figure: dict  # Plotly figure JSON: {"data": [...], "layout": {...}}
