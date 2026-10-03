"""add tenant_id to the 7 tenant-owned tables (+ founder backfill, per-tenant uniqueness)

Phased per the guide (research R8): add nullable tenant_id → backfill every existing row to
the FOUNDER tenant → set NOT NULL → add tenant-leading indexes and per-tenant uniqueness.
Fails loudly if no platform admin exists yet (run `python -m backend.cli.bootstrap_admin`
first), so existing data is never assigned to an ambiguous owner.

Revision ID: 0003_tenant_columns
Revises: 0002_auth_tenancy
Create Date: 2026-10-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tenant_columns"
down_revision: Union[str, None] = "0002_auth_tenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)

# (table, tenant-leading index name, index columns)
_TABLES = [
    ("conversations", "ix_conversations_tenant_updated", ["tenant_id", "updated_at"]),
    ("messages", "ix_messages_tenant_conv_seq", ["tenant_id", "conversation_id", "seq"]),
    ("tracked_raids", "ix_tracked_raids_tenant_asked", ["tenant_id", "last_asked_at"]),
    ("captured_graphs", "ix_captured_graphs_tenant_conv", ["tenant_id", "conversation_id"]),
    ("user_characters", "ix_user_characters_tenant_role", ["tenant_id", "role"]),
    ("guild_profile", "ix_guild_profile_tenant", ["tenant_id"]),
    ("artifacts", "ix_artifacts_tenant_conv", ["tenant_id", "conversation_id"]),
]


def _founder_tenant_id(conn) -> str:
    row = conn.execute(
        sa.text(
            "SELECT t.id FROM tenants t "
            "JOIN tenant_memberships m ON m.tenant_id = t.id "
            "JOIN users u ON u.id = m.user_id "
            "WHERE u.is_platform_admin = true "
            "ORDER BY t.created_at LIMIT 1"
        )
    ).scalar()
    if row is None:
        raise RuntimeError(
            "No platform admin / founder tenant found. Run "
            "`uv run python -m backend.cli.bootstrap_admin` BEFORE this migration so "
            "existing data can be backfilled to the founder's workspace (research R8)."
        )
    return str(row)


def upgrade() -> None:
    conn = op.get_bind()
    founder = _founder_tenant_id(conn)

    for table, index_name, index_cols in _TABLES:
        # 1. add nullable → 2. backfill to founder → 3. set NOT NULL.
        op.add_column(table, sa.Column("tenant_id", _UUID, nullable=True))
        conn.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
            {"tid": founder},
        )
        remaining = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
        ).scalar()
        if remaining:
            raise RuntimeError(f"{table}: {remaining} rows still have NULL tenant_id after backfill.")
        op.alter_column(table, "tenant_id", existing_type=_UUID, nullable=False)
        op.create_foreign_key(
            f"fk_{table}_tenant", table, "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
        )
        op.create_index(index_name, table, index_cols)

    # Per-tenant uniqueness changes.
    # tracked_raids.report_code: global unique → per-tenant.
    op.drop_index("ix_tracked_raids_report_code", table_name="tracked_raids")
    op.create_index("ix_tracked_raids_report_code", "tracked_raids", ["report_code"])
    op.create_unique_constraint(
        "uq_tracked_raid_tenant_code", "tracked_raids", ["tenant_id", "report_code"]
    )
    # user_characters identity: add tenant_id to the unique key.
    op.drop_constraint("uq_user_char_identity", "user_characters", type_="unique")
    op.create_unique_constraint(
        "uq_user_char_identity",
        "user_characters",
        ["tenant_id", "name", "server", "region", "role"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_char_identity", "user_characters", type_="unique")
    op.create_unique_constraint(
        "uq_user_char_identity", "user_characters", ["name", "server", "region", "role"]
    )
    op.drop_constraint("uq_tracked_raid_tenant_code", "tracked_raids", type_="unique")
    op.drop_index("ix_tracked_raids_report_code", table_name="tracked_raids")
    op.create_index(
        "ix_tracked_raids_report_code", "tracked_raids", ["report_code"], unique=True
    )
    for table, index_name, _cols in _TABLES:
        op.drop_index(index_name, table_name=table)
        op.drop_constraint(f"fk_{table}_tenant", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")
