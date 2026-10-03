"""Unit tests for RequestIdentity + tenant_session (T013)."""

from __future__ import annotations

import dataclasses
import uuid

import pytest
from sqlalchemy import text

from backend.app.tenancy.context import RequestIdentity, apply_tenant_scope, tenant_session


def _identity() -> RequestIdentity:
    return RequestIdentity(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


def test_request_identity_is_frozen():
    ident = _identity()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ident.is_platform_admin = True  # type: ignore[misc]


async def test_apply_tenant_scope_noop_on_sqlite(session):
    # Should not raise on SQLite (set_config is Postgres-only).
    await apply_tenant_scope(session, _identity())
    assert (await session.execute(text("SELECT 1"))).scalar_one() == 1


async def test_tenant_session_commits(session_factory):
    async with tenant_session(_identity(), factory=session_factory) as s:
        result = await s.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
