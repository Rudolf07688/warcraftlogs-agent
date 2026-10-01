"""Async data-access helpers for conversations and messages."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import CapturedGraph, Conversation, Message, TrackedRaid


async def create_conversation(
    session: AsyncSession, model: str, title: str | None = None
) -> Conversation:
    conv = Conversation(model=model, title=title or "New chat")
    session.add(conv)
    await session.flush()  # populate id/timestamps
    return conv


async def get_conversation(session: AsyncSession, conv_id: uuid.UUID) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def list_conversations(session: AsyncSession) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def delete_conversation(session: AsyncSession, conv_id: uuid.UUID) -> bool:
    result = await session.execute(delete(Conversation).where(Conversation.id == conv_id))
    return result.rowcount > 0


async def _next_seq(session: AsyncSession, conv_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Message.seq), -1)).where(
            Message.conversation_id == conv_id
        )
    )
    return int(result.scalar_one()) + 1


async def add_message(
    session: AsyncSession,
    conv_id: uuid.UUID,
    role: str,
    content: str,
    status: str = "complete",
) -> Message:
    seq = await _next_seq(session, conv_id)
    msg = Message(conversation_id=conv_id, role=role, content=content, seq=seq, status=status)
    session.add(msg)
    # Touch the conversation so the sidebar re-orders and title can be set.
    conv = await session.get(Conversation, conv_id)
    if conv is not None:
        if role == "user" and (conv.title in (None, "", "New chat")):
            conv.title = content[:60]
    await session.flush()
    return msg


async def list_messages(session: AsyncSession, conv_id: uuid.UUID) -> list[Message]:
    result = await session.execute(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq)
    )
    return list(result.scalars().all())


# --- Tracked raids (US1) ------------------------------------------------------


async def upsert_tracked_raid(
    session: AsyncSession,
    *,
    report_code: str,
    label: str,
    zone: str | None = None,
    guild: str | None = None,
    report_started_at: datetime | None = None,
    conversation_id: uuid.UUID | None = None,
) -> TrackedRaid:
    """Insert a raid on first capture, or touch ``last_asked_at`` on re-reference.

    Dedup is by ``report_code`` (FR-002); re-referencing never creates duplicates.
    """
    existing = await session.execute(
        select(TrackedRaid).where(TrackedRaid.report_code == report_code)
    )
    raid = existing.scalar_one_or_none()
    if raid is None:
        raid = TrackedRaid(
            report_code=report_code,
            label=label,
            zone=zone,
            guild=guild,
            report_started_at=report_started_at,
            last_conversation_id=conversation_id,
        )
        session.add(raid)
    else:
        raid.last_asked_at = datetime.now(timezone.utc)
        if conversation_id is not None:
            raid.last_conversation_id = conversation_id
        # Backfill label/metadata if it was previously only the bare code.
        if label and (not raid.label or raid.label == raid.report_code):
            raid.label = label
        if zone and not raid.zone:
            raid.zone = zone
        if guild and not raid.guild:
            raid.guild = guild
        if report_started_at and not raid.report_started_at:
            raid.report_started_at = report_started_at
    await session.flush()
    return raid


async def list_tracked_raids(session: AsyncSession) -> list[TrackedRaid]:
    result = await session.execute(
        select(TrackedRaid).order_by(TrackedRaid.last_asked_at.desc())
    )
    return list(result.scalars().all())


async def get_tracked_raid(session: AsyncSession, report_code: str) -> TrackedRaid | None:
    result = await session.execute(
        select(TrackedRaid).where(TrackedRaid.report_code == report_code)
    )
    return result.scalar_one_or_none()


# --- Captured graphs (US5) ----------------------------------------------------


async def add_captured_graph(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    report_code: str,
    data_type: str,
    graph_json: dict,
    fight_id: int = 0,
    source_id: int = 0,
    message_seq: int | None = None,
) -> CapturedGraph:
    graph = CapturedGraph(
        conversation_id=conversation_id,
        report_code=report_code,
        data_type=data_type,
        graph_json=graph_json,
        fight_id=fight_id,
        source_id=source_id,
        message_seq=message_seq,
    )
    session.add(graph)
    await session.flush()
    return graph


async def list_captured_graphs(
    session: AsyncSession, conv_id: uuid.UUID
) -> list[CapturedGraph]:
    result = await session.execute(
        select(CapturedGraph)
        .where(CapturedGraph.conversation_id == conv_id)
        .order_by(
            CapturedGraph.message_seq.is_(None),  # non-null seqs first
            CapturedGraph.message_seq,
            CapturedGraph.created_at,
        )
    )
    return list(result.scalars().all())
