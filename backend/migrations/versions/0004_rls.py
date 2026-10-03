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

import sqlalchemy as sa
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
    # CREATE so ADK's DatabaseSessionService can create its session tables as this role.
    conn.execute(sa.text(f"GRANT USAGE, CREATE ON SCHEMA public TO {role}"))


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
    # The app does ALL its work as the runtime role, including auth (users/auth_sessions/…),
    # which are NOT under RLS but still need table privileges. Grant DML on every existing
    # app table + sequence usage (the audit BIGSERIAL). RLS + FORCE still constrains the 7
    # tenant tables regardless of these grants.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
    # Future owner-created tables/sequences (later migrations) are usable without re-granting.
    owner = bind.execute(sa.text("SELECT current_user")).scalar()
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {role}"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = _runtime_role()
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM {role}")
    op.execute(f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM {role}")
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
