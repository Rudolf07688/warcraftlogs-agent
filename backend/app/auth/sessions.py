"""Opaque server-side session lifecycle + cookie helpers (feature 006, research R3).

A session is a random token: the RAW token lives only in the ``__Host-`` cookie; only its
sha256 digest is stored. Sessions expire two ways — **idle** (no use within
``session_idle_max_age_s``) and **absolute** (``expires_at``, a hard cap). ``last_seen_at``
is written at most every ``session_last_seen_throttle_s`` to avoid a write per request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db.models import Session as SessionRow
from ..repositories import sessions as sessions_repo
from . import csrf, tokens


@dataclass(frozen=True, slots=True)
class NewSession:
    """A freshly created session: the row plus the RAW tokens to hand the client once."""

    row: SessionRow
    raw_session_token: str
    raw_csrf_token: str


def _aware(dt: datetime) -> datetime:
    """Treat naive timestamps (SQLite) as UTC so comparisons never raise."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def create_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    active_tenant_id: uuid.UUID | None,
    user_agent: str | None = None,
) -> NewSession:
    """Mint a new session; the CSRF token is HMAC-derived from the new session id."""
    raw_token = tokens.generate_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.session_absolute_max_age_s)
    ua_hash = tokens.hash_token(user_agent) if user_agent else None
    row = await sessions_repo.insert_session(
        session,
        token_hash=tokens.hash_token(raw_token),
        user_id=user_id,
        active_tenant_id=active_tenant_id,
        expires_at=expires_at,
        user_agent_hash=ua_hash,
    )
    return NewSession(
        row=row, raw_session_token=raw_token, raw_csrf_token=csrf.issue_csrf(row.id)
    )


def is_expired(row: SessionRow, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if _aware(row.expires_at) <= now:
        return True
    idle_deadline = _aware(row.last_seen_at) + timedelta(seconds=settings.session_idle_max_age_s)
    return idle_deadline <= now


async def lookup_session(session: AsyncSession, raw_token: str) -> SessionRow | None:
    """Return the live session for a raw cookie token, or ``None`` if invalid/expired.

    Expired sessions are proactively revoked. A valid session's ``last_seen_at`` is
    refreshed at most once per throttle window.
    """
    if not raw_token:
        return None
    row = await sessions_repo.get_unrevoked_by_token_hash(session, tokens.hash_token(raw_token))
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    if is_expired(row, now):
        await sessions_repo.revoke(session, row)
        return None
    if (now - _aware(row.last_seen_at)).total_seconds() >= settings.session_last_seen_throttle_s:
        await sessions_repo.touch_last_seen(session, row, now=now)
    return row


async def revoke_session(session: AsyncSession, row: SessionRow) -> None:
    await sessions_repo.revoke(session, row)


async def revoke_all_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await sessions_repo.revoke_all_for_user(session, user_id)


# --- Cookie helpers ----------------------------------------------------------
# The __Host- prefix REQUIRES Secure + Path=/ + no Domain; set_cookie with no domain
# arg satisfies that. Clearing uses the same attributes so the browser matches it.


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_max_age_s,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
