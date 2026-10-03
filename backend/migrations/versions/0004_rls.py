"""enable + force row-level security on the tenant-owned tables (Postgres only)

Defense in depth (FR-020, research R4): even if an application ``WHERE tenant_id`` predicate
is ever missed, RLS still blocks cross-tenant reads/writes. The runtime role is granted DML
but is NOT the owner and lacks BYPASSRLS, so the policies actually constrain it. Each
protected transaction sets ``app.tenant_id`` transaction-locally.

Revision ID: 0004_rls
Revises: 0003_tenant_columns
Create Date: 2026-10-03
"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

revision: str = "0004_rls"
down_revision: Union[str, None] = "0003_tenant_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = [
    "conversations",
    "messages",
    "tracked_raids",
    "captured_graphs",
    "user_characters",
    "guild_profile",
    "artifacts",
]

_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _runtime_role() -> str:
    # The non-privileged role the app connects as (docker-compose / .env APP_DB_USER).
    return os.getenv("APP_DB_USER", "wcl_app")


def _runtime_password() -> str:
    return os.getenv("APP_DB_PASSWORD", "wcl_app")


def _ensure_runtime_role(conn, role: str) -> None:
    """Create the non-privileged runtime role if it doesn't exist, idempotently.

    The docker-compose postgres-init script only runs on a FRESH data volume, so on an
    existing database the role may be absent. Making the migration self-sufficient means
    `alembic upgrade head` works regardless of how the DB was provisioned. Requires the
    migration-owner to have CREATEROLE (the compose superuser does); on a managed Postgres
    where it doesn't, create the role manually first (see README) and this is a no-op.
    """
    pw = _runtime_password().replace("'", "''")
    conn.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} LOGIN PASSWORD '{pw}'
                  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
              END IF;
            END
            $$;
            """
        )
    )
    db = conn.execute(sa.text("SELECT current_database()")).scalar()
    conn.execute(sa.text(f'GRANT CONNECT ON DATABASE "{db}" TO {role}'))
    conn.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {role}"))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # RLS is Postgres-only; SQLite tests assert app-level scoping instead.
    role = _runtime_role()
    _ensure_runtime_role(bind, role)
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = _runtime_role()
    for table in _RLS_TABLES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM {role}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
