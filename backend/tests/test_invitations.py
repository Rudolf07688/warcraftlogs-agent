"""US1 invitation + activation tests (T022).

Exercises the real HTTP endpoints + auth stack against the SQLite test DB via the
``as_admin`` / ``client`` fixtures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.config import settings
from backend.app.db.models import Invitation, TenantMembership, User


def _token_from_link(link: str) -> str:
    assert "#token=" in link, link
    return link.split("#token=", 1)[1]


async def _create_invite(as_admin, email: str = "friend@example.com", role: str = "tenant_admin"):
    resp = await as_admin.client.post(
        "/api/admin/invitations", json={"email": email, "role": role}
    )
    return resp


async def test_admin_create_invitation_returns_link_once(as_admin):
    resp = await _create_invite(as_admin)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    assert body["email"] == "friend@example.com"
    assert body["invite_link"] and "#token=" in body["invite_link"]
    # The raw token is never echoed as a bare field (only inside the link).
    assert "token" not in body


async def test_non_admin_cannot_create_invitation(as_user):
    resp = await as_user.client.post(
        "/api/admin/invitations", json={"email": "x@example.com", "role": "member"}
    )
    assert resp.status_code == 403


async def test_accept_invitation_activates_and_signs_in(as_admin, client, session_factory):
    link = (await _create_invite(as_admin)).json()["invite_link"]
    token = _token_from_link(link)

    resp = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    assert resp.status_code == 200, resp.text
    me = resp.json()
    assert me["email"] == "friend@example.com"
    assert me["is_platform_admin"] is False
    assert me["active_tenant"] is not None
    assert len(me["memberships"]) == 1
    assert me["csrf_token"]
    # Session cookie was set.
    assert settings.session_cookie_name in resp.headers.get("set-cookie", "")

    # User is now active with a workspace + owner membership.
    async with session_factory() as db:
        user = (
            await db.execute(select(User).where(User.email == "friend@example.com"))
        ).scalar_one()
        assert user.status == "active"
        assert user.password_hash
        memberships = (
            await db.execute(select(TenantMembership).where(TenantMembership.user_id == user.id))
        ).scalars().all()
        assert len(memberships) == 1
        assert memberships[0].role == "tenant_admin"


async def test_reused_token_fails_generically(as_admin, client):
    token = _token_from_link((await _create_invite(as_admin)).json()["invite_link"])
    ok = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    assert ok.status_code == 200
    again = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_or_expired_invitation"


async def test_garbage_token_fails_generically(client):
    resp = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": "not-a-real-token",
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_or_expired_invitation"


async def test_expired_token_fails(as_admin, client, session_factory):
    token = _token_from_link((await _create_invite(as_admin)).json()["invite_link"])
    async with session_factory() as db:
        inv = (await db.execute(select(Invitation))).scalars().first()
        inv.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()
    resp = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    assert resp.status_code == 400


async def test_revoked_token_fails(as_admin, client, session_factory):
    token = _token_from_link((await _create_invite(as_admin)).json()["invite_link"])
    async with session_factory() as db:
        inv = (await db.execute(select(Invitation))).scalars().first()
        inv.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    resp = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    assert resp.status_code == 400


async def test_weak_and_mismatched_passwords_rejected(as_admin, client):
    token = _token_from_link((await _create_invite(as_admin)).json()["invite_link"])
    short = await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": "short", "password_confirmation": "short"},
    )
    assert short.status_code == 422
    # The response never echoes the attempted password.
    assert "short" not in short.text

    mismatch = await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a different passphrase entirely",
        },
    )
    assert mismatch.status_code == 422


async def test_reinvite_existing_member_conflicts(as_admin, client):
    # First invite + accept → user becomes a member.
    token = _token_from_link((await _create_invite(as_admin)).json()["invite_link"])
    await client.post(
        "/api/auth/accept-invitation",
        json={
            "token": token,
            "password": "a strong enough passphrase",
            "password_confirmation": "a strong enough passphrase",
        },
    )
    # Re-inviting the same email now conflicts (already has a workspace).
    resp = await _create_invite(as_admin)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "membership_exists"
