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


# --- REST --------------------------------------------------------------------


class ModelsResponse(BaseModel):
    models: list[str]
    default: str


class ConversationCreate(BaseModel):
    model: str
    title: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    seq: int
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
