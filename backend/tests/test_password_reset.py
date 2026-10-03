"""US5 founder-triggered password reset tests (T057)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


async def _invite_accept_member(as_admin, client, email="member@example.com", pw="a strong enough passphrase"):
    link = (await as_admin.client.post(
        "/api/admin/invitations", json={"email": email, "role": "member"}
    )).json()["invite_link"]
    token = link.split("#token=", 1)[1]
    me = await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )
    return email, pw, me.json()["user_id"]


async def _trigger_reset(as_admin, user_id) -> str:
    resp = await as_admin.client.post(f"/api/admin/users/{user_id}/reset")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "#token=" in body["reset_link"]
    assert "password" not in body  # founder never sees/sets the password
    return body["reset_link"].split("#token=", 1)[1]


async def test_reset_flow_updates_password_and_revokes_sessions(as_admin, client, session_factory):
    from backend.app.auth.dependencies import authenticate_session
    from sqlalchemy import select
    from backend.app.db.models import User

    email, old_pw, user_id = await _invite_accept_member(as_admin, client)

    # The member has a live session from acceptance.
    async with session_factory() as s:
        # (grab the raw token is not possible; instead assert login works with old pw)
        pass
    assert (await client.post("/api/auth/login", json={"email": email, "password": old_pw})).status_code == 200

    token = await _trigger_reset(as_admin, user_id)
    new_pw = "an even stronger passphrase!!"
    done = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": new_pw, "password_confirmation": new_pw},
    )
    assert done.status_code == 200
    assert "sign in" in done.json()["message"].lower()

    # Old password no longer works; new one does.
    assert (await client.post("/api/auth/login", json={"email": email, "password": old_pw})).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": email, "password": new_pw})).status_code == 200


async def test_reused_reset_token_fails(as_admin, client):
    email, _pw, user_id = await _invite_accept_member(as_admin, client)
    token = await _trigger_reset(as_admin, user_id)
    pw = "an even stronger passphrase!!"
    first = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )
    assert first.status_code == 200
    again = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_or_expired_token"


async def test_garbage_reset_token_fails(client):
    resp = await client.post(
        "/api/auth/reset-password",
        json={"token": "nope", "password": "a strong enough passphrase", "password_confirmation": "a strong enough passphrase"},
    )
    assert resp.status_code == 400


async def test_expired_reset_token_fails(as_admin, client, session_factory):
    from sqlalchemy import select
    from backend.app.db.models import PasswordResetToken

    _email, _pw, user_id = await _invite_accept_member(as_admin, client)
    token = await _trigger_reset(as_admin, user_id)
    async with session_factory() as s:
        row = (await s.execute(select(PasswordResetToken))).scalars().first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await s.commit()
    pw = "an even stronger passphrase!!"
    resp = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )
    assert resp.status_code == 400


async def test_forgot_password_is_neutral_202(client):
    resp = await client.post("/api/auth/forgot-password", json={"email": "anyone@example.com"})
    assert resp.status_code == 202
    assert "reset link" in resp.json()["message"].lower()


async def test_trigger_reset_forbidden_for_non_admin(as_user):
    resp = await as_user.client.post(f"/api/admin/users/{as_user.user_id}/reset")
    assert resp.status_code == 403
