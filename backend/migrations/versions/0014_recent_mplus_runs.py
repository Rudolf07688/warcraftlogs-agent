"""recent Mythic+ runs for the welcome page (feature 022)

Two tenant-owned tables (data-model.md):

* ``recent_mplus_runs``: one row per completed keystone fight found in a report an own
  character was logged in.
* ``recent_mplus_run_characters``: which own characters took part (cascade on character delete).

Both get the same RLS enable + tenant policy as ``0010_recent_raids``.

Revision ID: 0014_recent_mplus_runs
Revises: 0013_raw_fetches
Create Date: 2026-10-25
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_recent_mplus_runs"
down_revision: Union[str, None] = "0013_raw_fetches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)

_NEW_TABLES = ["recent_mplus_runs", "recent_mplus_run_characters"]
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def _tenant_fk() -> sa.Column:
    return sa.Column(
        "tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "recent_mplus_runs",
        sa.Column("id", _UUID, primary_key=True),
        _tenant_fk(),
        sa.Column("report_code", sa.String(32), nullable=False),
        sa.Column("fight_id", sa.Integer(), nullable=False),
        sa.Column("dungeon", sa.String(120), nullable=False),
        sa.Column("key_level", sa.SmallInteger(), nullable=False),
        sa.Column("started_at", _TS, nullable=False),
        sa.Column("timed", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "report_code", "fight_id", name="uq_recent_mplus_run_tenant_fight"
        ),
        sa.CheckConstraint("key_level > 0", name="ck_recent_mplus_run_level"),
    )
    op.create_index(
        "ix_recent_mplus_runs_tenant_started", "recent_mplus_runs", ["tenant_id", "started_at"]
    )
    op.create_table(
        "recent_mplus_run_characters",
        sa.Column(
            "run_id",
            _UUID,
            sa.ForeignKey("recent_mplus_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "character_id",
            _UUID,
            sa.ForeignKey("user_characters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        _tenant_fk(),
    )
    op.create_index(
        "ix_recent_mplus_run_characters_tenant_char",
        "recent_mplus_run_characters",
        ["tenant_id", "character_id"],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # RLS is Postgres-only; SQLite tests assert app-level scoping instead.
    role = _runtime_role()
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _NEW_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index(
        "ix_recent_mplus_run_characters_tenant_char", table_name="recent_mplus_run_characters"
    )
    op.drop_table("recent_mplus_run_characters")
    op.drop_index("ix_recent_mplus_runs_tenant_started", table_name="recent_mplus_runs")
    op.drop_table("recent_mplus_runs")
