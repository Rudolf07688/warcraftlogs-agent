"""Invitation row access (feature 006)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Invitation


async def create_invitation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    email: str,
    role: str,
    token_hash: bytes,
    expires_at: datetime,
    invited_by: uuid.UUID | None,
) -> Invitation:
    invitation = Invitation(
        tenant_id=tenant_id,
        email=email,
        role=role,
        token_hash=token_hash,
        expires_at=expires_at,
        invited_by=invited_by,
    )
    session.add(invitation)
    await session.flush()
    return invitation


async def get_invitation(session: AsyncSession, invitation_id: uuid.UUID) -> Invitation | None:
    return await session.get(Invitation, invitation_id)


async def get_invitation_by_token_hash(
    session: AsyncSession, token_hash: bytes, *, for_update: bool = False
) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token_hash == token_hash)
    if for_update:
        stmt = stmt.with_for_update()  # no-op on SQLite; row lock on Postgres
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_open_invitations_for_email(
    session: AsyncSession, *, email: str, exclude_id: uuid.UUID | None = None
) -> None:
    """Revoke any still-open invitation for this email — used on resend/reinvite."""
    stmt = (
        update(Invitation)
        .where(
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    if exclude_id is not None:
        stmt = stmt.where(Invitation.id != exclude_id)
    await session.execute(stmt)


async def mark_accepted(session: AsyncSession, invitation: Invitation) -> None:
    invitation.accepted_at = datetime.now(timezone.utc)
    await session.flush()


async def mark_revoked(session: AsyncSession, invitation: Invitation) -> None:
    invitation.revoked_at = datetime.now(timezone.utc)
    await session.flush()


async def list_open_invitations(session: AsyncSession) -> list[Invitation]:
    result = await session.execute(
        select(Invitation)
        .where(Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())
