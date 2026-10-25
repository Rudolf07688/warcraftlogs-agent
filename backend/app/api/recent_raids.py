"""REST: the welcome page's recent raids (feature 013, contracts/rest-recent-raids.md)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_tenant_db, require_csrf, require_session
from ..config import settings
from ..db import repository as repo
from ..model_state import get_model_state, is_valid_model
from ..schemas import (
    InvestigateRequest,
    InvestigateResponse,
    RecentMplusRunOut,
    RecentRaidCharacterOut,
    RecentRaidOut,
    RecentRaidsRefreshOut,
    RecentRaidsResponse,
)
from ..services.recent_raids import collapse_duplicate_runs, maybe_start_refresh
from ..tenancy.context import RequestIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recent-raids", tags=["recent-raids"])


def mplus_kickoff_prompt_for(report_code: str, fight_id: int, dungeon: str, key_level: int) -> str:
    """The server-owned kickoff wording for a one-click Mythic+ review (feature 022, FR-016).

    Bounded like the raid kickoff (feature 011): run and segment level first, cast-level
    detail only where a segment clearly warrants it.
    """
    return (
        f"Review this Mythic+ run ({dungeon} +{key_level}, report {report_code}, fight {fight_id}): "
        "give me the result against the timer (timed or depleted, and by how much); for each "
        "pull or boss segment, the single biggest time loss; the deaths (who died, to what, "
        "and whether it was avoidable); interrupt coverage; and one headline improvement for "
        "my character. Stay at the run and segment level; go into cast-level detail only where "
        "a segment clearly warrants it."
    )


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
        db, tenant_id=identity.tenant_id, limit=settings.recent_raids_shown
    )
    # Over-fetch: the same key logged by two group members is stored once per log.
    runs = collapse_duplicate_runs(
        await repo.list_recent_mplus_runs(
            db, tenant_id=identity.tenant_id, limit=settings.recent_mplus_shown * 4
        ),
        settings.recent_mplus_shown,
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
    mplus_runs = [
        RecentMplusRunOut(
            report_code=r.report_code,
            fight_id=r.fight_id,
            dungeon=r.dungeon,
            key_level=r.key_level,
            started_at=r.started_at,
            timed=r.timed,
            characters=[
                RecentRaidCharacterOut(name=c.name, server=c.server, region=c.region)
                for c in cs
            ],
        )
        for r, cs in runs
    ]
    return RecentRaidsResponse(
        has_characters=True,
        raids=raids,
        mplus_runs=mplus_runs,
        refresh=await _refresh_state(db, identity),
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


@router.post(
    "/mplus/{report_code}/{fight_id}/investigate", response_model=InvestigateResponse, status_code=201
)
async def investigate_mplus_run(
    report_code: str,
    fight_id: int,
    body: InvestigateRequest,
    request: Request,
    identity: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_db),
) -> InvestigateResponse:
    """Create an empty conversation to review a stored Mythic+ run (feature 022).

    Like a raid investigation, the client sends the returned kickoff as the first turn.
    Only this tenant's own stored runs qualify (FR-011).
    """
    run = await repo.get_recent_mplus_run(db, report_code, fight_id, tenant_id=identity.tenant_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not_found")
    _, default_model, _ = get_model_state(request.app)
    model = body.model or default_model
    if not is_valid_model(request.app, model):
        raise HTTPException(status_code=400, detail="invalid_model")
    conv = await repo.create_conversation(
        db, model=model, title=f"M+ {run.dungeon} +{run.key_level}"[:60], tenant_id=identity.tenant_id
    )
    return InvestigateResponse(
        conversation_id=conv.id,
        model=model,
        kickoff_prompt=mplus_kickoff_prompt_for(
            report_code, fight_id, run.dungeon, run.key_level
        ),
    )
