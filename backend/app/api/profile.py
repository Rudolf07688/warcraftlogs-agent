"""REST: the single global profile — self character, friends, main guild (US1).

A default-tenant singleton profile (no auth/multi-user in scope). Locking a
character or guild schedules a non-blocking background guide task (US6) and returns
immediately with a ``pending`` status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository as repo
from ..db.session import get_session
from ..schemas import (
    CharacterIn,
    CharacterOut,
    GuildIn,
    GuildOut,
    ProfileOut,
)
from ..services.guide import schedule_character_guide, schedule_guild_summary

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(session: AsyncSession = Depends(get_session)) -> ProfileOut:
    self_char, friends, guild = await repo.get_profile(session)
    return ProfileOut(
        self_character=CharacterOut.model_validate(self_char) if self_char else None,
        friends=[CharacterOut.model_validate(f) for f in friends],
        guild=GuildOut.model_validate(guild) if guild else None,
    )


@router.put("/self", response_model=CharacterOut)
async def put_self(
    body: CharacterIn, session: AsyncSession = Depends(get_session)
) -> CharacterOut:
    char = await repo.upsert_self(
        session, name=body.name, server=body.server, region=body.region
    )
    await session.commit()
    schedule_character_guide(char.id)
    return CharacterOut.model_validate(char)


@router.post("/friends", response_model=CharacterOut, status_code=201)
async def add_friend(
    body: CharacterIn, session: AsyncSession = Depends(get_session)
) -> CharacterOut:
    try:
        char = await repo.add_friend(
            session, name=body.name, server=body.server, region=body.region
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="duplicate_friend")
    schedule_character_guide(char.id)
    return CharacterOut.model_validate(char)


@router.delete("/friends/{char_id}", status_code=204)
async def delete_friend(
    char_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    deleted = await repo.delete_friend(session, char_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")
    await session.commit()


@router.put("/guild", response_model=GuildOut)
async def put_guild(
    body: GuildIn, session: AsyncSession = Depends(get_session)
) -> GuildOut:
    guild = await repo.set_guild(
        session, name=body.name, server=body.server, region=body.region
    )
    await session.commit()
    schedule_guild_summary(guild.id)
    return GuildOut.model_validate(guild)


@router.delete("/guild", status_code=204)
async def delete_guild(session: AsyncSession = Depends(get_session)) -> None:
    await repo.delete_guild(session)
    await session.commit()
