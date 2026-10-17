"""REST: the welcome page's recent raids (feature 013, contracts/rest-recent-raids.md)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_tenant_db, require_csrf, require_session
from ..config import settings
from ..db import repository as repo
from ..schemas import (
    RecentRaidCharacterOut,
    RecentRaidOut,
    RecentRaidsRefreshOut,
    RecentRaidsResponse,
)
from ..services.recent_raids import maybe_start_refresh
from ..tenancy.context import RequestIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recent-raids", tags=["recent-raids"])


async def _refresh_state(db: AsyncSession, identity: RequestIdentity) -> RecentRaidsRefreshOut:
    row = await repo.get_refresh(db, tenant_id=identity.tenant_id)
    if row is None:
        return RecentRaidsRefreshOut(status="idle", last_success_at=None, last_error=None)
    return RecentRaidsRefreshOut(
        status=row.status, last_success_at=row.last_success_at, last_error=row.last_error
    )


@router.get("", response_model=RecentRaidsResponse)
async def list_recent_raids(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> RecentRaidsResponse:
    """Stored raids now; a due refresh is started in the background, never awaited (FR-010)."""
    chars = await repo.list_own_characters(db, tenant_id=identity.tenant_id)
    if not chars:
        return RecentRaidsResponse(
            has_characters=False,
            raids=[],
            refresh=RecentRaidsRefreshOut(status="idle", last_success_at=None, last_error=None),
        )
    try:
        await maybe_start_refresh(db, tenant_id=identity.tenant_id, chars=chars, identity=identity)
    except Exception:  # noqa: BLE001 - the stored list is still returned
        logger.exception("recent raids: could not start a refresh")
    rows = await repo.list_recent_raids(
        db, tenant_id=identity.tenant_id, limit=settings.recent_raids_limit
    )
    raids = [
        RecentRaidOut(
            report_code=r.report_code,
            title=r.title,
            zone_name=r.zone_name,
            started_at=r.started_at,
            difficulty=r.difficulty,
            bosses_pulled=r.bosses_pulled,
            bosses_killed=r.bosses_killed,
            is_final=r.is_final,
            characters=[
                RecentRaidCharacterOut(name=c.name, server=c.server, region=c.region)
                for c in cs
            ],
        )
        for r, cs in rows
    ]
    return RecentRaidsResponse(
        has_characters=True, raids=raids, refresh=await _refresh_state(db, identity)
    )


@router.post(
    "/refresh",
    response_model=RecentRaidsRefreshOut,
    responses={202: {"model": RecentRaidsRefreshOut}, 409: {"description": "no_characters"}},
)
async def refresh_recent_raids(
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Explicit Retry (FR-015): a forced claim, which only passes the gate after a failure
    and never takes over a live run (FR-025). ``202`` when a refresh was started."""
    chars = await repo.list_own_characters(db, tenant_id=identity.tenant_id)
    if not chars:
        raise HTTPException(status_code=409, detail="no_characters")
    started = await maybe_start_refresh(
        db, tenant_id=identity.tenant_id, chars=chars, force=True, identity=identity
    )
    state = await _refresh_state(db, identity)
    if started:
        return JSONResponse(status_code=202, content=state.model_dump(mode="json"))
    return state
