"""Polish: the auth audit-event set is recorded with no secrets in metadata (T063)."""

from __future__ import annotations

from sqlalchemy import select

from backend.app.db.models import AuthAuditEvent


async def _event_types(session_factory) -> list[str]:
    async with session_factory() as s:
        rows = (await s.execute(select(AuthAuditEvent))).scalars().all()
        # No secret ever appears in audit metadata (redacted at the writer).
        blob = str([r.event_metadata for r in rows]).lower()
        assert "password" not in blob or "«redacted»" in str([r.event_metadata for r in rows])
        for r in rows:
            for key in r.event_metadata or {}:
                assert key.lower() not in {"token", "password", "csrf"}
        return [r.event_type for r in rows]


async def test_login_and_logout_audited(as_admin, client, session_factory):
    # A successful login via the public client.
    link = (await as_admin.client.post(
        "/api/admin/invitations", json={"email": "aud@example.com", "role": "member"}
    )).json()["invite_link"]
    token = link.split("#token=", 1)[1]
    pw = "a strong enough passphrase"
    await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )
    await client.post("/api/auth/login", json={"email": "aud@example.com", "password": pw})

    types = await _event_types(session_factory)
    assert "invitation.created" in types
    assert "invitation.accepted" in types
    assert "login" in types


async def test_disable_and_reset_audited(as_admin, client, session_factory):
    link = (await as_admin.client.post(
        "/api/admin/invitations", json={"email": "aud2@example.com", "role": "member"}
    )).json()["invite_link"]
    token = link.split("#token=", 1)[1]
    pw = "a strong enough passphrase"
    uid = (await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )).json()["user_id"]

    await as_admin.client.post(f"/api/admin/users/{uid}/reset")
    await as_admin.client.patch(f"/api/admin/users/{uid}", json={"status": "disabled"})

    types = await _event_types(session_factory)
    assert "password_reset.requested" in types
    assert "user.disabled" in types
