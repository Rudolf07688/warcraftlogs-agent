"""conversations.pinned_at + conversations.title_source (feature 019)

``pinned_at`` (nullable): when the conversation was pinned; NULL = not pinned (sc-165).

``title_source``: where the title came from (sc-155) — ``auto`` (default name, eligible
for one generated title), ``explicit`` (named at creation), ``generated`` (generation
claimed) or ``legacy``. Rows that exist before this migration are backfilled to
``legacy`` so their names never change (FR-020); new rows default to ``auto``. RLS on
``conversations`` is row-level, so the new columns need no policy change.

Revision ID: 0012_conversation_pin_title
Revises: 0011_guide_content_types
Create Date: 2026-10-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_conversation_pin_title"
down_revision: Union[str, None] = "0011_guide_content_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("title_source", sa.String(10), nullable=False, server_default="auto"),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 0004 FORCEs RLS on conversations, so the owner is bound by its own tenant policy
        # and, without SUPERUSER/BYPASSRLS, the backfill would match no rows. Lift FORCE for
        # the UPDATE only; Alembic runs this revision in one transaction and Postgres DDL is
        # transactional, so a failure rolls FORCE back to its previous state.
        op.execute("ALTER TABLE conversations NO FORCE ROW LEVEL SECURITY")
        op.execute("UPDATE conversations SET title_source = 'legacy'")
        op.execute("ALTER TABLE conversations FORCE ROW LEVEL SECURITY")
    else:
        op.execute("UPDATE conversations SET title_source = 'legacy'")


def downgrade() -> None:
    op.drop_column("conversations", "title_source")
    op.drop_column("conversations", "pinned_at")
