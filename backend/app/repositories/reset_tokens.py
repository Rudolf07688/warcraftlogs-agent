"""Password-reset token row access (feature 006)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import PasswordResetToken


async def create_reset_token(
    session: AsyncSession, *, user_id: uuid.UUID, token_hash: bytes, expires_at: datetime
) -> PasswordResetToken:
    row = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    session.add(row)
    await session.flush()
    return row


async def get_by_token_hash(
    session: AsyncSession, token_hash: bytes, *, for_update: bool = False
) -> PasswordResetToken | None:
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def consume(session: AsyncSession, row: PasswordResetToken) -> None:
    row.consumed_at = datetime.now(timezone.utc)
    await session.flush()
