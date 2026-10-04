"""One-shot database initializer: migrate → bootstrap founder → migrate (feature 006/007).

Collapses the three-step R8 dance (`upgrade 0002` → `bootstrap_admin` → `upgrade head`)
into a single, idempotent command so a fresh (or just-reset) database comes up ready:

    uv run python -m backend.cli.init_db

Why three steps exist at all: migration ``0003_tenant_columns`` backfills every existing
pre-tenancy row to the **founder** tenant, so the founder must exist *before* it runs —
but the founder can only be created once ``0002_auth_tenancy`` has built the auth tables.
This command runs them in order for you:

  1. ``alembic upgrade 0002_auth_tenancy``  — create the auth/tenancy tables.
  2. create the platform-admin founder **iff** none exists yet.
  3. ``alembic upgrade head``               — tenant_id backfill, RLS, feature tables.

Re-running is safe: already-applied migrations are skipped and an existing founder is left
untouched (so you can run it on every deploy). Founder credentials come from
``BOOTSTRAP_ADMIN_EMAIL`` / ``BOOTSTRAP_ADMIN_PASSWORD`` for non-interactive / secret-manager
runs; otherwise you're prompted. The password is never echoed or logged.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.auth.passwords import PasswordPolicyError
from backend.app.config import settings
from backend.app.repositories import users as users_repo
from backend.cli.bootstrap_admin import bootstrap_admin

# The last revision before 0003 needs the founder to exist (see module docstring).
_BOOTSTRAP_REVISION = "0002_auth_tenancy"
# alembic.ini lives next to the migrations dir, at backend/alembic.ini.
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config() -> Config:
    return Config(str(_ALEMBIC_INI))


async def _platform_admin_exists() -> bool:
    """True if a platform admin already exists (connects as the migration owner)."""
    engine = create_async_engine(settings.owner_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            return await users_repo.count_active_admins(db) > 0
    finally:
        await engine.dispose()


def main() -> int:
    cfg = _alembic_config()

    # Step 1: ensure the auth/tenancy tables exist (no-op if already past 0002).
    print(f"[init-db] Migrating to {_BOOTSTRAP_REVISION}…")
    command.upgrade(cfg, _BOOTSTRAP_REVISION)

    # Step 2: create the founder once; idempotent on re-runs.
    if asyncio.run(_platform_admin_exists()):
        print("[init-db] Platform admin already exists — skipping founder bootstrap.")
    else:
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL") or input("Founder email: ").strip()
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or getpass.getpass("Founder password: ")
        if not email or not password:
            print(
                "[init-db] Both email and password are required. Set BOOTSTRAP_ADMIN_EMAIL / "
                "BOOTSTRAP_ADMIN_PASSWORD or enter them when prompted.",
                file=sys.stderr,
            )
            return 2
        try:
            user_id, tenant_id = asyncio.run(bootstrap_admin(email, password))
        except PasswordPolicyError as exc:
            print(f"[init-db] Password rejected: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"[init-db] {exc}", file=sys.stderr)
            return 1
        print(f"[init-db] Created platform admin {email} (user_id={user_id}, tenant_id={tenant_id})")

    # Step 3: finish migrating — tenant_id backfill, RLS, and the feature tables.
    print("[init-db] Migrating to head…")
    command.upgrade(cfg, "head")
    print("[init-db] Database is at head and ready. Sign in at /login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
