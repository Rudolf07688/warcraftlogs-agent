"""baseline: snapshot of the pre-multi-tenancy schema

Captures the schema as it existed BEFORE feature 006 (features 001–005), so Alembic
history starts from a known point. Each table is created only if it does not already
exist, so this is safe to run against the founder's existing database (which already
has these tables from the old ``create_all`` path) as well as a fresh install.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")
_TS = sa.DateTime(timezone=True)


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has("conversations"):
        op.create_table(
            "conversations",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("title", sa.String(200), nullable=False, server_default="New chat"),
            sa.Column("model", sa.String(100), nullable=False),
            sa.Column("created_at", _TS, server_default=sa.func.now()),
            sa.Column("updated_at", _TS, server_default=sa.func.now()),
        )
    if not _has("messages"):
        op.create_table(
            "messages",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column(
                "conversation_id",
                _UUID,
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(10), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(10), nullable=False, server_default="complete"),
            sa.Column("created_at", _TS, server_default=sa.func.now()),
            sa.UniqueConstraint("conversation_id", "seq", name="uq_message_conv_seq"),
        )
        op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    if not _has("tracked_raids"):
        op.create_table(
            "tracked_raids",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("report_code", sa.String(32), nullable=False),
            sa.Column("label", sa.String(200), nullable=False),
            sa.Column("zone", sa.String(120), nullable=True),
            sa.Column("guild", sa.String(120), nullable=True),
            sa.Column("report_started_at", _TS, nullable=True),
            sa.Column("first_seen_at", _TS, server_default=sa.func.now()),
            sa.Column("last_asked_at", _TS, server_default=sa.func.now()),
            sa.Column(
                "last_conversation_id",
                _UUID,
                sa.ForeignKey("conversations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("encounters", _JSON, nullable=True),
        )
        op.create_index(
            "ix_tracked_raids_report_code", "tracked_raids", ["report_code"], unique=True
        )
    if not _has("captured_graphs"):
        op.create_table(
            "captured_graphs",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column(
                "conversation_id",
                _UUID,
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("message_seq", sa.Integer(), nullable=True),
            sa.Column("report_code", sa.String(32), nullable=False),
            sa.Column("data_type", sa.String(40), nullable=False),
            sa.Column("fight_id", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_id", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("graph_json", _JSON, nullable=False),
            sa.Column("created_at", _TS, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_captured_graphs_conversation_id", "captured_graphs", ["conversation_id"]
        )
    if not _has("user_characters"):
        op.create_table(
            "user_characters",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("role", sa.String(10), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("server", sa.String(100), nullable=False),
            sa.Column("region", sa.String(8), nullable=False),
            sa.Column("class_name", sa.String(40), nullable=True),
            sa.Column("active_spec", sa.String(40), nullable=True),
            sa.Column("guide_markdown", sa.Text(), nullable=True),
            sa.Column("guide_status", sa.String(10), nullable=False, server_default="none"),
            sa.Column("guide_updated_at", _TS, nullable=True),
            sa.Column("created_at", _TS, server_default=sa.func.now()),
            sa.Column("updated_at", _TS, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "name", "server", "region", "role", name="uq_user_char_identity"
            ),
        )
    if not _has("guild_profile"):
        op.create_table(
            "guild_profile",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("server", sa.String(100), nullable=False),
            sa.Column("region", sa.String(8), nullable=False),
            sa.Column("summary_markdown", sa.Text(), nullable=True),
            sa.Column("summary_status", sa.String(10), nullable=False, server_default="none"),
            sa.Column("summary_updated_at", _TS, nullable=True),
            sa.Column("created_at", _TS, server_default=sa.func.now()),
            sa.Column("updated_at", _TS, server_default=sa.func.now()),
        )
    if not _has("artifacts"):
        op.create_table(
            "artifacts",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column(
                "conversation_id",
                _UUID,
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("message_seq", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("spec_json", _JSON, nullable=False),
            sa.Column("created_at", _TS, server_default=sa.func.now()),
        )
        op.create_index("ix_artifacts_conversation_id", "artifacts", ["conversation_id"])


def downgrade() -> None:
    # Baseline is the floor of history; dropping the pre-existing app tables would be
    # destructive and is intentionally unsupported.
    raise NotImplementedError("Cannot downgrade below the baseline schema.")
