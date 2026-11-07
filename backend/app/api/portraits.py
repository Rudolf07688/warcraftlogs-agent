"""REST: portraits for the caller's profile characters (feature 075, contracts/portraits-api.md).

Its own request so the profile page never waits on Blizzard. The characters are read from the
caller's own profile on the server; the request carries no names.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_tenant_db, require_session
from ..db import repository as repo
from ..services.portraits import CharacterRef, portrait_urls
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/profile/portraits", tags=["profile"])


class PortraitOut(BaseModel):
    character_id: str
    name: str
    server: str
    region: str
    class_name: str | None
    portrait_url: str | None


class PortraitsOut(BaseModel):
    portraits: list[PortraitOut]


@router.get("", response_model=PortraitsOut)
async def list_portraits(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> PortraitsOut:
    chars = [
        *await repo.list_own_characters(db, tenant_id=identity.tenant_id),
        *await repo.list_friend_characters(db, tenant_id=identity.tenant_id),
    ]
    # Release the tenant transaction's connection before waiting on Blizzard.
    await db.commit()
    urls = await portrait_urls([CharacterRef(c.region, c.server, c.name) for c in chars])
    return PortraitsOut(
        portraits=[
            PortraitOut(
                character_id=str(c.id),
                name=c.name,
                server=c.server,
                region=c.region.lower(),
                class_name=c.class_name,
                portrait_url=url,
            )
            for c, url in zip(chars, urls, strict=True)
        ]
    )
