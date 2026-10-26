"""The one write path for profile characters (feature 029, design C8).

Both the REST profile routes (``api/profile.py``) and proposal execution
(``services/profile_proposals.py``) add, re-role and remove own characters and friends
through these functions. They never commit: a REST call commits once per request, and a
proposal applies several items in one transaction. Callers schedule the guide task
(``schedule_character_guide``) **after** the commit, since the guide job reads the character
in its own transaction and would otherwise find nothing.
"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository as repo
from ..db.models import UserCharacter
from ..schemas import CharacterIn, RaidRole
from ..tenancy.context import RequestIdentity


class CharacterNotFound(Exception):
    """No ``role`` character with that id in the acting tenant's profile."""


async def add_character(
    db: AsyncSession, identity: RequestIdentity, body: CharacterIn, role: str
) -> UserCharacter:
    """Add an own (``"self"``) or friend character. Raises ``repo.CharacterConflict``."""
    try:
        return await repo.add_character(
            db,
            tenant_id=identity.tenant_id,
            role=role,
            name=body.name,
            server=body.server,
            region=body.region,
            raid_role=body.raid_role,
        )
    except IntegrityError as exc:
        # The DB unique constraint is the backstop for a same-role race.
        raise repo.CharacterConflict(
            "duplicate_character" if role == "self" else "duplicate_friend"
        ) from exc


async def set_raid_role(
    db: AsyncSession,
    identity: RequestIdentity,
    char_id: uuid.UUID,
    raid_role: RaidRole | None,
    role: str,
) -> UserCharacter:
    """Set (or, with ``None``, clear) a character's raid-role override in place."""
    char = await repo.update_character_role(
        db, char_id, tenant_id=identity.tenant_id, role=role, raid_role=raid_role
    )
    if char is None:
        raise CharacterNotFound(char_id)
    return char


async def remove_character(
    db: AsyncSession, identity: RequestIdentity, char_id: uuid.UUID, role: str
) -> None:
    if not await repo.delete_character(db, char_id, tenant_id=identity.tenant_id, role=role):
        raise CharacterNotFound(char_id)

