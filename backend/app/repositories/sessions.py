"""Session row access (feature 006). Policy (tokens, cookie, expiry) lives in auth/sessions.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Session


async def insert_session(
    session: AsyncSession,
    *,
    token_hash: bytes,
    user_id: uuid.UUID,
    active_tenant_id: uuid.UUID | None,
    expires_at: datetime,
    user_agent_hash: bytes | None = None,
) -> Session:
    row = Session(
        token_hash=token_hash,
        user_id=user_id,
        active_tenant_id=active_tenant_id,
        expires_at=expires_at,
        user_agent_hash=user_agent_hash,
    )
    session.add(row)
    await session.flush()
    return row


async def get_unrevoked_by_token_hash(session: AsyncSession, token_hash: bytes) -> Session | None:
    """Return the (possibly-expired) unrevoked session for this digest; caller checks expiry."""
    result = await session.execute(
        select(Session).where(Session.token_hash == token_hash, Session.revoked_at.is_(None))
    )
    return result.scalar_one_or_none()


async def revoke(session: AsyncSession, row: Session) -> None:
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await session.flush()


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


async def touch_last_seen(session: AsyncSession, row: Session, *, now: datetime | None = None) -> None:
    row.last_seen_at = now or datetime.now(timezone.utc)
    await session.flush()
