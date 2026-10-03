"""US4 admin surface tests (T052): authz, invitations, disable/enable, no secrets."""

from __future__ import annotations

import pytest

ADMIN_PATHS = [
    ("get", "/api/admin/users"),
    ("get", "/api/admin/invitations"),
]


async def test_all_admin_endpoints_forbidden_for_non_admin(as_user):
    # GETs
    for method, path in ADMIN_PATHS:
        resp = await getattr(as_user.client, method)(path)
        assert resp.status_code == 403, f"{path} should be 403 for non-admin"
    # A representative unsafe endpoint
    resp = await as_user.client.post("/api/admin/invitations", json={"email": "x@e.com", "role": "member"})
    assert resp.status_code == 403


async def test_list_users_and_invitations(as_admin):
    # Create an invitation first.
    created = await as_admin.client.post(
        "/api/admin/invitations", json={"email": "friend@example.com", "role": "tenant_admin"}
    )
    assert created.status_code == 201

    users = (await as_admin.client.get("/api/admin/users")).json()["users"]
    emails = {u["email"] for u in users}
    assert "founder@example.com" in emails  # the admin themselves
    assert "friend@example.com" in emails  # the invited (not-yet-active) user
    # No secrets in the payload.
    assert "password_hash" not in str(users)
    assert "token" not in str(users)

    invites = (await as_admin.client.get("/api/admin/invitations")).json()["invitations"]
    assert len(invites) == 1
    assert invites[0]["status"] == "open"
    assert "invite_link" not in invites[0] or invites[0]["invite_link"] is None  # never on list


async def test_resend_invalidates_prior_link(as_admin):
    created = (await as_admin.client.post(
        "/api/admin/invitations", json={"email": "f@example.com", "role": "member"}
    )).json()
    inv_id = created["id"]
    first_link = created["invite_link"]

    resent = await as_admin.client.post(f"/api/admin/invitations/{inv_id}/resend")
    assert resent.status_code == 200
    new_link = resent.json()["invite_link"]
    assert new_link and new_link != first_link  # token rotated


async def test_revoke_invitation(as_admin, client):
    created = (await as_admin.client.post(
        "/api/admin/invitations", json={"email": "f@example.com", "role": "member"}
    )).json()
    inv_id = created["id"]
    token = created["invite_link"].split("#token=", 1)[1]

    revoked = await as_admin.client.delete(f"/api/admin/invitations/{inv_id}")
    assert revoked.status_code == 204
    # The revoked link no longer activates.
    accept = await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": "a strong enough passphrase", "password_confirmation": "a strong enough passphrase"},
    )
    assert accept.status_code == 400


async def test_disable_blocks_signin_and_enable_restores(as_admin, client, session_factory):
    from sqlalchemy import select

    from backend.app.db.models import User

    # Invite + accept a user.
    link = (await as_admin.client.post(
        "/api/admin/invitations", json={"email": "member@example.com", "role": "member"}
    )).json()["invite_link"]
    token = link.split("#token=", 1)[1]
    pw = "a strong enough passphrase"
    await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )

    async with session_factory() as s:
        uid = (await s.execute(select(User).where(User.email == "member@example.com"))).scalar_one().id

    # Disable → sign-in fails.
    disabled = await as_admin.client.patch(f"/api/admin/users/{uid}", json={"status": "disabled"})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert (await client.post("/api/auth/login", json={"email": "member@example.com", "password": pw})).status_code == 401

    # Enable → sign-in works again.
    enabled = await as_admin.client.patch(f"/api/admin/users/{uid}", json={"status": "active"})
    assert enabled.status_code == 200
    assert (await client.post("/api/auth/login", json={"email": "member@example.com", "password": pw})).status_code == 200


async def test_cannot_disable_last_admin(as_admin):
    resp = await as_admin.client.patch(
        f"/api/admin/users/{as_admin.user_id}", json={"status": "disabled"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "last_admin"
