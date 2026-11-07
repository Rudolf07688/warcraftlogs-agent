"""the workspace's main class/spec/content and the onboarding skip (feature 074, sc-166/167)

One tenant-owned table, ``profile_settings``: one row per tenant (``tenant_id`` is the key)
with ``main_class``, ``main_spec``, ``main_content`` (raid, mplus or both; a CHECK) and
``onboarding_dismissed_at``. The API validates class and spec against the live roster, so
they carry no constraint here. Onboarding is pending while a tenant has no row or no skip
time, and no own character; every tenant that exists now gets a row marked as skipped, so
only accounts created from here on see the welcome prompt.

A table rather than ``tenants`` columns: ``backend/cli/bootstrap_admin.py`` inserts a tenant
through the ORM between ``upgrade 0002_auth_tenancy`` and ``upgrade head``, and the ORM names
every mapped column. Same RLS enable + tenant policy as ``0016_profile_proposals``.

Revision ID: 0023_profile_main_spec
Revises: 0022_pg_stat_statements
Create Date: 2026-11-07
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_profile_main_spec"
down_revision: Union[str, None] = "0022_pg_stat_statements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.Uuid(as_uuid=True)
_TS = sa.DateTime(timezone=True)

_TABLE = "profile_settings"
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _runtime_role() -> str:
    # Mirror 0004_rls: the non-privileged role the app connects as.
    return os.getenv("APP_DB_USER", "wcl_app")


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "tenant_id", _UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("main_class", sa.String(40), nullable=True),
        sa.Column("main_spec", sa.String(40), nullable=True),
        sa.Column("main_content", sa.String(8), nullable=True),
        sa.Column("onboarding_dismissed_at", _TS, nullable=True),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "main_content IN ('raid', 'mplus', 'both')", name="ck_profile_settings_main_content"
        ),
    )
    # Existing workspaces are not new: mark them as having skipped the prompt. Runs as the
    # migration owner before RLS is forced on the table.
    op.execute(
        sa.text(
            f"INSERT INTO {_TABLE} (tenant_id, onboarding_dismissed_at) "
            "SELECT id, CURRENT_TIMESTAMP FROM tenants"
        )
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # RLS is Postgres-only; SQLite tests assert app-level scoping instead.
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {_TABLE} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} TO {_runtime_role()}")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {_TABLE}")
    op.drop_table(_TABLE)
