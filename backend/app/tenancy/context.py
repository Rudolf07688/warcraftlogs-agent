"""Request identity + tenant-scoped transactions (feature 006, research R4/R5).

``RequestIdentity`` is the ONLY authority handlers use for who-is-acting and which
tenant they're in — it is built from the authenticated session, never from client
input (FR-006). ``tenant_session`` opens a transaction and sets ``app.tenant_id`` /
``app.user_id`` **transaction-locally** so PostgreSQL RLS and application scoping agree.
On SQLite (tests) the ``set_config`` calls are skipped; app-level ``WHERE tenant_id``
scoping is what the SQLite suite asserts.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Imported as a module (not `from … import SessionLocal`) so tests can repoint
# ``db_session.SessionLocal`` at a SQLite factory and have it take effect here.
from ..db import session as db_session


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    """The authenticated security context for one request/socket. Immutable."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    membership_role: str | None
    is_platform_admin: bool
    session_id: uuid.UUID


async def set_scope(
    session: AsyncSession, *, tenant_id: uuid.UUID | None, user_id: uuid.UUID | None = None
) -> None:
    """Set transaction-local ``app.tenant_id`` / ``app.user_id`` for RLS (Postgres only)."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id) if tenant_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :uid, true)"),
        {"uid": str(user_id) if user_id else ""},
    )


async def apply_tenant_scope(session: AsyncSession, identity: RequestIdentity) -> None:
    """Scope a transaction to a request's identity (must run inside it). No-op on SQLite."""
    await set_scope(session, tenant_id=identity.tenant_id, user_id=identity.user_id)


@asynccontextmanager
async def tenant_scope(
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped transaction for non-request work (background jobs, WS internals)."""
    maker = factory or db_session.SessionLocal
    async with maker() as session:
        try:
            await set_scope(session, tenant_id=tenant_id, user_id=user_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def commit_and_rescope(session: AsyncSession, identity: RequestIdentity) -> None:
    """Commit, then re-apply the transaction-local tenant scope for subsequent work.

    ``set_config(…, true)`` is transaction-local, so a mid-handler commit drops it; without
    this the next query would run with no ``app.tenant_id`` and RLS would return nothing
    (Postgres). No-op difference on SQLite.
    """
    await session.commit()
    await apply_tenant_scope(session, identity)


@asynccontextmanager
async def tenant_session(
    identity: RequestIdentity,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a tenant-scoped transaction: set RLS config, yield, commit/rollback.

    ``factory`` defaults to the app's ``SessionLocal``; tests pass a SQLite factory.
    """
    maker = factory or db_session.SessionLocal
    async with maker() as session:
        try:
            await apply_tenant_scope(session, identity)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
