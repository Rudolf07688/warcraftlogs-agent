"""Pydantic contracts for the WebSocket frames and REST bodies."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class RaidListResponse(BaseModel):
    raids: list[RaidOut]


class InvestigateRequest(BaseModel):
    model: str | None = None


class InvestigateResponse(BaseModel):
    conversation_id: uuid.UUID
    model: str
    kickoff_prompt: str
