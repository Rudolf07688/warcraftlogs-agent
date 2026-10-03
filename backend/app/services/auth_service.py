"""Login / logout workflows (feature 006, US2).

Login is constant-time against account enumeration (dummy-hash for unknown emails),
progressively throttled per account+source, and sets the user's single tenant active.
All failure causes collapse to one generic error.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import sessions as session_svc
from ..auth.passwords import verify_password
from ..auth.rate_limit import login_limiter
from ..db.models import Session, User
from ..repositories import audit
from ..repositories import sessions as sessions_repo
from ..repositories import tenants as tenants_repo
from ..repositories import users as users_repo


class LoginFailed(Exception):
    code = "invalid_credentials"
    message = "Invalid email or password."


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__("rate_limited")
        self.retry_after = retry_after


@dataclass(frozen=True)
class LoginResult:
    user: User
    active_tenant_id: uuid.UUID
    session: session_svc.NewSession


async def login(
    db: AsyncSession, *, email: str, password: str, source: str, user_agent: str | None = None
) -> LoginResult:
    normalized = users_repo.normalize_email(email)
    key = f"{normalized}|{source}"
    retry = login_limiter.retry_after(key)
    if retry > 0:
        raise RateLimited(retry)

    user = await users_repo.get_user_by_email(db, normalized)
    # Always run a verify (dummy hash for unknown email) to equalize timing.
    ok, updated_hash = await verify_password(password, user.password_hash if user else None)

    memberships = (
        await tenants_repo.list_memberships_for_user(db, user.id) if user is not None else []
    )
    if user is None or not ok or user.status != "active" or not memberships:
        login_limiter.record_failure(key)
        if user is not None:
            await users_repo.record_login_failure(db, user)
        await audit.record_event(
            db,
            event_type="login",
            outcome="failure",
            target_user_id=user.id if user else None,
            metadata={"email": normalized},
        )
        raise LoginFailed()

    active_tenant_id = memberships[0][1].id
    if updated_hash:  # rehash-on-login when stored params are outdated
        await users_repo.set_password(db, user, password_hash=updated_hash)
    login_limiter.record_success(key)
    await users_repo.record_login_success(db, user)
    new_session = await session_svc.create_session(
        db, user_id=user.id, active_tenant_id=active_tenant_id, user_agent=user_agent
    )
    await audit.record_event(
        db,
        event_type="login",
        outcome="success",
        actor_user_id=user.id,
        tenant_id=active_tenant_id,
    )
    return LoginResult(user=user, active_tenant_id=active_tenant_id, session=new_session)


async def logout(db: AsyncSession, *, session_id: uuid.UUID) -> None:
    """Revoke a session by id (idempotent)."""
    row = await db.get(Session, session_id)
    if row is not None and row.revoked_at is None:
        await sessions_repo.revoke(db, row)
        await audit.record_event(
            db, event_type="logout", actor_user_id=row.user_id, tenant_id=row.active_tenant_id
        )
