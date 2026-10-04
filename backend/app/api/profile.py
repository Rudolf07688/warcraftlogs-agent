"""REST: the per-tenant profile — self character, friends, main guild (US1, tenant-scoped US3).

Locking a character or guild schedules a non-blocking background guide task (US6, scoped to
the tenant) and returns immediately with a ``pending`` status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_tenant_db, require_csrf, require_session
from ..db import repository as repo
from ..schemas import (
    CharacterIn,
    CharacterOut,
    FriendPatchIn,
    GuildIn,
    GuildOut,
    ProfileOut,
)
from ..services.guide import schedule_character_guide, schedule_guild_summary
from ..tenancy.context import RequestIdentity, commit_and_rescope

router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _char_out(db: AsyncSession, char) -> CharacterOut:
    """Build a ``CharacterOut`` with guide status derived from the shared spec guide (FR-016).

    ``spec_guides`` is global (no RLS), so reading it on the tenant session is fine.
    """
    guide = None
    if char.class_name and char.active_spec:
        guide = await repo.get_spec_guide(
            db, class_name=char.class_name, spec=char.active_spec
        )
    return CharacterOut.from_character(char, guide)


@router.get("", response_model=ProfileOut)
async def get_profile(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> ProfileOut:
    self_char, friends, guild = await repo.get_profile(db, tenant_id=identity.tenant_id)
    chars = ([self_char] if self_char else []) + list(friends)
    pairs = [(c.class_name, c.active_spec) for c in chars if c.class_name and c.active_spec]
    guides = await repo.get_spec_guides_for(db, pairs)

    def out(c) -> CharacterOut:
        guide = guides.get((c.class_name, c.active_spec)) if c.class_name and c.active_spec else None
        return CharacterOut.from_character(c, guide)

    return ProfileOut(
        self_character=out(self_char) if self_char else None,
        friends=[out(f) for f in friends],
        guild=GuildOut.model_validate(guild) if guild else None,
    )


@router.put("/self", response_model=CharacterOut)
async def put_self(
    body: CharacterIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    char = await repo.upsert_self(
        db,
        tenant_id=identity.tenant_id,
        name=body.name,
        server=body.server,
        region=body.region,
        raid_role=body.raid_role,
    )
    await commit_and_rescope(db, identity)
    schedule_character_guide(char.id, identity.tenant_id)
    return await _char_out(db, char)


@router.post("/friends", response_model=CharacterOut, status_code=201)
async def add_friend(
    body: CharacterIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    try:
        char = await repo.add_friend(
            db,
            tenant_id=identity.tenant_id,
            name=body.name,
            server=body.server,
            region=body.region,
            raid_role=body.raid_role,
        )
        await commit_and_rescope(db, identity)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="duplicate_friend")
    schedule_character_guide(char.id, identity.tenant_id)
    return await _char_out(db, char)


@router.patch("/friends/{char_id}", response_model=CharacterOut)
async def patch_friend(
    char_id: uuid.UUID,
    body: FriendPatchIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    """Set a friend's raid-role override in place (US4). ``null`` reverts to inferred."""
    char = await repo.update_friend_role(
        db, char_id, tenant_id=identity.tenant_id, raid_role=body.raid_role
    )
    if char is None:
        raise HTTPException(status_code=404, detail="not_found")
    await commit_and_rescope(db, identity)
    return await _char_out(db, char)


@router.delete("/friends/{char_id}", status_code=204)
async def delete_friend(
    char_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    deleted = await repo.delete_friend(db, char_id, tenant_id=identity.tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")


@router.put("/guild", response_model=GuildOut)
async def put_guild(
    body: GuildIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> GuildOut:
    guild = await repo.set_guild(
        db, tenant_id=identity.tenant_id, name=body.name, server=body.server, region=body.region
    )
    await commit_and_rescope(db, identity)
    schedule_guild_summary(guild.id, identity.tenant_id)
    return GuildOut.model_validate(guild)


@router.delete("/guild", status_code=204)
async def delete_guild(
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    await repo.delete_guild(db, tenant_id=identity.tenant_id)
