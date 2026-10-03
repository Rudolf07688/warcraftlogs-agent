"""Platform-admin endpoints (`/api/admin/*`) — feature 006.

Every route requires ``require_platform_admin`` (server-side, independent of any UI hiding)
plus CSRF on unsafe methods. Views never expose password or token hashes. The raw invite/
reset link is returned ONCE, only from create/resend/trigger-reset. US1 ships create; the
list/resend/revoke/disable endpoints land in US4, reset in US5.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_csrf, require_platform_admin
from ..auth.rate_limit import token_limiter
from ..db.models import Invitation
from ..db.session import get_session
from ..schemas import InvitationIn, InvitationOut
from ..services import invitation_service, link_delivery
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/admin", tags=["admin"])


def invitation_status(inv: Invitation) -> str:
    if inv.accepted_at is not None:
        return "accepted"
    if inv.revoked_at is not None:
        return "revoked"
    expires = inv.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return "expired"
    return "open"


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: InvitationIn,
    request: Request,
    identity: RequestIdentity = Depends(require_platform_admin),
    _csrf: RequestIdentity = Depends(require_csrf),
    db: AsyncSession = Depends(get_session),
) -> InvitationOut:
    host = request.client.host if request.client else "unknown"
    if not token_limiter.allow_request(f"admin-invite:{host}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many invitations. Slow down."},
        )
    try:
        created = await invitation_service.create_invitation(
            db, email=body.email, role=body.role, invited_by=identity.user_id
        )
    except invitation_service.InvitationConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    invite_link = await link_delivery.deliver_invitation_link(
        email=created.invitation.email, raw_token=created.raw_token
    )
    inv = created.invitation
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role,
        status=invitation_status(inv),
        expires_at=inv.expires_at,
        invite_link=invite_link,
    )
