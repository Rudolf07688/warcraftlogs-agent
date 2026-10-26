"""Profile change proposals (feature 029): the row helpers behind services/profile_proposals.py.

Every query filters on the tenant **and** the user in the same WHERE as the id, so another
tenant's or another user's proposal is simply not found (no disclosure; tenancy guide,
"Tenant authorization"). RLS on ``profile_proposals`` is the backstop on Postgres.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ProfileProposal


async def insert_proposal(session: AsyncSession, row: ProfileProposal) -> ProfileProposal:
    session.add(row)
    await session.flush()
    return row


async def get_proposal_row(
    session: AsyncSession,
    proposal_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    for_update: bool = False,
) -> ProfileProposal | None:
    stmt = select(ProfileProposal).where(
        ProfileProposal.id == proposal_id,
        ProfileProposal.tenant_id == tenant_id,
        ProfileProposal.user_id == user_id,
    )
    if for_update:
        stmt = stmt.with_for_update()  # no-op on SQLite; row lock on Postgres
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_proposal_rows(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> list[ProfileProposal]:
    result = await session.execute(
        select(ProfileProposal)
        .where(
            ProfileProposal.tenant_id == tenant_id,
            ProfileProposal.user_id == user_id,
            ProfileProposal.conversation_id == conversation_id,
        )
        .order_by(ProfileProposal.created_at)
    )
    return list(result.scalars().all())


async def set_message_seq(
    session: AsyncSession,
    proposal_ids: list[uuid.UUID],
    seq: int,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Link this turn's proposals to its saved answer (feature 031), as artifacts are linked.

    Only the given ids: a proposal whose turn never finished keeps ``message_seq`` null and
    shows as a standalone card instead of moving under a later answer.
    """
    if not proposal_ids:
        return
    await session.execute(
        update(ProfileProposal)
        .where(
            ProfileProposal.id.in_(proposal_ids),
            ProfileProposal.tenant_id == tenant_id,
            ProfileProposal.user_id == user_id,
            ProfileProposal.message_seq.is_(None),
        )
        .values(message_seq=seq)
    )
    await session.flush()
