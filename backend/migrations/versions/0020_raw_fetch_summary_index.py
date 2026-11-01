"""raw_fetches: partial index for the stored-reports lookup (feature 047, sc-324)

``list_stored_reports_for_character`` reads the newest stored report summaries. Without an index
it scanned every ``raw_fetches`` row; this partial index holds only the rows of our two summary
queries, newest first, so the lookup walks it and stops at its limit. The predicate is the
literal one the repository's query uses (``models.RAW_SUMMARY_PREDICATE``).

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
    op.create_index(
        "ix_raw_fetches_summaries",
        "raw_fetches",
        [sa.text("fetched_at DESC")],
        postgresql_where=sa.text(_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("ix_raw_fetches_summaries", table_name="raw_fetches")
