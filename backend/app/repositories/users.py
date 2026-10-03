"""User row access (feature 006)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import User


def normalize_email(email: str) -> str:
    """Case-fold + trim for a stable, case-insensitive identity (matches DB citext)."""
    return email.strip().lower()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    status: str = "invited",
    is_platform_admin: bool = False,
    password_hash: str | None = None,
) -> User:
    user = User(
        email=normalize_email(email),
        status=status,
        is_platform_admin=is_platform_admin,
        password_hash=password_hash,
    )
    session.add(user)
    await session.flush()
    return user


async def activate_with_password(
    session: AsyncSession, user: User, *, password_hash: str
) -> User:
    """Set the first/new password and mark the account active (invitation accept)."""
    user.password_hash = password_hash
    user.status = "active"
    user.password_changed_at = datetime.now(timezone.utc)
    await session.flush()
    return user


async def set_password(session: AsyncSession, user: User, *, password_hash: str) -> User:
    user.password_hash = password_hash
    user.password_changed_at = datetime.now(timezone.utc)
    await session.flush()
    return user


async def set_status(session: AsyncSession, user: User, *, status: str) -> User:
    user.status = status
    await session.flush()
    return user


async def record_login_success(session: AsyncSession, user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.login_blocked_until = None
    await session.flush()


async def record_login_failure(session: AsyncSession, user: User) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    await session.flush()


async def count_active_admins(session: AsyncSession) -> int:
    """Platform admins that can still sign in — used to block disabling the last one."""
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.is_platform_admin.is_(True), User.status == "active")
    )
    return int(result.scalar_one())


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())
