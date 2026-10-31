"""raw store visibility — who may be served a stored WCL response (feature 039, sc-178/sc-177)

``raw_fetches`` stays global (decision 6) but is now read, so each row is served only by the
visibility rule (specs/039-local-first-data/data-model.md):

* ``raw_reports`` (global, no RLS): per report code, the visibility and end time WCL last
  showed us, and when. "public" here makes a report's rows shareable.
* ``raw_fetch_grants`` (tenant-scoped, RLS ``tenant_isolation`` like 0004): a tenant fetched
  this report code from WCL itself, so its rows may be served to that tenant.
* ``raw_fetches.payload_hash``: sha256 of the body without ``data._cost``; an unchanged
  refetch only moves ``fetched_at`` (sc-177).

Revision ID: 0018_raw_store_visibility
Revises: 0017_proposal_user_rls
Create Date: 2026-11-01
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_raw_store_visibility"
down_revision: Union[str, None] = "0017_proposal_user_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TENANT = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def upgrade() -> None:
    op.add_column("raw_fetches", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.create_table(
        "raw_reports",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("visibility", sa.String(16), nullable=True),
        sa.Column("end_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "raw_fetch_grants",
        sa.Column(
            "tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("report_code", sa.String(32), primary_key=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )

    if op.get_bind().dialect.name != "postgresql":
        return  # RLS and grants are Postgres-only; SQLite tests assert app-level scoping.
    role = _runtime_role()
    op.execute("ALTER TABLE raw_fetch_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE raw_fetch_grants FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON raw_fetch_grants USING ({_TENANT}) WITH CHECK ({_TENANT})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON raw_reports, raw_fetch_grants TO {role}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON raw_fetch_grants")
    op.drop_table("raw_fetch_grants")
    op.drop_table("raw_reports")
    op.drop_column("raw_fetches", "payload_hash")
