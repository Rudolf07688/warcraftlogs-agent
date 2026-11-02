"""raw_fetches: partial index for the stored-reports lookup (feature 047, sc-324)

``list_stored_reports_for_character`` reads the newest stored report summaries. Without an index
it scanned every ``raw_fetches`` row; this partial index holds only the rows of our two summary
queries, newest first, so the lookup walks it and stops at its limit. The predicate is the
literal one the repository's query used. Feature 051 (sc-354) replaces it in 0021.

Built and dropped CONCURRENTLY outside the migration transaction, so writes to ``raw_fetches``
never wait for the build (051 sc-359; the rule is in ``script.py.mako``).

Revision ID: 0020_raw_fetch_summary_index
Revises: 0019_kb_chunks
Create Date: 2026-11-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_raw_fetch_summary_index"
down_revision: Union[str, None] = "0019_kb_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PREDICATE = "operation_name IN ('ReportSummary', 'ReportsBatch')"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # A failed concurrent build leaves an INVALID index behind: drop it so a re-run converges.
        op.drop_index(
            "ix_raw_fetches_summaries", table_name="raw_fetches", postgresql_concurrently=True, if_exists=True
        )
        op.create_index(
            "ix_raw_fetches_summaries",
            "raw_fetches",
            [sa.text("fetched_at DESC")],
            postgresql_where=sa.text(_PREDICATE),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_raw_fetches_summaries", table_name="raw_fetches", postgresql_concurrently=True, if_exists=True
        )
