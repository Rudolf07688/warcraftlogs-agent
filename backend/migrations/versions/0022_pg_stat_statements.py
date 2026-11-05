"""statement statistics and the telemetry monitoring role (Postgres only, feature 058, sc-417)

``pg_stat_statements`` (the db service preloads it, docker-compose.yml) feeds Alloy's Postgres
exporter. The exporter logs in as a monitoring role: a member of ``pg_monitor`` with CONNECT on the
database and nothing else (no table privileges, not the owner, not a superuser). Like 0004's
runtime role it comes from the environment (PG_MONITOR_USER, PG_MONITOR_PASSWORD), but there is no
default password: without PG_MONITOR_PASSWORD the role is skipped, the exporter reports the
database as down, and the app is unaffected. To add it later: set the password, then
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

_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _monitor_role() -> str:
    role = os.getenv("PG_MONITOR_USER") or "wcl_monitor"
    if not _ROLE_NAME.match(role):
        raise ValueError("PG_MONITOR_USER must be a plain lower-case identifier")
    return role


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # statement statistics and roles are Postgres-only
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    password = os.getenv("PG_MONITOR_PASSWORD")
    if not password:
        return
    role = _monitor_role()
    exists = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
    if not exists:
        # Driver-level SQL: no bind-parameter parsing, so a ':' in the password stays literal.
        pw = password.replace("'", "''")
        bind.exec_driver_sql(
            f"CREATE ROLE {role} LOGIN PASSWORD '{pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
        )
    op.execute(f"GRANT pg_monitor TO {role}")
    db = bind.execute(sa.text("SELECT current_database()")).scalar()
    op.execute(f'GRANT CONNECT ON DATABASE "{db}" TO {role}')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = _monitor_role()
    exists = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
    if exists:
        db = bind.execute(sa.text("SELECT current_database()")).scalar()
        op.execute(f'REVOKE CONNECT ON DATABASE "{db}" FROM {role}')
        op.execute(f"DROP ROLE {role}")
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
