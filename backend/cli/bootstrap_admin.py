"""Create the first platform administrator (feature 006, research R8).

Run ONCE after ``alembic upgrade 0002_auth_tenancy`` and BEFORE ``alembic upgrade head``
(the 0003 founder-data backfill needs this tenant to exist). There is intentionally NO
HTTP route that can create the first admin — bootstrapping is operator-only.

    uv run python -m backend.cli.bootstrap_admin

Email + password are read from ``BOOTSTRAP_ADMIN_EMAIL`` / ``BOOTSTRAP_ADMIN_PASSWORD``
if set (for non-interactive/secret-manager runs), otherwise prompted. The password is
never echoed or logged.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from backend.app.auth.passwords import PasswordPolicyError, hash_password, validate_password_policy
from backend.app.db import session as db_session
from backend.app.repositories import audit
from backend.app.repositories import tenants as tenants_repo
from backend.app.repositories import users as users_repo


async def bootstrap_admin(email: str, password: str) -> tuple[str, str]:
    """Create the platform-admin user + their auto-provisioned tenant + owner membership.

    Returns ``(user_id, tenant_id)`` as strings. Raises on policy violation or if the
    email already exists.
    """
    validate_password_policy(password)
    normalized = users_repo.normalize_email(email)
    async with db_session.SessionLocal() as db:
        if await users_repo.get_user_by_email(db, normalized) is not None:
            raise ValueError(f"A user with email {normalized!r} already exists.")
        pw_hash = await hash_password(password)
        user = await users_repo.create_user(
            db,
            email=normalized,
            status="active",
            is_platform_admin=True,
            password_hash=pw_hash,
        )
        tenant = await tenants_repo.create_tenant(db, name=normalized)
        await tenants_repo.create_membership(
            db, tenant_id=tenant.id, user_id=user.id, role="tenant_admin"
        )
        await audit.record_event(
            db,
            event_type="admin.bootstrap",
            actor_user_id=user.id,
            target_user_id=user.id,
            tenant_id=tenant.id,
        )
        await db.commit()
        return str(user.id), str(tenant.id)


def main() -> int:
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL") or input("Founder email: ").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or getpass.getpass("Founder password: ")
    if not email or not password:
        print("Both email and password are required.", file=sys.stderr)
        return 2
    try:
        user_id, tenant_id = asyncio.run(bootstrap_admin(email, password))
    except PasswordPolicyError as exc:
        print(f"Password rejected: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Created platform admin {email}")
    print(f"  user_id={user_id}")
    print(f"  tenant_id={tenant_id}")
    print("Next: run `uv run alembic -c backend/alembic.ini upgrade head` to add tenant_id + RLS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
