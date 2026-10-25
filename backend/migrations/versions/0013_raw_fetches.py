"""raw_fetches — every Warcraft Logs response, stored for DB-first reads (feature 020)

Creates the GLOBAL ``raw_fetches`` table (data-model.md): one row per query key (query text
plus variables), upserted by the backend's fetch writer. Deliberately **not** tenant-scoped
and **no RLS** (decision 6): Warcraft Logs data is public, like the shared Redis cache. The
runtime role is granted DML (mirroring ``0007_spec_guides``).

``report_codes`` (every report the query names, batches too) gets a GIN index so a report's
rows are found with ``report_codes ? '<code>'``; ``report_code`` (exactly one report) a btree.

Revision ID: 0013_raw_fetches
Revises: 0012_conversation_pin_title
Create Date: 2026-10-25
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_raw_fetches"
down_revision: Union[str, None] = "0012_conversation_pin_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def upgrade() -> None:
    op.create_table(
        "raw_fetches",
        sa.Column("query_key", sa.String(64), primary_key=True),
        sa.Column("operation_name", sa.String(120), nullable=True),
        sa.Column("params", _JSON, nullable=False),
        sa.Column("report_code", sa.String(32), nullable=True),
        sa.Column("report_codes", _JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
    )
    op.create_index("ix_raw_fetches_report_code", "raw_fetches", ["report_code"])
    op.create_index(
        "ix_raw_fetches_report_codes", "raw_fetches", ["report_codes"], postgresql_using="gin"
    )

    if op.get_bind().dialect.name != "postgresql":
        return  # grants are Postgres-only; tests build the schema via metadata.create_all
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON raw_fetches TO {_runtime_role()}")


def downgrade() -> None:
    op.drop_index("ix_raw_fetches_report_codes", table_name="raw_fetches")
    op.drop_index("ix_raw_fetches_report_code", table_name="raw_fetches")
    op.drop_table("raw_fetches")
