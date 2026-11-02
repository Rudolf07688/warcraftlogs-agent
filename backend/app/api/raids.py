"""REST: tracked raids — list + one-click investigate (US1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from wcl_agent.agent import RAID_KICKOFF_OPENING

from ..auth.dependencies import get_tenant_db, require_csrf, require_session
from ..auth.rate_limit import investigate_limiter
from ..db import repository as repo
from ..model_state import get_model_state, is_valid_model
from ..services import kickoff_prefetch
from ..services.raids import _build_label
from ..schemas import (
    InvestigateRequest,
    InvestigateResponse,
    RaidListResponse,
    RaidOut,
)
from ..tenancy.context import RequestIdentity, commit_and_rescope

router = APIRouter(prefix="/api/raids", tags=["raids"])


def kickoff_prompt_for(report_code: str) -> str:
    """The server-owned kickoff wording for a one-click investigation (US1/FR-004).

    The frontend never hardcodes this — the server is the single source of truth
    for the report-code → prompt mapping. Its opening also selects the kickoff playbook in the
    agent instruction (050, sc-358).
    """
    # Feature 011 / FR-010: a bounded per-boss overview, so the first turn's evidence
    # gathering is naturally limited (one report-level round + one per-boss round).
    return (
        f"{RAID_KICKOFF_OPENING} (report {report_code}): for each boss, "
        "one headline finding and the single biggest improvement opportunity, noting "
        "kills versus wipes. Stay at the report and per-boss level; go into cast-level "
        "detail only where a boss clearly warrants it."
    )


@router.get("", response_model=RaidListResponse)
async def list_raids(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_tenant_db),
) -> RaidListResponse:
    raids = await repo.list_tracked_raids(db, tenant_id=identity.tenant_id)
    return RaidListResponse(raids=[RaidOut.model_validate(r) for r in raids])


async def within_investigate_limit(
    identity: RequestIdentity = Depends(require_csrf),
) -> RequestIdentity:
    """052 sc-352: per user, before the endpoint takes a tenant DB transaction and before the
    404 rule, so a 429 costs no pool connection and reveals nothing about the code."""
    if not investigate_limiter.allow_request(str(identity.user_id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many investigations. Slow down."},
            headers={"Retry-After": "60"},
        )
    return identity


@router.post("/{report_code}/investigate", response_model=InvestigateResponse, status_code=201)
async def investigate_raid(
    report_code: str,
    body: InvestigateRequest,
    request: Request,
    identity: RequestIdentity = Depends(within_investigate_limit),
    db: AsyncSession = Depends(get_tenant_db),
) -> InvestigateResponse:
    """Create an empty conversation to auto-investigate a raid.

    No message is persisted here — the client sends the returned ``kickoff_prompt``
    as a normal first turn over the WebSocket, which persists it through the
    standard path (no double-persist / seq-0 special case). The kickoff turn's data is
    pre-fetched in the background (``services.kickoff_prefetch``).
    """
    raid = await repo.get_tracked_raid(db, report_code, tenant_id=identity.tenant_id)
    if raid is None:
        # Feature 013: a raid from the welcome page becomes a tracked raid on investigation.
        # Arbitrary codes still 404: only this tenant's own recent raids qualify (FR-017).
        recent = await repo.get_recent_raid(db, report_code, tenant_id=identity.tenant_id)
        if recent is None:
            raise HTTPException(status_code=404, detail="not_found")
        label, zone, guild, started = _build_label(
            report_code,
            {
                "status": "success",
                "title": recent.title,
                "zone": recent.zone_name,
                "guild": recent.guild_name,
                "start_time_ms": recent.started_at.timestamp() * 1000,
            },
        )
        raid = await repo.upsert_tracked_raid(
            db,
            tenant_id=identity.tenant_id,
            report_code=report_code,
            label=label,
            zone=zone,
            guild=guild,
            report_started_at=started,
        )

    _, default_model, _ = get_model_state(request.app)
    model = body.model or default_model
    if not is_valid_model(request.app, model):
        raise HTTPException(status_code=400, detail="invalid_model")

    conv = await repo.create_conversation(
        db, model=model, title=raid.label[:60], tenant_id=identity.tenant_id
    )
    # 052 sc-352: committed first, so a failed commit starts no pre-fetch (re-scoped for any
    # later work on this session).
    await commit_and_rescope(db, identity)
    # 046 sc-339: warm the kickoff turn's data in the background, only past the 404 rule
    # above (schedule() checks store reads, the breaker and the per-report cooldown).
    kickoff_prefetch.schedule(identity, report_code)
    return InvestigateResponse(
        conversation_id=conv.id,
        model=model,
        kickoff_prompt=kickoff_prompt_for(report_code),
    )
