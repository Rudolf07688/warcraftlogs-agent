"""REST: the per-tenant profile — own characters, friends, main guild (US1, tenant-scoped US3).

Feature 012: a tenant registers up to ``repo.MAX_OWN_CHARACTERS`` own characters (``/self``),
managed exactly like friends (``/friends``) through the same repository functions.

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
    CharacterPatchIn,
    GuildIn,
    GuildOut,
    ProfileOut,
)
from ..services.guide import schedule_character_guide, schedule_guild_summary
from ..tenancy.context import RequestIdentity, commit_and_rescope

router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _char_out(db: AsyncSession, char) -> CharacterOut:
    """Build a ``CharacterOut`` with guide statuses derived from the shared library (FR-016).

    ``spec_guides`` is global (no RLS), so reading it on the tenant session is fine.
    """
    guides: dict = {}
    if char.class_name and char.active_spec:
        keys = [(char.class_name, char.active_spec, ct) for ct in ("raid", "mplus")]
        rows = await repo.get_spec_guides_for(db, keys, with_text=False)
        guides = {ct: g for (_, _, ct), g in rows.items()}
    return CharacterOut.from_character(char, guides)


def _conflict(exc: repo.CharacterConflict) -> HTTPException:
    return HTTPException(status_code=409, detail=exc.code)


async def _add(
    db: AsyncSession, identity: RequestIdentity, body: CharacterIn, role: str
) -> CharacterOut:
    """Add an own or friend character, then schedule its background guide task."""
    try:
        char = await repo.add_character(
            db,
            tenant_id=identity.tenant_id,
            role=role,
            name=body.name,
            server=body.server,
            region=body.region,
            raid_role=body.raid_role,
        )
        await commit_and_rescope(db, identity)
    except repo.CharacterConflict as exc:
        await db.rollback()
        raise _conflict(exc)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="duplicate_character" if role == "self" else "duplicate_friend",
        )
    schedule_character_guide(char.id, identity.tenant_id)
    return await _char_out(db, char)


async def _patch(
    db: AsyncSession, identity: RequestIdentity, char_id: uuid.UUID, body: CharacterPatchIn, role: str
) -> CharacterOut:
    """Set a character's raid-role override in place (US4). ``null`` reverts to inferred."""
    char = await repo.update_character_role(
        db, char_id, tenant_id=identity.tenant_id, role=role, raid_role=body.raid_role
    )
    if char is None:
        raise HTTPException(status_code=404, detail="not_found")
    await commit_and_rescope(db, identity)
    return await _char_out(db, char)


async def _delete(
    db: AsyncSession, identity: RequestIdentity, char_id: uuid.UUID, role: str
) -> None:
    deleted = await repo.delete_character(db, char_id, tenant_id=identity.tenant_id, role=role)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")


@router.get("", response_model=ProfileOut)
async def get_profile(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> ProfileOut:
    own, friends, guild = await repo.get_profile(db, tenant_id=identity.tenant_id)
    chars = list(own) + list(friends)
    keys = [
        (c.class_name, c.active_spec, ct)
        for c in chars
        if c.class_name and c.active_spec
        for ct in ("raid", "mplus")
    ]
    guides = await repo.get_spec_guides_for(db, keys, with_text=False)  # status only, one query

    def out(c) -> CharacterOut:
        mine = {
            ct: guides.get((c.class_name, c.active_spec, ct))
            for ct in ("raid", "mplus")
            if c.class_name and c.active_spec
        }
        return CharacterOut.from_character(c, mine)

    return ProfileOut(
        own=[out(c) for c in own],
        own_limit=repo.MAX_OWN_CHARACTERS,
        friends=[out(f) for f in friends],
        guild=GuildOut.model_validate(guild) if guild else None,
    )


@router.post("/self", response_model=CharacterOut, status_code=201)
async def add_own_character(
    body: CharacterIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    return await _add(db, identity, body, "self")


@router.patch("/self/{char_id}", response_model=CharacterOut)
async def patch_own_character(
    char_id: uuid.UUID,
    body: CharacterPatchIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    return await _patch(db, identity, char_id, body, "self")


@router.delete("/self/{char_id}", status_code=204)
async def delete_own_character(
    char_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    await _delete(db, identity, char_id, "self")


@router.post("/friends", response_model=CharacterOut, status_code=201)
async def add_friend(
    body: CharacterIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    return await _add(db, identity, body, "friend")


@router.patch("/friends/{char_id}", response_model=CharacterOut)
async def patch_friend(
    char_id: uuid.UUID,
    body: CharacterPatchIn,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> CharacterOut:
    return await _patch(db, identity, char_id, body, "friend")


@router.delete("/friends/{char_id}", status_code=204)
async def delete_friend(
    char_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> None:
    await _delete(db, identity, char_id, "friend")


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
