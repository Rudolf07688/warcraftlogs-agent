"""Shared test fixtures.

Repository/service/endpoint tests run against a fresh in-memory SQLite database
(the models use portable column types), so they need no external Postgres. The
live WebSocket stream and real Vertex/WCL calls are exercised in quickstart.md.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.models import Base


@pytest_asyncio.fixture
async def engine():
    # StaticPool keeps the single in-memory connection alive across sessions.
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


# --- Auth/tenancy test harness (feature 006, T021) ---------------------------
# ``as_user`` / ``as_admin`` provision a real user + tenant + membership + session in
# the SQLite test DB and hand back an httpx client whose cookie + CSRF header + Origin
# are pre-set, so the full auth code path (session lookup, CSRF, tenant scoping) runs
# against the in-memory DB — no stubbing of the security layer.

TEST_PASSWORD = "correct horse battery staple 42"


@dataclass(frozen=True)
class AuthedClient:
    client: AsyncClient
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    password: str
    session_token: str
    csrf_token: str


@pytest_asyncio.fixture
async def patched_db(session_factory, monkeypatch) -> async_sessionmaker[AsyncSession]:
    """Repoint the app's ``SessionLocal`` at the SQLite test factory for the test."""
    from backend.app.db import session as db_session

    monkeypatch.setattr(db_session, "SessionLocal", session_factory)
    return session_factory


@pytest_asyncio.fixture
async def client(patched_db) -> AsyncIterator[AsyncClient]:
    """Unauthenticated client (for login / accept-invitation / public routes)."""
    from backend.app.config import settings
    from backend.app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": settings.site_url}
    ) as c:
        yield c


async def _provision_authed(
    session_factory, *, email: str, is_admin: bool
) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    from backend.app.auth import sessions as session_svc
    from backend.app.auth.passwords import hash_password
    from backend.app.repositories import tenants as tenants_repo
    from backend.app.repositories import users as users_repo

    async with session_factory() as db:
        pw_hash = await hash_password(TEST_PASSWORD)
        user = await users_repo.create_user(
            db, email=email, status="active", is_platform_admin=is_admin, password_hash=pw_hash
        )
        tenant = await tenants_repo.create_tenant(db, name=email)
        await tenants_repo.create_membership(
            db, tenant_id=tenant.id, user_id=user.id, role="tenant_admin"
        )
        new = await session_svc.create_session(
            db, user_id=user.id, active_tenant_id=tenant.id
        )
        await db.commit()
        return user.id, tenant.id, new.raw_session_token, new.raw_csrf_token


async def _authed_client(patched_db, *, email: str, is_admin: bool) -> AuthedClient:
    from backend.app.config import settings
    from backend.app.main import app

    user_id, tenant_id, token, csrf = await _provision_authed(
        patched_db, email=email, is_admin=is_admin
    )
    transport = ASGITransport(app=app)
    c = AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "origin": settings.site_url,
            "x-csrf-token": csrf,
            # Send the session as an explicit Cookie header — httpx's jar won't match a
            # __Host- cookie against the bare "test" host used by ASGITransport.
            "cookie": f"{settings.session_cookie_name}={token}",
        },
    )
    return AuthedClient(
        client=c,
        user_id=user_id,
        tenant_id=tenant_id,
        email=email,
        password=TEST_PASSWORD,
        session_token=token,
        csrf_token=csrf,
    )


@pytest_asyncio.fixture
async def as_user(patched_db) -> AsyncIterator[AuthedClient]:
    authed = await _authed_client(patched_db, email="user@example.com", is_admin=False)
    try:
        yield authed
    finally:
        await authed.client.aclose()


@pytest_asyncio.fixture
async def as_admin(patched_db) -> AsyncIterator[AuthedClient]:
    authed = await _authed_client(patched_db, email="founder@example.com", is_admin=True)
    try:
        yield authed
    finally:
        await authed.client.aclose()


@pytest_asyncio.fixture
def make_authed_client(patched_db):
    """Factory for extra tenants in isolation tests (US3). Caller closes the client."""

    async def _make(email: str, *, is_admin: bool = False) -> AuthedClient:
        return await _authed_client(patched_db, email=email, is_admin=is_admin)

    return _make
