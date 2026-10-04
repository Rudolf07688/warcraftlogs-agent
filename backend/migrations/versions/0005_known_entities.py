"""known players + known encounters (feature 007 / US1)

Durable, per-tenant metadata captured from successful tool calls so later
conversations can reuse known players/encounters without re-querying Warcraft Logs.
Both tables carry ``tenant_id`` and get the same RLS enable + tenant policy that
``0004_rls`` applies to the peer tenant-owned tables.

Revision ID: 0005_known_entities
Revises: 0004_rls
Create Date: 2026-10-04
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_known_entities"
down_revision: Union[str, None] = "0004_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)

_NEW_TABLES = ["known_players", "known_encounters"]
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def upgrade() -> None:
    op.create_table(
        "known_players",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "tenant_id",
            _UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("server", sa.String(100), nullable=False),
        sa.Column("region", sa.String(8), nullable=False),
        sa.Column("class_name", sa.String(40), nullable=True),
        sa.Column("spec", sa.String(40), nullable=True),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column("first_seen_at", _TS, server_default=sa.func.now()),
        sa.Column("last_seen_at", _TS, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "name", "server", "region", name="uq_known_player_identity"
        ),
    )
    op.create_index(
        "ix_known_players_tenant_seen", "known_players", ["tenant_id", "last_seen_at"]
    )
    op.create_table(
        "known_encounters",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "tenant_id",
            _UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("encounter_name", sa.String(120), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("zone_name", sa.String(120), nullable=True),
        sa.Column("first_seen_at", _TS, server_default=sa.func.now()),
        sa.Column("last_seen_at", _TS, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "encounter_id", name="uq_known_encounter_identity"
        ),
    )
    op.create_index(
        "ix_known_encounters_tenant_seen",
        "known_encounters",
        ["tenant_id", "last_seen_at"],
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
        # 0004 set ALTER DEFAULT PRIVILEGES for the owner, so these grants are usually
        # already in place; re-granting explicitly keeps the migration self-sufficient.
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _NEW_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index("ix_known_encounters_tenant_seen", table_name="known_encounters")
    op.drop_table("known_encounters")
    op.drop_index("ix_known_players_tenant_seen", table_name="known_players")
    op.drop_table("known_players")
