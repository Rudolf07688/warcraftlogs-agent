"""Founder-triggered password reset (feature 006, US5).

The admin triggers a reset → a single-use token (digest stored) → a founder-shared link.
Completing it rehashes the password, consumes the token, and revokes ALL the user's
sessions (so every device must sign in again). The admin never sees or sets the password.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import sessions as session_svc
from ..auth import tokens
from ..auth.passwords import PasswordPolicyError, hash_password, validate_password_policy
from ..config import settings
from ..repositories import audit
from ..repositories import reset_tokens as reset_repo
from ..repositories import users as users_repo


class ResetInvalid(Exception):
    code = "invalid_or_expired_token"
    message = "This reset link is invalid or has expired."


@dataclass(frozen=True)
class CreatedReset:
    raw_token: str


async def request_reset(
    db: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID | None
) -> CreatedReset:
    raw_token = tokens.generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.password_reset_ttl_s)
    await reset_repo.create_reset_token(
        db, user_id=user_id, token_hash=tokens.hash_token(raw_token), expires_at=expires_at
    )
    await audit.record_event(
        db, event_type="password_reset.requested", actor_user_id=actor_id, target_user_id=user_id
    )
    return CreatedReset(raw_token=raw_token)


async def complete_reset(
    db: AsyncSession, *, raw_token: str, password: str, password_confirmation: str
) -> None:
    if password != password_confirmation:
        raise PasswordPolicyError("Passwords do not match.")
    validate_password_policy(password)

    row = await reset_repo.get_by_token_hash(db, tokens.hash_token(raw_token), for_update=True)
    now = datetime.now(timezone.utc)
    expires = row.expires_at if row else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if row is None or row.consumed_at is not None or expires <= now:
        raise ResetInvalid()

    user = await users_repo.get_user_by_id(db, row.user_id)
    if user is None or user.status == "disabled":
        raise ResetInvalid()

    pw_hash = await hash_password(password)
    await users_repo.set_password(db, user, password_hash=pw_hash)
    await reset_repo.consume(db, row)
    # Revoke every session so all devices must re-authenticate (US5).
    await session_svc.revoke_all_user_sessions(db, user.id)
    await audit.record_event(
        db, event_type="password_reset.completed", actor_user_id=user.id, target_user_id=user.id
    )
