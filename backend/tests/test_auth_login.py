"""US2 login / session / me / logout tests (T028)."""

from __future__ import annotations

from backend.app.config import settings


async def _invite_and_accept(as_admin, client, email="newuser@example.com", pw="a strong enough passphrase"):
    link = (
        await as_admin.client.post(
            "/api/admin/invitations", json={"email": email, "role": "tenant_admin"}
        )
    ).json()["invite_link"]
    token = link.split("#token=", 1)[1]
    await client.post(
        "/api/auth/accept-invitation",
        json={"token": token, "password": pw, "password_confirmation": pw},
    )
    return email, pw


async def test_login_success_sets_cookie_and_returns_me(as_admin, client):
    email, pw = await _invite_and_accept(as_admin, client)
    # Fresh client with Origin header, no session.
    resp = await client.post("/api/auth/login", json={"email": email, "password": pw})
    assert resp.status_code == 200, resp.text
    me = resp.json()
    assert me["email"] == email
    assert me["csrf_token"]
    assert me["active_tenant"] is not None
    assert settings.session_cookie_name in resp.headers.get("set-cookie", "")


async def test_login_generic_error_for_wrong_password(as_admin, client):
    email, _ = await _invite_and_accept(as_admin, client)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "wrong password here!!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_login_generic_error_for_unknown_email(client):
    resp = await client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever passphrase x"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_login_rejected_for_disabled_user(as_admin, client, session_factory):
    from sqlalchemy import select

    from backend.app.db.models import User

    email, pw = await _invite_and_accept(as_admin, client)
    async with session_factory() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        user.status = "disabled"
        await db.commit()
    resp = await client.post("/api/auth/login", json={"email": email, "password": pw})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_me_requires_session(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_returns_identity_for_authed(as_user):
    resp = await as_user.client.get("/api/auth/me")
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == as_user.email
    assert me["csrf_token"]  # recoverable after reload (HMAC-derived)


async def test_logout_revokes_session(as_user):
    # Authenticated action works first.
    assert (await as_user.client.get("/api/auth/me")).status_code == 200
    out = await as_user.client.post("/api/auth/logout")
    assert out.status_code == 204
    # The old cookie no longer works.
    after = await as_user.client.get("/api/auth/me")
    assert after.status_code == 401


async def test_unsafe_request_without_csrf_is_forbidden(as_admin):
    # Strip the CSRF header → admin POST must be rejected (CSRF guard).
    client = as_admin.client
    resp = await client.post(
        "/api/admin/invitations",
        json={"email": "x@example.com", "role": "member"},
        headers={"x-csrf-token": ""},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


async def test_unsafe_request_with_bad_origin_is_forbidden(as_admin):
    resp = await as_admin.client.post(
        "/api/admin/invitations",
        json={"email": "y@example.com", "role": "member"},
        headers={"origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"
