"""FastAPI auth dependencies (feature 006, T016).

- ``require_session`` → the authenticated ``RequestIdentity`` (401 if no live session).
- ``require_platform_admin`` → same, but 403 unless ``is_platform_admin``.
- ``require_csrf`` → identity + enforced CSRF/origin on unsafe methods.
- ``get_tenant_db`` → a tenant-scoped ``AsyncSession`` (RLS config set) for endpoint work.

Identity is derived ONLY from the session here — never from client input (FR-006).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
# Module import so tests can repoint ``db_session.SessionLocal`` at a SQLite factory.
from ..db import session as db_session
from ..repositories import tenants as tenants_repo
from ..repositories import users as users_repo
from ..tenancy.context import RequestIdentity, tenant_session
from . import sessions as session_svc
from .csrf import CSRF_HEADER, SAFE_METHODS, is_origin_allowed, verify_csrf


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Authentication required."},
    )


async def _resolve_identity(db: AsyncSession, raw_token: str | None) -> RequestIdentity | None:
    row = await session_svc.lookup_session(db, raw_token or "")
    if row is None:
        return None
    user = await users_repo.get_user_by_id(db, row.user_id)
    if user is None or user.status != "active":
        return None
    role: str | None = None
    if row.active_tenant_id is not None:
        membership = await tenants_repo.get_membership(db, row.active_tenant_id, user.id)
        tenant = await tenants_repo.get_tenant(db, row.active_tenant_id)
        if (
            membership is None
            or membership.status != "active"
            or tenant is None
            or tenant.status != "active"
        ):
            return None
        role = membership.role
    return RequestIdentity(
        user_id=user.id,
        tenant_id=row.active_tenant_id,
        membership_role=role,
        is_platform_admin=user.is_platform_admin,
        session_id=row.id,
    )


async def authenticate_session(raw_token: str | None) -> RequestIdentity | None:
    """Resolve a raw session token to an identity (or None). Shared by HTTP + WebSocket."""
    async with db_session.SessionLocal() as db:
        identity = await _resolve_identity(db, raw_token)
        await db.commit()  # persist throttled last_seen / proactive revoke
    return identity


async def require_session(request: Request) -> RequestIdentity:
    identity = await authenticate_session(request.cookies.get(settings.session_cookie_name))
    if identity is None:
        raise _unauthorized()
    return identity


async def require_platform_admin(
    identity: RequestIdentity = Depends(require_session),
) -> RequestIdentity:
    if not identity.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Platform admin required."},
        )
    return identity


async def require_csrf(
    request: Request, identity: RequestIdentity = Depends(require_session)
) -> RequestIdentity:
    """Identity + CSRF/origin enforcement for unsafe methods."""
    if request.method in SAFE_METHODS:
        return identity
    if not is_origin_allowed(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "Origin check failed."},
        )
    if not verify_csrf(identity.session_id, request.headers.get(CSRF_HEADER)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "Invalid CSRF token."},
        )
    return identity


async def get_tenant_db(
    identity: RequestIdentity = Depends(require_session),
) -> AsyncIterator[AsyncSession]:
    """Yield a tenant-scoped transaction (RLS config set) for endpoint data access."""
    async with tenant_session(identity) as db:
        yield db
