"""Platform-admin endpoints (`/api/admin/*`) — feature 006.

Every route requires ``require_platform_admin`` (server-side, independent of any UI hiding)
plus CSRF on unsafe methods. Views never expose password or token hashes. The raw invite/
reset link is returned ONCE, only from create/resend/trigger-reset. US1 ships create; the
list/resend/revoke/disable endpoints land in US4, reset in US5.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import sessions as session_svc
from ..auth.dependencies import require_csrf, require_platform_admin
from ..auth.rate_limit import token_limiter
from ..db.models import Invitation
from ..db.session import get_session
from ..repositories import audit
from ..repositories import invitations as inv_repo
from ..repositories import tenants as tenants_repo
from ..repositories import users as users_repo
from ..schemas import (
    AdminUserListResponse,
    AdminUserOut,
    AdminUserPatchIn,
    InvitationIn,
    InvitationListResponse,
    InvitationOut,
    MembershipRef,
    ResetLinkOut,
)
from ..services import invitation_service, link_delivery, password_reset_service
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _admin_user_out(db, user) -> AdminUserOut:
    memberships = await tenants_repo.list_memberships_for_user(db, user.id)
    return AdminUserOut(
        id=user.id,
        email=user.email,
        status=user.status,
        last_login_at=user.last_login_at,
        memberships=[MembershipRef(tenant_id=t.id, name=t.name, role=m.role) for m, t in memberships],
    )


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


# NOTE: membership add/change/remove endpoints are deliberately deferred in v1 (one
# workspace per user). The tenant_memberships table + MembershipIn schema are retained so
# they can be added later without rework (plan Complexity Tracking).


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    _identity: RequestIdentity = Depends(require_platform_admin),
    db=Depends(get_session),
    limit: int = 100,
    cursor: str | None = None,
) -> AdminUserListResponse:
    # Friends-scale deployment: return all users in one page (cursor reserved for later).
    users = await users_repo.list_users(db)
    return AdminUserListResponse(
        users=[await _admin_user_out(db, u) for u in users], next_cursor=None
    )


@router.get("/invitations", response_model=InvitationListResponse)
async def list_invitations(
    _identity: RequestIdentity = Depends(require_platform_admin),
    db=Depends(get_session),
) -> InvitationListResponse:
    invites = await inv_repo.list_open_invitations(db)
    return InvitationListResponse(
        invitations=[
            # Never expose the token / link on a list view (admin-api.md).
            InvitationOut(
                id=i.id,
                email=i.email,
                role=i.role,
                status=invitation_status(i),
                expires_at=i.expires_at,
            )
            for i in invites
        ]
    )


@router.post("/invitations/{invitation_id}/resend", response_model=InvitationOut)
async def resend_invitation(
    invitation_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_platform_admin),
    _csrf: RequestIdentity = Depends(require_csrf),
    db=Depends(get_session),
) -> InvitationOut:
    try:
        created = await invitation_service.resend_invitation(
            db, invitation_id=invitation_id, actor_id=identity.user_id
        )
    except invitation_service.InvitationInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": exc.message},
        ) from exc
    link = await link_delivery.deliver_invitation_link(
        email=created.invitation.email, raw_token=created.raw_token
    )
    inv = created.invitation
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role,
        status=invitation_status(inv),
        expires_at=inv.expires_at,
        invite_link=link,
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_platform_admin),
    _csrf: RequestIdentity = Depends(require_csrf),
    db=Depends(get_session),
) -> None:
    await invitation_service.revoke_invitation(
        db, invitation_id=invitation_id, actor_id=identity.user_id
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def patch_user(
    user_id: uuid.UUID,
    body: AdminUserPatchIn,
    identity: RequestIdentity = Depends(require_platform_admin),
    _csrf: RequestIdentity = Depends(require_csrf),
    db=Depends(get_session),
) -> AdminUserOut:
    user = await users_repo.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "User not found."},
        )
    if body.status == "disabled":
        # Never disable the last active platform admin.
        if user.is_platform_admin and await users_repo.count_active_admins(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "last_admin", "message": "Cannot disable the last admin."},
            )
        await users_repo.set_status(db, user, status="disabled")
        await session_svc.revoke_all_user_sessions(db, user.id)  # kick active sessions
        await audit.record_event(
            db, event_type="user.disabled", actor_user_id=identity.user_id, target_user_id=user.id
        )
    else:
        await users_repo.set_status(db, user, status="active")
        await audit.record_event(
            db, event_type="user.enabled", actor_user_id=identity.user_id, target_user_id=user.id
        )
    return await _admin_user_out(db, user)


@router.post("/users/{user_id}/reset", response_model=ResetLinkOut)
async def trigger_reset(
    user_id: uuid.UUID,
    identity: RequestIdentity = Depends(require_platform_admin),
    _csrf: RequestIdentity = Depends(require_csrf),
    db=Depends(get_session),
) -> ResetLinkOut:
    user = await users_repo.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "User not found."},
        )
    created = await password_reset_service.request_reset(
        db, user_id=user_id, actor_id=identity.user_id
    )
    link = await link_delivery.deliver_reset_link(email=user.email, raw_token=created.raw_token)
    return ResetLinkOut(reset_link=link)
