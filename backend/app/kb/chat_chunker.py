"""A finished chat exchange rendered as one knowledge base chunk (feature 043, sc-305).

The chunk is the user's message and the agent's saved final answer. Tool payloads and frames
never reach it: the answer is the streamed text the socket saved, and tool results travel as
separate records. The WCL data a tool returned is already a ``wcl`` chunk of its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from .chunks import MAX_CHAT_TEXT, ChatChunkDraft, PlayerRef, bounded

LABEL_WORDS = 12


@dataclass(frozen=True)
class ExchangeJob:
    """One completed turn, from the chat socket after its answer is saved."""

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    message_seq: int  # the agent answer's seq
    question: str
    answer: str
    created_at: datetime


def chunk_exchange(job: ExchangeJob, characters: tuple[PlayerRef, ...] = ()) -> ChatChunkDraft:
    question = " ".join(job.question.split())
    words = question.split(" ")
    label = " ".join(words[:LABEL_WORDS]) + ("…" if len(words) > LABEL_WORDS else "")
    text = bounded(f"Question: {job.question.strip()}\n\nAnswer: {job.answer.strip()}", MAX_CHAT_TEXT)
    return ChatChunkDraft(
        tenant_id=job.tenant_id,
        conversation_id=job.conversation_id,
        message_seq=job.message_seq,
        created_at=job.created_at,
        label=label or "(empty question)",
        text=text,
        characters=characters,
    )
