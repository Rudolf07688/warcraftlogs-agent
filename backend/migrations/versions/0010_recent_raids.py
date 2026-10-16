"""recent raids for the welcome page (feature 013)

Three tenant-owned tables (data-model.md §1-3):

* ``recent_raids``: one row per Warcraft Logs report an own character was logged in,
  stored for good once final (a finished report never changes).
* ``recent_raid_characters``: which own characters took part (cascade on character delete).
* ``recent_raid_refresh``: one row per tenant; the refresh state and the cross-instance
  claim lock (research R4).

All three get the same RLS enable + tenant policy as ``0005_known_entities``.

Revision ID: 0010_recent_raids
Revises: 0009_guide_provenance
Create Date: 2026-10-16
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_recent_raids"
down_revision: Union[str, None] = "0009_guide_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)

_NEW_TABLES = ["recent_raids", "recent_raid_characters", "recent_raid_refresh"]
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
        "recent_raids",
        sa.Column("id", _UUID, primary_key=True),
        _tenant_fk(),
        sa.Column("report_code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("zone_name", sa.String(120), nullable=True),
        sa.Column("guild_name", sa.String(120), nullable=True),
        sa.Column("started_at", _TS, nullable=False),
        sa.Column("ended_at", _TS, nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), nullable=True),
        sa.Column("bosses_pulled", sa.SmallInteger(), nullable=True),
        sa.Column("bosses_killed", sa.SmallInteger(), nullable=True),
        sa.Column("is_raid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details_fetched_at", _TS, nullable=True),
        sa.Column("first_seen_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "report_code", name="uq_recent_raid_tenant_code"),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN (1, 3, 4, 5)", name="ck_recent_raid_difficulty"
        ),
        sa.CheckConstraint(
            "bosses_killed IS NULL OR bosses_pulled IS NULL OR bosses_killed <= bosses_pulled",
            name="ck_recent_raid_kills",
        ),
    )
    op.create_index(
        "ix_recent_raids_tenant_started", "recent_raids", ["tenant_id", "started_at"]
    )
    op.create_table(
        "recent_raid_characters",
        sa.Column(
            "raid_id",
            _UUID,
            sa.ForeignKey("recent_raids.id", ondelete="CASCADE"),
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
        "ix_recent_raid_characters_tenant_char",
        "recent_raid_characters",
        ["tenant_id", "character_id"],
    )
    op.create_table(
        "recent_raid_refresh",
        sa.Column(
            "tenant_id",
            _UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(10), nullable=False, server_default="idle"),
        sa.Column("run_id", _UUID, nullable=True),
        sa.Column("started_at", _TS, nullable=True),
        sa.Column("finished_at", _TS, nullable=True),
        sa.Column("last_success_at", _TS, nullable=True),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("character_set", sa.String(64), nullable=True),
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
    op.drop_table("recent_raid_refresh")
    op.drop_index(
        "ix_recent_raid_characters_tenant_char", table_name="recent_raid_characters"
    )
    op.drop_table("recent_raid_characters")
    op.drop_index("ix_recent_raids_tenant_started", table_name="recent_raids")
    op.drop_table("recent_raids")
