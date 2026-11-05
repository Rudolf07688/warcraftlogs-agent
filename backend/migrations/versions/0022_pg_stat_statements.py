"""statement statistics and the telemetry monitoring role (Postgres only, feature 058, sc-417)

``pg_stat_statements`` (the db service preloads it, docker-compose.yml) feeds Alloy's Postgres
exporter. The exporter logs in as a monitoring role: a member of ``pg_monitor`` with CONNECT on the
database and nothing else (no table privileges, not the owner, not a superuser). Like 0004's
runtime role it comes from the environment (PG_MONITOR_USER, PG_MONITOR_PASSWORD), but there is no
default password: without PG_MONITOR_PASSWORD the role is skipped, the exporter reports the
database as down, and the app is unaffected. The password must be 16 or more letters and digits
(it goes into the exporter's connection URL). An existing role of that name is used only if it
is itself monitor-only (no superuser, CREATEROLE, CREATEDB or BYPASSRLS, no other memberships,
owns nothing); anything else stops the migration, so the variable can't point the exporter at the
owner or the runtime role. To add the role later: set the password, then
``alembic downgrade 0021_raw_fetch_own_summary && alembic upgrade head``.

Revision ID: 0022_pg_stat_statements
Revises: 0021_raw_fetch_own_summary
Create Date: 2026-11-05
"""
from __future__ import annotations

import os
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_pg_stat_statements"
down_revision: Union[str, None] = "0021_raw_fetch_own_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")
_PASSWORD = re.compile(r"[A-Za-z0-9]{16,}")

# Why an existing role isn't monitor-only (empty: it is): attributes, other memberships, owned
# relations or databases.
_NOT_MONITOR_ONLY = sa.text(
    """
    SELECT concat_ws(', ',
      CASE WHEN r.rolsuper THEN 'superuser' END,
      CASE WHEN r.rolcreaterole THEN 'createrole' END,
      CASE WHEN r.rolcreatedb THEN 'createdb' END,
      CASE WHEN r.rolbypassrls THEN 'bypassrls' END,
      CASE WHEN EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
                        WHERE m.member = r.oid AND g.rolname <> 'pg_monitor') THEN 'other memberships' END,
      CASE WHEN EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = r.oid)
             OR EXISTS (SELECT 1 FROM pg_database d WHERE d.datdba = r.oid) THEN 'owns objects' END)
    FROM pg_roles r WHERE r.rolname = :r
    """
)


def _monitor_role() -> str:
    role = os.getenv("PG_MONITOR_USER") or "wcl_monitor"
    if not _ROLE_NAME.fullmatch(role):
        raise ValueError("PG_MONITOR_USER must be a plain lower-case identifier")
    return role


def _check_monitor_only(bind, role: str) -> bool:
    """True if the role exists and is monitor-only; False if it doesn't exist; raises otherwise."""
    reasons = bind.execute(_NOT_MONITOR_ONLY, {"r": role}).scalar()
    if reasons is None:
        return False
    if reasons:
        raise RuntimeError(f"role {role} exists and is not monitor-only ({reasons}): pick another PG_MONITOR_USER")
    return True


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # statement statistics and roles are Postgres-only
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    password = os.getenv("PG_MONITOR_PASSWORD")
    if not password:
        return
    if not _PASSWORD.fullmatch(password):
        raise ValueError("PG_MONITOR_PASSWORD must be 16 or more letters and digits")
    role = _monitor_role()
    if role in {os.getenv("POSTGRES_USER"), os.getenv("APP_DB_USER"), bind.execute(sa.text("SELECT current_user")).scalar()}:
        raise ValueError("PG_MONITOR_USER must not be the owner or the runtime role")
    if not _check_monitor_only(bind, role):
        # Letters and digits only (checked above): nothing to quote or escape.
        bind.exec_driver_sql(
            f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
        )
    op.execute(f"GRANT pg_monitor TO {role}")
    db = bind.execute(sa.text("SELECT current_database()")).scalar()
    op.execute(f'GRANT CONNECT ON DATABASE "{db}" TO {role}')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = _monitor_role()
    if _check_monitor_only(bind, role):
        db = bind.execute(sa.text("SELECT current_database()")).scalar()
        op.execute(f'REVOKE CONNECT ON DATABASE "{db}" FROM {role}')
        op.execute(f"DROP ROLE {role}")
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
