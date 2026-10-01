"""Async data-access helpers for conversations and messages."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Conversation, Message


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
    session: AsyncSession, conv_id: uuid.UUID, role: str, content: str
) -> Message:
    seq = await _next_seq(session, conv_id)
    msg = Message(conversation_id=conv_id, role=role, content=content, seq=seq)
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
