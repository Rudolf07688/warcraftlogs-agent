"""raw_fetches.own_summary and the grants-driven stored-reports lookup (feature 051, sc-354)

``own_summary`` marks the rows of our own fixed report summary query (single or batch) with exact
codes; the app sets it when writing, and this migration backfills it with the rule the lookup
used before (each row's key re-derived from our query text and its params, codes exact and equal).
The lookup then reads only own summaries naming a code granted to the tenant or confirmed public
recently: a partial GIN index on the flagged rows' codes, and indexes for the two code sources.
0020's ``ix_raw_fetches_summaries`` is no longer used and is dropped.

Nothing here holds a lock on ``raw_fetches`` for long (051 sc-359, the rule in
``script.py.mako``): everything runs outside the migration transaction. The column is added with a
constant default (metadata only, a brief exclusive lock), the backfill updates in short committed
batches, and the indexes are built and dropped CONCURRENTLY. Every step is guarded (IF [NOT]
EXISTS, drop-then-create, an idempotent backfill), so a re-run after a failure converges.

Revision ID: 0021_raw_fetch_own_summary
Revises: 0020_raw_fetch_summary_index
Create Date: 2026-11-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from wcl_agent.client.queries import REPORT_SUMMARY, report_summaries_query
from wcl_agent.client.wcl_client import _flight_key, exact_report_codes

revision: str = "0021_raw_fetch_own_summary"
down_revision: Union[str, None] = "0020_raw_fetch_summary_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUMMARY_PREDICATE = "operation_name IN ('ReportSummary', 'ReportsBatch')"
_CHUNK = 1000
# (name, table, columns, using, where)
_INDEXES = (
    ("ix_raw_fetches_own_summary_codes", "raw_fetches", ["report_codes"], "gin", "own_summary"),
    ("ix_raw_reports_public_checked", "raw_reports", ["checked_at"], None, "visibility = 'public'"),
    ("ix_raw_fetch_grants_tenant_granted", "raw_fetch_grants", ["tenant_id", "granted_at"], None, None),
)


def is_own(query_key: str, params: object, codes: object) -> bool:
    """The pre-051 lookup's rule for one stored row (047 ``_our_summary``), frozen here."""
    if not isinstance(params, dict) or not params:
        return False
    if set(params) == {"code"}:
        query = REPORT_SUMMARY
    elif set(params) == {f"c{i}" for i in range(len(params))}:
        query = report_summaries_query(len(params))
    else:
        return False
    exact = exact_report_codes(query, params)
    return exact is not None and exact == codes and _flight_key(query, params) == query_key


def backfill(conn: sa.Connection) -> int:
    """Flag every stored summary row the old rule accepts; returns how many. Reads keys, params
    and codes only (never payloads); in autocommit each chunk's UPDATE commits on its own, so row
    locks are held for one chunk. Re-running it only re-sets flags already set."""
    rows = sa.table(
        "raw_fetches", sa.column("query_key"), sa.column("params", sa.JSON), sa.column("report_codes", sa.JSON),
        sa.column("operation_name"), sa.column("own_summary", sa.Boolean),
    )
    found = conn.execute(
        sa.select(rows.c.query_key, rows.c.params, rows.c.report_codes).where(sa.text(_SUMMARY_PREDICATE))
    )
    keys = [key for key, params, codes in found if is_own(key, params, codes)]
    for start in range(0, len(keys), _CHUNK):
        conn.execute(
            sa.update(rows).where(rows.c.query_key.in_(keys[start : start + _CHUNK])).values(own_summary=True)
        )
    return len(keys)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.add_column(
            "raw_fetches",
            sa.Column("own_summary", sa.Boolean(), nullable=False, server_default=sa.false()),
            if_not_exists=True,
        )
        backfill(op.get_bind())
        for name, table, columns, using, where in _INDEXES:
            # A failed concurrent build leaves an INVALID index behind: drop it so a re-run converges.
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
            op.create_index(
                name, table, columns, postgresql_using=using,
                postgresql_where=sa.text(where) if where else None, postgresql_concurrently=True,
            )
        op.drop_index(
            "ix_raw_fetches_summaries", table_name="raw_fetches", postgresql_concurrently=True, if_exists=True
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_raw_fetches_summaries", table_name="raw_fetches", postgresql_concurrently=True, if_exists=True
        )
        op.create_index(
            "ix_raw_fetches_summaries", "raw_fetches", [sa.text("fetched_at DESC")],
            postgresql_where=sa.text(_SUMMARY_PREDICATE), postgresql_concurrently=True,
        )
        for name, table, _columns, _using, _where in reversed(_INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
        op.drop_column("raw_fetches", "own_summary", if_exists=True)
