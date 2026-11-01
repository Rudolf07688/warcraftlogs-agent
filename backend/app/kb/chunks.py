"""What a chunker produces: chunk drafts with their filter values, plus text helpers (043).

A draft is everything a ``kb_chunks`` / ``kb_chat_chunks`` row holds except the vector state;
``kb/store.py`` writes it. Texts are bounded so a chunk embeds whole (the model truncates
anything longer) and stays compact in 044's search results.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MAX_TEXT = 2_000  # WCL and guide chunks
MAX_CHAT_TEXT = 6_000  # one exchange
MAX_LABEL = 200


@dataclass(frozen=True)
class PlayerRef:
    """A player named by a chunk; ``key`` is the resolver's ``name_key``."""

    name: str
    key: str
    class_name: str | None = None
    spec: str | None = None
    id: int | None = None  # the report's actor id (WCL chunks)

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "key": self.key}
        if self.class_name:
            out["class"] = self.class_name
        if self.spec:
            out["spec"] = self.spec
        if self.id is not None:
            out["id"] = self.id
        return out


@dataclass(frozen=True)
class ChunkDraft:
    """One ``kb_chunks`` row before it is written (the source id is the writer's)."""

    chunk_key: str
    label: str
    text: str
    report_code: str | None = None
    zone_id: int | None = None
    encounter_id: int | None = None
    difficulty: int | None = None
    fight_id: int | None = None
    kill: bool | None = None
    start_time: datetime | None = None
    players: tuple[PlayerRef, ...] = ()
    region: str | None = None
    realm: str | None = None
    guild: str | None = None
    class_name: str | None = None
    spec: str | None = None
    role: str | None = None
    content_type: str | None = None
    patch: str | None = None
    section: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return content_hash(self.text)

    def columns(self) -> dict[str, Any]:
        """The row's columns (without source id, ids and vector state)."""
        return {
            "chunk_key": self.chunk_key,
            "label": self.label[:MAX_LABEL],
            "text": self.text,
            "content_hash": self.content_hash,
            "report_code": self.report_code,
            "zone_id": self.zone_id,
            "encounter_id": self.encounter_id,
            "difficulty": self.difficulty,
            "fight_id": self.fight_id,
            "kill": self.kill,
            "start_time": self.start_time,
            "players": [p.as_json() for p in self.players] or None,
            "region": self.region,
            "realm": self.realm,
            "guild": self.guild,
            "class_name": self.class_name,
            "spec": self.spec,
            "role": self.role,
            "content_type": self.content_type,
            "patch": self.patch,
            "section": self.section[:MAX_LABEL] if self.section else None,
            "extra": self.extra or None,
        }


@dataclass(frozen=True)
class ChatChunkDraft:
    """One ``kb_chat_chunks`` row before it is written."""

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    message_seq: int
    created_at: datetime
    label: str
    text: str
    characters: tuple[PlayerRef, ...] = ()

    @property
    def content_hash(self) -> str:
        return content_hash(self.text)

    def columns(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "conversation_id": self.conversation_id,
            "message_seq": self.message_seq,
            "created_at": self.created_at,
            "label": self.label[:MAX_LABEL],
            "text": self.text,
            "content_hash": self.content_hash,
            "characters": [p.as_json() for p in self.characters] or None,
        }


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def bounded(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters at a word boundary, marked with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip() + "…"


def humanise(value: float | int) -> str:
    """139_100_000 -> "139.1M", 12_345 -> "12.3K", 950 -> "950"."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= size:
            return f"{value / size:.1f}{suffix}"
    return f"{value:g}" if isinstance(value, float) else str(value)
