"""Public + session auth endpoints (`/api/auth/*`) — feature 006.

US1 ships accept-invitation; login/logout/me land in US2 (same router). Public errors are
generic (no account enumeration). Secrets never appear in responses except the raw session
cookie and the in-body CSRF token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import csrf as csrf_mod
from ..auth import sessions as session_svc
from ..auth import tokens
from ..auth.dependencies import require_session
from ..auth.passwords import PasswordPolicyError
from ..auth.rate_limit import token_limiter
from ..config import settings
from ..db.models import User
from ..db.session import get_session
from ..repositories import sessions as sessions_repo
from ..repositories import users as users_repo
from ..repositories import tenants as tenants_repo
from ..schemas import (
    AcceptInvitationIn,
    ActionMessageOut,
    ForgotPasswordIn,
    LoginIn,
    MeOut,
    MembershipRef,
    ResetPasswordIn,
    TenantRef,
)
from ..services import auth_service, invitation_service, password_reset_service
from ..tenancy.context import RequestIdentity

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def build_me_out(
    db: AsyncSession, user: User, active_tenant_id: uuid.UUID | None, csrf_token: str
) -> MeOut:
    """Assemble the identity payload the SPA bootstraps from (login/accept/me/reset)."""
    memberships = await tenants_repo.list_memberships_for_user(db, user.id)
    refs = [
        MembershipRef(tenant_id=t.id, name=t.name, role=m.role) for m, t in memberships
    ]
    active = next(
        (TenantRef(id=t.id, name=t.name) for _, t in memberships if t.id == active_tenant_id),
        None,
    )
    return MeOut(
        user_id=user.id,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
        active_tenant=active,
        memberships=refs,
        csrf_token=csrf_token,
    )


def _source_key(request: Request, prefix: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{prefix}:{host}"


@router.post("/accept-invitation", response_model=MeOut)
async def accept_invitation(
    body: AcceptInvitationIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> MeOut:
    if not token_limiter.allow_request(_source_key(request, "accept")):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many attempts. Try again shortly."},
        )
    try:
        result = await invitation_service.accept_invitation(
            db,
            raw_token=body.token,
            password=body.password,
            password_confirmation=body.password_confirmation,
            user_agent=request.headers.get("user-agent"),
        )
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_password", "message": str(exc)},
        ) from exc
    except invitation_service.InvitationInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    session_svc.set_session_cookie(response, result.session.raw_session_token)
    return await build_me_out(
        db, result.user, result.tenant.id, result.session.raw_csrf_token
    )


@router.post("/login", response_model=MeOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> MeOut:
    host = request.client.host if request.client else "unknown"
    try:
        result = await auth_service.login(
            db,
            email=body.email,
            password=body.password,
            source=host,
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.RateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many attempts. Try again shortly."},
            headers={"Retry-After": str(int(exc.retry_after) + 1)},
        ) from exc
    except auth_service.LoginFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    session_svc.set_session_cookie(response, result.session.raw_session_token)
    return await build_me_out(
        db, result.user, result.active_tenant_id, result.session.raw_csrf_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_session)
) -> None:
    """Idempotent: revokes the current session if valid; always clears the cookie.

    CSRF/origin is enforced only when a live session is present (so a stale cookie still
    gets a clean 204 and the client ends up signed out either way).
    """
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        row = await sessions_repo.get_unrevoked_by_token_hash(db, tokens.hash_token(raw))
        if row is not None:
            if not csrf_mod.is_origin_allowed(request) or not csrf_mod.verify_csrf(
                row.id, request.headers.get(csrf_mod.CSRF_HEADER)
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "csrf_failed", "message": "Invalid CSRF token."},
                )
            await auth_service.logout(db, session_id=row.id)
    session_svc.clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.get("/me", response_model=MeOut)
async def me(
    identity: RequestIdentity = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> MeOut:
    user = await users_repo.get_user_by_id(db, identity.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Authentication required."},
        )
    # CSRF token is HMAC-derived, so /me recovers it after a page reload.
    csrf_token = csrf_mod.issue_csrf(identity.session_id)
    return await build_me_out(db, user, identity.tenant_id, csrf_token)


@router.post("/reset-password", response_model=ActionMessageOut)
async def reset_password(
    body: ResetPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> ActionMessageOut:
    if not token_limiter.allow_request(_source_key(request, "reset")):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many attempts. Try again shortly."},
        )
    try:
        await password_reset_service.complete_reset(
            db,
            raw_token=body.token,
            password=body.password,
            password_confirmation=body.password_confirmation,
        )
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_password", "message": str(exc)},
        ) from exc
    except password_reset_service.ResetInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    # No new session: all sessions were revoked; the user signs in again.
    return ActionMessageOut(message="Password updated. Please sign in.")


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, response_model=ActionMessageOut)
async def forgot_password(
    body: ForgotPasswordIn, request: Request
) -> ActionMessageOut:
    """Deferred in v1 (no email provider): always a neutral 202, performs no delivery.

    Wired now so enabling email later turns on self-service without an API change.
    """
    token_limiter.allow_request(_source_key(request, "forgot"))
    return ActionMessageOut(message="If that account exists, a reset link has been sent.")
